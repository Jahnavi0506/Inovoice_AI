from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path

from invoice_api.extraction import extract_fields
from invoice_api.bench.dataset import generate_dataset


def _norm(s: str | None) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


def _norm_amount(s: str | None) -> str:
    if not s:
        return ""
    return s.replace(",", "").strip()


def _pred_field_value(pred: dict, field: str) -> str | None:
    v = pred.get(field)
    if isinstance(v, dict):
        inner = v.get("value")
        return None if inner is None else str(inner)
    return None if v is None else str(v)


@dataclass(frozen=True)
class Score:
    correct: int
    total: int

    @property
    def pct(self) -> float:
        return 0.0 if self.total == 0 else (100.0 * self.correct / self.total)


def _extract_text_from_pdf(pdf_path: Path) -> str:
    try:
        from pypdf import PdfReader
    except Exception as e:  # pragma: no cover
        raise RuntimeError("Missing dependency 'pypdf'. Install it to run benchmark.") from e

    reader = PdfReader(str(pdf_path))
    out = []
    for page in reader.pages:
        out.append(page.extract_text() or "")
    return "\n".join(out)


def _tokenize_for_parser(text: str) -> list[str]:
    # mimic OCR-ish tokens to reuse extract_fields(words)
    return re.findall(
        r"\d{1,2}[-/]\d{1,2}[-/]20\d{2}|"  # m/d/y dates
        r"20\d{2}[-/]\d{1,2}[-/]\d{1,2}|"  # y/m/d dates
        r"[A-Za-z0-9]+(?:[-/][A-Za-z0-9]+)+|"  # ids like 20260002-A
        r"\d+(?:,\d{3})*(?:\.\d{2})?|"  # amounts / numbers
        r"[A-Za-z0-9]+|"  # words
        r"US\$|USD|\$|[-/]|[#,.:]",
        text,
    )


def run_benchmark(*, out_dir: Path, num_formats: int) -> int:
    cases = generate_dataset(out_dir, num_formats=num_formats)

    overall_correct = 0
    overall_total = 0
    per_format: dict[str, Score] = {}

    for cse in cases:
        text = _extract_text_from_pdf(cse.pdf_path)
        words = _tokenize_for_parser(text)
        pred = extract_fields(words)

        fields = ["invoice_number", "date", "vendor", "amount"]
        correct = 0
        for f in fields:
            pred_val = _pred_field_value(pred, f)
            if f == "amount":
                ok = _norm_amount(pred_val) == _norm_amount(getattr(cse.truth, f))
            else:
                ok = _norm(pred_val) == _norm(getattr(cse.truth, f))
            correct += 1 if ok else 0

        total = len(fields)
        overall_correct += correct
        overall_total += total

        prev = per_format.get(cse.format_id, Score(0, 0))
        per_format[cse.format_id] = Score(prev.correct + correct, prev.total + total)

    overall = Score(overall_correct, overall_total)

    print(f"Accuracy: {overall.pct:.0f}% across {num_formats} invoice formats")
    print("")
    for fmt in sorted(per_format.keys()):
        s = per_format[fmt]
        print(f"- {fmt}: {s.pct:.0f}% ({s.correct}/{s.total} fields)")

    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default=str(Path("bench_data").resolve()))
    ap.add_argument("--formats", type=int, default=15)
    args = ap.parse_args()

    return run_benchmark(out_dir=Path(args.out_dir), num_formats=args.formats)


if __name__ == "__main__":
    raise SystemExit(main())

