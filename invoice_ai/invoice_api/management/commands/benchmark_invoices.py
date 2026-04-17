from pathlib import Path

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Generate multi-format invoice PDFs and benchmark extraction accuracy."

    def add_arguments(self, parser):
        parser.add_argument(
            "--out-dir",
            default=str(Path("bench_data").resolve()),
            help="Directory to write generated PDFs + truth files.",
        )
        parser.add_argument(
            "--formats",
            type=int,
            default=15,
            help="Number of invoice formats (templates) to generate.",
        )

    def handle(self, *args, **opts):
        from invoice_api.bench.runner import run_benchmark

        out_dir = Path(opts["out_dir"])
        formats = int(opts["formats"])
        run_benchmark(out_dir=out_dir, num_formats=formats)

