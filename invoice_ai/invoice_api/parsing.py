from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Optional


_DATE_FORMATS: tuple[str, ...] = (
    "%Y-%m-%d",
    "%d-%m-%Y",
    "%d/%m/%Y",
    "%m/%d/%Y",
    "%d %b %Y",
    "%d %B %Y",
    "%b %d %Y",
    "%B %d %Y",
)


def parse_amount_raw(raw: str | None) -> tuple[Optional[Decimal], Optional[str]]:
    """Return (parsed Decimal or None, normalized raw string for storage)."""
    if raw is None:
        return None, None
    s = str(raw).strip()
    if not s:
        return None, None
    m = re.search(r"[-+]?\d[\d,]*(?:\.\d+)?", s)
    if not m:
        return None, s
    token = m.group(0).replace(",", "")
    try:
        return Decimal(token), s
    except (InvalidOperation, ValueError):
        return None, s


def parse_date_raw(raw: str | None) -> tuple[Optional[date], Optional[str]]:
    """Return (parsed date or None, original trimmed string for storage)."""
    if raw is None:
        return None, None
    s = str(raw).strip()
    if not s:
        return None, None
    s_norm = re.sub(r"\s+", " ", s)
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s_norm, fmt).date(), s
        except ValueError:
            continue
    m = re.search(r"(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})", s_norm)
    if m:
        d1, d2, y = m.group(1), m.group(2), m.group(3)
        if len(y) == 2:
            y = "20" + y
        for fmt in ("%d/%m/%Y", "%m/%d/%Y"):
            try:
                return datetime.strptime(f"{d1}/{d2}/{y}", fmt).date(), s
            except ValueError:
                continue
    return None, s


def coalesce_extracted_value(fields: dict[str, Any], key: str) -> Optional[str]:
    v = (fields.get(key) or {}).get("value")
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def apply_extracted_fields_to_invoice(invoice: Any, fields: dict[str, Any]) -> None:
    """Populate typed + raw columns from the extractor output. Caller calls save()."""
    invoice.invoice_number = coalesce_extracted_value(fields, "invoice_number")
    invoice.vendor = coalesce_extracted_value(fields, "vendor")

    date_s = coalesce_extracted_value(fields, "date")
    invoice.date_raw = date_s
    parsed_date, _ = parse_date_raw(date_s)
    invoice.date = parsed_date

    amount_s = coalesce_extracted_value(fields, "amount")
    invoice.amount_raw = amount_s
    parsed_amt, _ = parse_amount_raw(amount_s)
    invoice.amount = parsed_amt
