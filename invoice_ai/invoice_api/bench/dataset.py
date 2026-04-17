from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class InvoiceTruth:
    invoice_number: str
    date: str  # normalized YYYY-MM-DD
    vendor: str
    amount: str


@dataclass(frozen=True)
class InvoiceCase:
    format_id: str
    pdf_path: Path
    truth: InvoiceTruth


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def generate_dataset(root: Path, *, num_formats: int = 15) -> list[InvoiceCase]:
    """
    Generate a diverse invoice PDF dataset without committing binaries.

    Writes:
      - PDFs:  <root>/pdfs/<format_id>/*.pdf
      - Truth: <root>/truth/<format_id>.jsonl
    """
    try:
        from reportlab.lib.pagesizes import LETTER
        from reportlab.pdfgen import canvas
    except Exception as e:  # pragma: no cover
        raise RuntimeError(
            "Missing dependency 'reportlab'. Install it to generate benchmark PDFs."
        ) from e

    pdf_dir = root / "pdfs"
    truth_dir = root / "truth"
    _ensure_dir(pdf_dir)
    _ensure_dir(truth_dir)

    formats: list[str] = [f"format_{i:02d}" for i in range(1, num_formats + 1)]
    cases: list[InvoiceCase] = []

    for idx, fmt in enumerate(formats, start=1):
        fmt_pdf_dir = pdf_dir / fmt
        _ensure_dir(fmt_pdf_dir)

        # 1 case per format (keeps runtime fast but covers many layouts)
        inv_no = f"{2026}{idx:04d}-A"
        date = f"2026-04-{(idx % 28) + 1:02d}"
        vendor = [
            "Northwind Traders LLC",
            "Contoso Services Inc",
            "Fabrikam Supplies Co",
            "Adventure Works",
            "Tailspin Toys",
            "Woodgrove Bank",
            "Alpine Ski House",
            "Blue Yonder Airlines",
            "Wide World Importers",
            "Proseware Studio",
            "Coho Vineyard",
            "Litware Retail",
            "Lucerne Publishing",
            "A. Datum Corporation",
            "Fourth Coffee",
            "City Power & Light",
        ][(idx - 1) % 16]
        amount = f"{(1000 + idx * 37):.2f}"

        pdf_path = fmt_pdf_dir / f"{fmt}.pdf"

        c = canvas.Canvas(str(pdf_path), pagesize=LETTER)
        width, height = LETTER

        # Template variations (labels, positions, punctuation, date formats, currency)
        if idx % 5 == 1:
            # Classic: Invoice No / Date / Total Due
            c.setFont("Helvetica-Bold", 20)
            c.drawString(40, height - 60, "INVOICE")
            c.setFont("Helvetica", 12)
            c.drawString(40, height - 90, f"From: {vendor}")
            c.drawString(40, height - 120, f"Invoice No: {inv_no}")
            c.drawString(40, height - 140, f"Date: {date}")
            c.drawString(40, height - 170, f"Total Due: ${amount}")
        elif idx % 5 == 2:
            # INV #, mm/dd/yyyy, Balance Due
            mm, dd, yyyy = date.split("-")[1], date.split("-")[2], date.split("-")[0]
            c.setFont("Helvetica-Bold", 16)
            c.drawString(40, height - 60, vendor)
            c.setFont("Helvetica-Bold", 20)
            c.drawString(40, height - 95, "Invoice")
            c.setFont("Helvetica", 12)
            c.drawString(40, height - 125, f"INV #: {inv_no}")
            c.drawString(40, height - 145, f"Invoice Date: {mm}/{dd}/{yyyy}")
            c.drawString(40, height - 175, f"Balance Due: US$ {amount}")
        elif idx % 5 == 3:
            # Bill Number, yyyy/mm/dd, Grand Total
            yyyy, mm, dd = date.split("-")
            c.setFont("Helvetica-Bold", 22)
            c.drawString(40, height - 60, "Tax Invoice")
            c.setFont("Helvetica", 12)
            c.drawString(40, height - 95, f"{vendor}")
            c.drawString(40, height - 125, f"Bill No - {inv_no}")
            c.drawString(40, height - 145, f"Bill Date: {yyyy}/{mm}/{dd}")
            c.drawString(40, height - 175, f"Grand Total : ${amount}")
        elif idx % 5 == 4:
            # #12345 style, Month dd, yyyy, Total
            import calendar

            yyyy, mm, dd = date.split("-")
            month_name = calendar.month_abbr[int(mm)]
            c.setFont("Helvetica-Bold", 18)
            c.drawString(40, height - 60, vendor)
            c.setFont("Helvetica-Bold", 18)
            c.drawString(width - 200, height - 60, "INVOICE")
            c.setFont("Helvetica", 12)
            c.drawString(40, height - 110, f"#{inv_no}")
            c.drawString(40, height - 130, f"{month_name} {int(dd)} {yyyy}")
            c.drawString(40, height - 170, f"Total: ${amount}")
        else:
            # Invoice number keyword, date with dashes, Invoice Total
            c.setFont("Helvetica-Bold", 20)
            c.drawString(40, height - 60, vendor)
            c.setFont("Helvetica", 12)
            c.drawString(40, height - 95, "INVOICE STATEMENT")
            c.drawString(40, height - 125, f"Invoice Number - {inv_no}")
            c.drawString(40, height - 145, f"Date Issued - {date}")
            c.drawString(40, height - 175, f"Invoice Total: $ {amount}")

        c.showPage()
        c.save()

        truth = InvoiceTruth(
            invoice_number=inv_no,
            date=date,
            vendor=vendor,
            amount=amount,
        )

        cases.append(InvoiceCase(format_id=fmt, pdf_path=pdf_path, truth=truth))

    # Persist truth per format (jsonl, one invoice per line)
    by_format: dict[str, list[InvoiceCase]] = {}
    for cse in cases:
        by_format.setdefault(cse.format_id, []).append(cse)

    for fmt, fmt_cases in by_format.items():
        truth_path = truth_dir / f"{fmt}.jsonl"
        with truth_path.open("w", encoding="utf-8") as f:
            for cse in fmt_cases:
                f.write(
                    json.dumps(
                        {
                            "pdf_path": str(cse.pdf_path),
                            "truth": {
                                "invoice_number": cse.truth.invoice_number,
                                "date": cse.truth.date,
                                "vendor": cse.truth.vendor,
                                "amount": cse.truth.amount,
                            },
                        }
                    )
                    + "\n"
                )

    return cases

