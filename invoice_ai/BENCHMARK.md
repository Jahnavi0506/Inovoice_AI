## Multi-Invoice Intelligence Benchmark

This repo includes a **generated** dataset of diverse invoice PDF templates (no binary PDFs committed) and a benchmark that scores the extractor against ground truth.

### Install deps

```bash
python -m pip install -r requirements.txt
```

### Run benchmark (creates 10–20 PDFs automatically)

Generates PDFs + truth into `bench_data/` and prints overall + per-format accuracy:

```bash
python manage.py benchmark_invoices --formats 15
```

Example output:

- `Accuracy: 80% across 15 invoice formats`

