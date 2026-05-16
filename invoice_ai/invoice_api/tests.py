from datetime import date
from decimal import Decimal

from django.test import TestCase

from invoice_api.parsing import apply_extracted_fields_to_invoice, parse_amount_raw, parse_date_raw
from invoice_api.models import Invoice


class ParsingTests(TestCase):
    def test_parse_date_iso(self) -> None:
        d, raw = parse_date_raw("2026-04-18")
        self.assertEqual(d, date(2026, 4, 18))
        self.assertEqual(raw, "2026-04-18")

    def test_parse_amount_currency(self) -> None:
        a, raw = parse_amount_raw("Total: $1,234.56 USD")
        self.assertEqual(a, Decimal("1234.56"))
        self.assertEqual(raw, "Total: $1,234.56 USD")

    def test_apply_extracted_fields(self) -> None:
        inv = Invoice()
        fields = {
            "invoice_number": {"value": "INV-001", "confidence": 0.9},
            "date": {"value": "2026-01-15", "confidence": 0.8},
            "vendor": {"value": "Acme Corp", "confidence": 0.7},
            "amount": {"value": "99.50", "confidence": 0.85},
        }
        apply_extracted_fields_to_invoice(inv, fields)
        self.assertEqual(inv.invoice_number, "INV-001")
        self.assertEqual(inv.date, date(2026, 1, 15))
        self.assertEqual(inv.date_raw, "2026-01-15")
        self.assertEqual(inv.vendor, "Acme Corp")
        self.assertEqual(inv.amount, Decimal("99.50"))
        self.assertEqual(inv.amount_raw, "99.50")
