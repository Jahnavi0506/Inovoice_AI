import base64
import io
import os
import re
from pathlib import Path
from typing import Any, Optional

import cv2
import numpy as np
import pytesseract
from pdf2image import convert_from_path
from PIL import Image


def _configure_tesseract() -> None:
    cmd = (os.environ.get("TESSERACT_CMD") or "").strip()
    if cmd:
        pytesseract.pytesseract.tesseract_cmd = cmd
        return
    win = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
    if win.is_file():
        pytesseract.pytesseract.tesseract_cmd = str(win)


def _poppler_kwargs() -> dict[str, str]:
    p = (os.environ.get("POPPLER_PATH") or "").strip()
    if not p:
        win = Path(r"C:\poppler-25.12.0\Library\bin")
        if win.is_dir():
            p = str(win)
    if p and Path(p).is_dir():
        return {"poppler_path": p}
    return {}


_configure_tesseract()


def _imread_bgr(path: str):
    """Read image as BGR; works for non-ASCII paths on Windows."""
    data = np.fromfile(path, dtype=np.uint8)
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


def load_invoice_preview(file_path: str) -> Image.Image:
    """
    First-page / single-image preview without running OCR (lighter than extract_ocr_data).
    """
    if file_path.lower().endswith(".pdf"):
        images = convert_from_path(file_path, first_page=1, last_page=1, **_poppler_kwargs())
        return images[0]

    img = _imread_bgr(file_path)
    if img is None:
        raise ValueError(f"Could not read image: {file_path}")
    return Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))


def extract_ocr_data(file_path: str):
    if file_path.lower().endswith(".pdf"):
        images = convert_from_path(file_path, **_poppler_kwargs())
        pil_img = images[0]
        img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
    else:
        img = _imread_bgr(file_path)
        if img is None:
            raise ValueError(f"Could not read image: {file_path}")
        pil_img = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))

    data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)

    words = []
    boxes = []

    for i in range(len(data["text"])):
        if data["text"][i].strip() != "":
            words.append(data["text"][i])

            x = data["left"][i]
            y = data["top"][i]
            w = data["width"][i]
            h = data["height"][i]

            boxes.append([x, y, x + w, y + h])

    return words, boxes, pil_img


def pil_to_data_uri(pil_img: Image.Image, *, fmt: str = "PNG") -> str:
    buf = io.BytesIO()
    pil_img.save(buf, format=fmt)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    mime = "image/png" if fmt.upper() == "PNG" else "image/jpeg"
    return f"data:{mime};base64,{b64}"


def blur_score(pil_img: Image.Image) -> float:
    """
    Simple blur heuristic: variance of Laplacian (lower => blurrier).
    """
    img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2GRAY)
    return float(cv2.Laplacian(img, cv2.CV_64F).var())


_TOKEN_SPLIT_RE = re.compile(r"[^\w]+", re.UNICODE)


def _tokenize(s: str) -> list[str]:
    return [t for t in _TOKEN_SPLIT_RE.split((s or "").strip()) if t]


def _normalize_token(t: str) -> str:
    return re.sub(r"\s+", "", (t or "")).lower()


def _union_box(boxes: list[list[int]]) -> Optional[list[int]]:
    if not boxes:
        return None
    xs0 = [b[0] for b in boxes]
    ys0 = [b[1] for b in boxes]
    xs1 = [b[2] for b in boxes]
    ys1 = [b[3] for b in boxes]
    return [int(min(xs0)), int(min(ys0)), int(max(xs1)), int(max(ys1))]


def assign_field_boxes(
    *,
    words: list[str],
    boxes: list[list[int]],
    fields: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """
    Attach a best-effort `box` to each extracted field by matching the field's
    extracted text back onto OCR `words` and unioning the matching word boxes.
    """
    if not words or not boxes or len(words) != len(boxes) or not fields:
        return fields

    norm_words = [_normalize_token(w) for w in words]

    for field_name, payload in (fields or {}).items():
        val = (payload or {}).get("value")
        if not val:
            payload["box"] = None
            continue

        val_toks = [_normalize_token(t) for t in _tokenize(str(val))]
        val_toks = [t for t in val_toks if t]
        if not val_toks:
            payload["box"] = None
            continue

        best_match: Optional[tuple[int, int]] = None  # (start, length)

        # Exact token-sequence match.
        for i in range(0, max(0, len(norm_words) - len(val_toks) + 1)):
            if norm_words[i : i + len(val_toks)] == val_toks:
                best_match = (i, len(val_toks))
                break

        # Fallback: single-token substring match (useful for invoice numbers).
        if best_match is None and len(val_toks) == 1:
            target = val_toks[0]
            for i, w in enumerate(norm_words):
                if target and (target in w or w in target):
                    best_match = (i, 1)
                    break

        if best_match is None:
            payload["box"] = None
            continue

        start, ln = best_match
        payload["box"] = _union_box(boxes[start : start + ln])

    return fields
