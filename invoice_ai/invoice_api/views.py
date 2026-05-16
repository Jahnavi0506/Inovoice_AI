import csv
import io
from typing import Any, Optional

from django.db.models import Avg
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from .layoutlm_utils import extract_fields
from .models import Invoice, InvoiceCorrection
from .parsing import apply_extracted_fields_to_invoice, parse_amount_raw, parse_date_raw
from .serializers import InvoiceSerializer
from .utils import assign_field_boxes, blur_score, extract_ocr_data, load_invoice_preview, pil_to_data_uri


def _invoice_form_strings(invoice: Invoice) -> dict[str, str]:
    return {
        "invoice_number": invoice.invoice_number or "",
        "date": invoice.date.isoformat()
        if invoice.date
        else (invoice.date_raw or ""),
        "vendor": invoice.vendor or "",
        "amount": str(invoice.amount)
        if invoice.amount is not None
        else (invoice.amount_raw or ""),
    }


def _invoice_edit_snapshot(invoice: Invoice) -> dict[str, Optional[str]]:
    return {
        "invoice_number": invoice.invoice_number,
        "vendor": invoice.vendor,
        "date": invoice.date_raw or (invoice.date.isoformat() if invoice.date else None),
        "amount": invoice.amount_raw
        or (str(invoice.amount) if invoice.amount is not None else None),
    }


def _apply_invoice_form_post(invoice: Invoice, post: Any) -> None:
    invoice.invoice_number = (post.get("invoice_number") or "").strip() or None
    invoice.vendor = (post.get("vendor") or "").strip() or None

    date_s = (post.get("date") or "").strip() or None
    invoice.date_raw = date_s
    parsed_d, _ = parse_date_raw(date_s)
    invoice.date = parsed_d

    amt_s = (post.get("amount") or "").strip() or None
    invoice.amount_raw = amt_s
    parsed_a, _ = parse_amount_raw(amt_s)
    invoice.amount = parsed_a


class UploadInvoiceView(APIView):
    parser_classes = [MultiPartParser, FormParser]
    serializer_class = InvoiceSerializer

    def post(self, request):
        serializer = self.serializer_class(data=request.data)

        if not serializer.is_valid():
            return Response(serializer.errors, status=400)

        invoice = serializer.save()

        words, boxes, image = extract_ocr_data(invoice.file.path)

        fields = extract_fields(words, boxes=boxes, image=image)
        fields = assign_field_boxes(words=list(words), boxes=list(boxes), fields=fields)

        apply_extracted_fields_to_invoice(invoice, fields)
        invoice.save()

        out = InvoiceSerializer(invoice)
        return Response(
            {
                "data": out.data,
                "words": words[:10],
                "boxes": boxes[:10],
                "extracted_fields": fields,
            }
        )


class UploadInvoicePageView(APIView):
    def get(self, request):
        inv_id = request.GET.get("invoice_id")
        if inv_id:
            invoice = get_object_or_404(Invoice, pk=inv_id)
            image = load_invoice_preview(invoice.file.path)
            return render(
                request,
                "upload.html",
                {
                    "data": invoice,
                    "fields": _invoice_form_strings(invoice),
                    "fields_raw": {},
                    "preview_data_uri": pil_to_data_uri(image),
                    "preview_w": image.size[0],
                    "preview_h": image.size[1],
                    "warnings": [],
                },
            )
        return render(request, "upload.html")

    def post(self, request):
        if "invoice_id" in request.POST:
            invoice = get_object_or_404(Invoice, pk=request.POST["invoice_id"])

            before = _invoice_edit_snapshot(invoice)
            _apply_invoice_form_post(invoice, request.POST)
            after = _invoice_edit_snapshot(invoice)

            for field_name in ("invoice_number", "date", "vendor", "amount"):
                b = before.get(field_name)
                a = after.get(field_name)
                if (b or None) != (a or None):
                    InvoiceCorrection.objects.create(
                        invoice=invoice,
                        field_name=field_name,
                        original_value=b,
                        corrected_value=a,
                    )

            invoice.save()
            return redirect(f"{request.path}?invoice_id={invoice.id}")

        file = request.FILES.get("file")

        if file:
            invoice = Invoice.objects.create(file=file)

            words, boxes, image = extract_ocr_data(invoice.file.path)
            fields = extract_fields(words, boxes=boxes, image=image)
            fields = assign_field_boxes(words=list(words), boxes=list(boxes), fields=fields)

            warnings: list[str] = []
            try:
                score = blur_score(image)
                if score < 70.0:
                    warnings.append("Blurry image detected — extraction may be inaccurate.")
            except Exception:
                pass

            if not words:
                warnings.append("No text detected — please upload a clearer image/PDF.")

            present = sum(
                1
                for k in ["invoice_number", "date", "vendor", "amount"]
                if (fields.get(k) or {}).get("value")
            )
            if present <= 2 and words:
                warnings.append("Partial extraction — some fields were not found.")

            low_conf_fields = [
                k
                for k in ["invoice_number", "date", "vendor", "amount"]
                if float((fields.get(k) or {}).get("confidence") or 0.0) < 0.70
                and (fields.get(k) or {}).get("value")
            ]
            if low_conf_fields:
                warnings.append("Low confidence — please verify highlighted fields.")

            apply_extracted_fields_to_invoice(invoice, fields)
            invoice.save()

            return render(
                request,
                "upload.html",
                {
                    "data": invoice,
                    "fields": {k: (v or {}).get("value") for k, v in (fields or {}).items()},
                    "fields_raw": fields,
                    "preview_data_uri": pil_to_data_uri(image),
                    "preview_w": image.size[0] if image else None,
                    "preview_h": image.size[1] if image else None,
                    "warnings": warnings,
                },
            )

        return render(request, "upload.html")


class InvoiceExportJsonView(APIView):
    def get(self, request, invoice_id: int):
        invoice = get_object_or_404(Invoice, pk=invoice_id)
        payload = {
            "id": invoice.id,
            "uploaded_at": invoice.uploaded_at.isoformat() if invoice.uploaded_at else None,
            "invoice_number": invoice.invoice_number,
            "date": invoice.date.isoformat() if invoice.date else None,
            "date_raw": invoice.date_raw,
            "vendor": invoice.vendor,
            "amount": str(invoice.amount) if invoice.amount is not None else None,
            "amount_raw": invoice.amount_raw,
        }
        resp = JsonResponse(payload, json_dumps_params={"indent": 2})
        resp["Content-Disposition"] = f'attachment; filename="invoice_{invoice.id}.json"'
        return resp


class InvoiceExportCsvView(APIView):
    def get(self, request, invoice_id: int):
        invoice = get_object_or_404(Invoice, pk=invoice_id)
        out = io.StringIO()
        w = csv.writer(out)
        w.writerow(
            [
                "id",
                "uploaded_at",
                "invoice_number",
                "date",
                "date_raw",
                "vendor",
                "amount",
                "amount_raw",
            ]
        )
        w.writerow(
            [
                invoice.id,
                invoice.uploaded_at.isoformat() if invoice.uploaded_at else "",
                invoice.invoice_number or "",
                invoice.date.isoformat() if invoice.date else "",
                invoice.date_raw or "",
                invoice.vendor or "",
                str(invoice.amount) if invoice.amount is not None else "",
                invoice.amount_raw or "",
            ]
        )
        resp = HttpResponse(out.getvalue(), content_type="text/csv")
        resp["Content-Disposition"] = f'attachment; filename="invoice_{invoice.id}.csv"'
        return resp


class InvoiceErpExportSimulateView(APIView):
    def post(self, request, invoice_id: int):
        invoice = get_object_or_404(Invoice, pk=invoice_id)
        erp_payload = {
            "target": request.data.get("target") or request.POST.get("target") or "SAP",
            "documentType": "INVOICE",
            "companyCode": "IN",
            "vendorName": invoice.vendor,
            "invoiceNo": invoice.invoice_number,
            "invoiceDate": invoice.date.isoformat() if invoice.date else invoice.date_raw,
            "currency": "INR",
            "amount": str(invoice.amount) if invoice.amount is not None else invoice.amount_raw,
            "sourceInvoiceId": invoice.id,
        }
        return Response({"status": "SIMULATED_EXPORT_OK", "erp_payload": erp_payload})


class DashboardPageView(APIView):
    def get(self, request):
        total = Invoice.objects.count()

        avg_amount = (
            Invoice.objects.filter(amount__isnull=False).aggregate(v=Avg("amount")).get("v")
        )

        vendors = (
            Invoice.objects.exclude(vendor__isnull=True)
            .exclude(vendor__exact="")
            .values("vendor")
            .distinct()
            .count()
        )

        return render(
            request,
            "dashboard.html",
            {
                "total_invoices": total,
                "avg_amount": avg_amount,
                "vendors_detected": vendors,
            },
        )


class DashboardStatsApiView(APIView):
    def get(self, request):
        total = Invoice.objects.count()
        avg_amount = (
            Invoice.objects.filter(amount__isnull=False).aggregate(v=Avg("amount")).get("v")
        )
        vendors = (
            Invoice.objects.exclude(vendor__isnull=True)
            .exclude(vendor__exact="")
            .values("vendor")
            .distinct()
            .count()
        )
        return Response(
            {
                "total_invoices_processed": total,
                "average_amount_inr": float(avg_amount) if avg_amount is not None else None,
                "vendors_detected": vendors,
            }
        )
