"""
Field extraction utilities.

This module provides a LayoutLM-powered token-classification path (when the
required deps/model are available) and falls back to deterministic heuristics.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import threading
from typing import Any, Optional

from .extraction import extract_fields as extract_fields_heuristic


_MODEL_NAME = "Theivaprakasham/layoutlmv3-finetuned-invoice"

_LOAD_LOCK = threading.Lock()


@lru_cache(maxsize=1)
def _get_processor():
    from transformers import AutoProcessor

    # We pass `apply_ocr=False` because OCR is already done elsewhere.
    return AutoProcessor.from_pretrained(_MODEL_NAME, apply_ocr=False)


@lru_cache(maxsize=1)
def _get_model():
    from transformers import AutoModelForTokenClassification

    # Prefer safetensors consistently so we don't later download a different weight file.
    model = AutoModelForTokenClassification.from_pretrained(_MODEL_NAME, use_safetensors=True)
    model.eval()
    return model


def warmup_layoutlm() -> bool:
    """
    Best-effort warmup so first request doesn't block on HF downloads.
    Returns True if deps were available and warmup attempted.
    """
    try:
        import torch  # noqa: F401
        import transformers  # noqa: F401
    except Exception:
        return False

    with _LOAD_LOCK:
        _get_processor()
        _get_model()
    return True


@dataclass(frozen=True)
class _Span:
    label: str
    text: str
    confidence: float


def _normalize_box(box: list[int], w: int, h: int) -> list[int]:
    # LayoutLM expects 0..1000 normalized boxes
    x0, y0, x1, y1 = box
    if w <= 0 or h <= 0:
        return [0, 0, 0, 0]
    return [
        max(0, min(1000, int(1000 * x0 / w))),
        max(0, min(1000, int(1000 * y0 / h))),
        max(0, min(1000, int(1000 * x1 / w))),
        max(0, min(1000, int(1000 * y1 / h))),
    ]


def _field_for_entity(entity: str) -> Optional[str]:
    e = entity.lower()
    if "inv" in e and ("no" in e or "num" in e or "number" in e or "invoice" in e):
        return "invoice_number"
    if "date" in e:
        return "date"
    if any(k in e for k in ["vendor", "supplier", "company", "seller", "billfrom", "from"]):
        return "vendor"
    if any(k in e for k in ["amount", "total", "balance", "grandtotal", "due"]):
        return "amount"
    return None


def _best_span(spans: list[_Span]) -> Optional[_Span]:
    if not spans:
        return None
    # Prefer high confidence; tie-break by longer text.
    return sorted(spans, key=lambda s: (s.confidence, len(s.text)), reverse=True)[0]


def _layoutlm_extract(words: list[str], boxes: list[list[int]], image: Any) -> Optional[dict[str, dict[str, Any]]]:
    try:
        import torch
        # transformers is imported inside _get_* helpers; keep here only to detect availability.
    except Exception:
        return None

    if not words or not boxes or image is None or len(words) != len(boxes):
        return None

    with _LOAD_LOCK:
        processor = _get_processor()
        model = _get_model()

    w, h = image.size  # PIL Image
    norm_boxes = [_normalize_box(list(b), w=w, h=h) for b in boxes]

    encoding = processor(
        image,
        words,
        boxes=norm_boxes,
        return_tensors="pt",
        truncation=True,
        padding="max_length",
    )

    with torch.no_grad():
        outputs = model(**encoding)
        logits = outputs.logits  # (1, seq_len, num_labels)
        probs = torch.softmax(logits, dim=-1)
        pred_ids = torch.argmax(probs, dim=-1).squeeze(0).tolist()
        pred_confs = torch.max(probs, dim=-1).values.squeeze(0).tolist()

    id2label = getattr(model.config, "id2label", None) or {}
    word_ids = encoding.word_ids(batch_index=0)

    # Aggregate subword predictions back to words (max confidence for each word).
    per_word: list[tuple[str, float]] = [("O", 0.0) for _ in range(len(words))]
    for tok_i, wid in enumerate(word_ids):
        if wid is None or wid >= len(words):
            continue
        lbl = id2label.get(int(pred_ids[tok_i]), "O")
        conf = float(pred_confs[tok_i])
        if conf >= per_word[wid][1]:
            per_word[wid] = (lbl, conf)

    # Build BIO spans.
    spans_by_entity: dict[str, list[_Span]] = {}
    cur_entity: Optional[str] = None
    cur_words: list[str] = []
    cur_confs: list[float] = []

    def flush():
        nonlocal cur_entity, cur_words, cur_confs
        if cur_entity and cur_words:
            text = " ".join(cur_words).strip()
            if text:
                avg_conf = sum(cur_confs) / max(1, len(cur_confs))
                spans_by_entity.setdefault(cur_entity, []).append(_Span(cur_entity, text, float(avg_conf)))
        cur_entity, cur_words, cur_confs = None, [], []

    for wtxt, (lbl, conf) in zip(words, per_word):
        if lbl == "O" or not lbl:
            flush()
            continue
        if "-" in lbl:
            prefix, ent = lbl.split("-", 1)
        else:
            prefix, ent = "B", lbl

        if prefix == "B" or (cur_entity and ent != cur_entity):
            flush()
            cur_entity = ent
            cur_words = [wtxt]
            cur_confs = [conf]
        else:
            # I- continuation
            if cur_entity is None:
                cur_entity = ent
            cur_words.append(wtxt)
            cur_confs.append(conf)
    flush()

    # Map entities -> our target fields.
    out: dict[str, dict[str, Any]] = {}
    for entity, spans in spans_by_entity.items():
        field = _field_for_entity(entity)
        if not field:
            continue
        best = _best_span(spans)
        if not best:
            continue
        # Prefer a higher-confidence model prediction than any existing one.
        prev = out.get(field)
        if (prev is None) or (float(best.confidence) > float(prev.get("confidence", 0.0))):
            out[field] = {"value": best.text, "confidence": float(best.confidence), "source": "layoutlm"}

    return out or None


def extract_fields(words, boxes=None, image=None) -> dict[str, dict[str, Any]]:
    """
    Primary extraction entrypoint used by views.

    Returns per-field objects:
      { "value": <str|None>, "confidence": <float>, "source": "layoutlm"|"heuristic" }
    """
    word_list = list(words) if words is not None else []
    box_list = [list(b) for b in (boxes or [])]

    model_out = _layoutlm_extract(word_list, box_list, image=image)
    if model_out is None:
        return extract_fields_heuristic(word_list, boxes=box_list)

    # Fill missing fields from heuristics (never leave keys absent).
    heur = extract_fields_heuristic(word_list, boxes=box_list)
    merged = dict(heur)
    for k, v in model_out.items():
        merged[k] = v
    return merged