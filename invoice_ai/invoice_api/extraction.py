import re
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Optional, TypedDict, Literal


_DATE_PATTERNS: list[tuple[str, re.Pattern]] = [
    # 2026-04-17, 2026/04/17
    ("ymd", re.compile(r"\b(20\d{2})\s*[-/]\s*(\d{1,2})\s*[-/]\s*(\d{1,2})\b")),
    # 04/17/2026 or 4-7-2026
    ("mdy", re.compile(r"\b(\d{1,2})\s*[-/]\s*(\d{1,2})\s*[-/]\s*(20\d{2})\b")),
    # Apr 17 2026 / April 17, 2026
    (
        "mon_d_y",
        re.compile(
        r"\b(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|"
        r"Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+(\d{1,2})(?:,)?\s+(20\d{2})\b",
        re.IGNORECASE,
        ),
    ),
]

_INVOICE_NO_PATTERNS = [
    # Invoice No: ABC-123, Invoice #: 1002, Inv No 2026-0001
    re.compile(
        r"\b(?:invoice|inv|bill)\s*(?:number|no|#)\s*[:\-]?\s*([A-Z0-9][A-Z0-9\-\/]{2,})\b",
        re.IGNORECASE,
    ),
    # INV-1001, INV 1001
    re.compile(r"\bINV[\s\-]?(\d{2,})\b", re.IGNORECASE),
    # #ABC-12345 / #12345 / #20260004-A
    re.compile(r"\B#\s*([A-Z0-9][A-Z0-9\-\/]{2,})\b", re.IGNORECASE),
]

_AMOUNT_PATTERNS = [
    # Balance Due: $1,234.56
    re.compile(
        r"\b(?:balance\s+due|amount\s+due|total\s+due|grand\s+total|invoice\s+total|total)\b"
        r"[\s:]*"
        r"(?:USD|US\s*\$|US\$|\$)?\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})|[0-9]+(?:\.[0-9]{2}))\b",
        re.IGNORECASE,
    ),
    # $123.45 near Total
    re.compile(
        r"\b(?:USD|US\$|\$)\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})|[0-9]+(?:\.[0-9]{2}))\b"
    ),
]

_VENDOR_BLACKLIST = {
    "invoice",
    "bill",
    "from",
    "to",
    "ship",
    "shipto",
    "sold",
    "soldto",
    "page",
    "date",
    "total",
    "balance",
    "due",
    "amount",
    "inv",
}


def _normalize_whitespace(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _normalize_amount(raw: str) -> str:
    # Remove commas, keep 2 decimals if present
    s = raw.replace(",", "").strip()
    # If it's an integer-like string, keep as-is
    return s


def _try_parse_date(text: str) -> Optional[str]:
    for kind, pat in _DATE_PATTERNS:
        m = pat.search(text)
        if not m:
            continue
        try:
            if kind == "ymd":
                yyyy, mm, dd = int(m.group(1)), int(m.group(2)), int(m.group(3))
            elif kind == "mon_d_y":
                mon = m.group(1).lower()[:3]
                month_map = {
                    "jan": 1,
                    "feb": 2,
                    "mar": 3,
                    "apr": 4,
                    "may": 5,
                    "jun": 6,
                    "jul": 7,
                    "aug": 8,
                    "sep": 9,
                    "oct": 10,
                    "nov": 11,
                    "dec": 12,
                }
                mm = month_map.get(mon)
                dd = int(m.group(2))
                yyyy = int(m.group(3))
            else:
                mm, dd, yyyy = int(m.group(1)), int(m.group(2)), int(m.group(3))
            dt = datetime(yyyy, mm, dd)
            return dt.strftime("%Y-%m-%d")
        except Exception:
            continue
    return None


def _best_invoice_number(text: str) -> Optional[str]:
    for pat in _INVOICE_NO_PATTERNS:
        m = pat.search(text)
        if m:
            val = m.group(1).strip()
            # very short values are usually false positives
            if len(val) >= 3:
                return val
    return None


def _best_amount(text: str) -> Optional[str]:
    # Prefer "total-like" labels over any $ amount
    for pat in _AMOUNT_PATTERNS:
        m = pat.search(text)
        if m:
            return _normalize_amount(m.group(1))
    return None


class FieldValue(TypedDict):
    value: Optional[str]
    confidence: float
    source: Literal["heuristic"]


def _wrap(value: Optional[str], confidence_if_present: float) -> FieldValue:
    return {
        "value": value,
        "confidence": float(confidence_if_present if value else 0.0),
        "source": "heuristic",
    }


def _best_vendor(words: list[str]) -> Optional[str]:
    """
    Heuristic: vendor is often near the top and is not a label word.
    Given we only get OCR words, choose the earliest plausible "company-ish"
    token sequence.
    """
    cleaned = [w.strip() for w in words if w and w.strip()]
    # drop pure punctuation tokens
    cleaned = [w for w in cleaned if re.search(r"[A-Za-z0-9]", w)]
    # consider only the first ~40 tokens (header region)
    header = cleaned[:40]
    # If we have a "From <vendor>" style, prefer it.
    lowered = [re.sub(r"[^A-Za-z]", "", w).lower() for w in header]
    if "from" in lowered:
        i = lowered.index("from")
        parts: list[str] = []
        for w in header[i + 1 :]:
            key = re.sub(r"[^A-Za-z]", "", w).lower()
            if not key:
                continue
            if key in _VENDOR_BLACKLIST or key in {"inv", "invoice", "bill", "statement", "no", "number"}:
                break
            parts.append(w)
            if len(parts) >= 5:
                break
        cand = _normalize_whitespace(" ".join(parts))
        if cand and "invoice" not in cand.lower():
            return cand

    # Remove obvious labels
    header = [w for w in header if re.sub(r"[^A-Za-z]", "", w).lower() not in _VENDOR_BLACKLIST]
    # Prefer a 2-4 word vendor name with letters
    candidates: list[str] = []
    for i in range(len(header)):
        if not re.search(r"[A-Za-z]", header[i]):
            continue
        parts = [header[i]]
        for j in range(i + 1, min(i + 4, len(header))):
            if re.search(r"[A-Za-z]", header[j]):
                parts.append(header[j])
            else:
                break
        name = _normalize_whitespace(" ".join(parts))
        # Avoid capturing "INVOICE" or similar
        if len(name) >= 3 and name.lower() not in _VENDOR_BLACKLIST and "invoice" not in name.lower():
            candidates.append(name)
    if not candidates:
        return None
    # The earliest candidate is usually the vendor
    return candidates[0]


def extract_fields(words: Iterable[str], boxes: Optional[Iterable[Iterable[int]]] = None) -> dict:
    """
    Extract key invoice fields across many invoice styles.

    Args:
        words: OCR tokens in reading order (best-effort).
        boxes: Optional bounding boxes (unused for now, reserved for future layout-aware logic).
    """
    word_list = list(words) if words is not None else []
    text = _normalize_whitespace(" ".join(word_list))

    # Confidence is heuristic: useful for ranking/UI, not calibrated probability.
    out: dict[str, FieldValue] = {
        "invoice_number": _wrap(_best_invoice_number(text), 0.78),
        "date": _wrap(_try_parse_date(text), 0.72),
        "vendor": _wrap(_best_vendor(word_list), 0.62),
        "amount": _wrap(_best_amount(text), 0.80),
    }
    return out

