from django.apps import AppConfig
import os


class InvoiceApiConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'invoice_api'

    def ready(self):
        # Django runserver uses a reloader that imports apps twice; only warm up in the
        # "real" process to avoid duplicate HF downloads.
        if os.environ.get("RUN_MAIN") not in {"true", "1", "True"}:
            return

        if os.environ.get("INVOICEAI_WARMUP_LAYOUTLM", "1") not in {"1", "true", "True", "yes", "YES"}:
            return

        try:
            from .layoutlm_utils import warmup_layoutlm

            warmup_layoutlm()
        except Exception:
            # Warmup is best-effort; extraction will still work (heuristic fallback).
            return
