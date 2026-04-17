from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from .models import Invoice
from .models import InvoiceCorrection
from .serializers import InvoiceSerializer
from .utils import extract_ocr_data, pil_to_data_uri, blur_score, assign_field_boxes
from .layoutlm_utils import extract_fields
from django.shortcuts import render, redirect
from django.http import HttpResponse, JsonResponse
import csv
import io
import json
from django.db.models import Avg, Count
from django.db.models.functions import Cast
from django.db.models import FloatField

class UploadInvoiceView(APIView):
    parser_classes = [MultiPartParser, FormParser]
    serializer_class = InvoiceSerializer

    def post(self, request):
        print("FILES:", request.FILES)

        serializer = self.serializer_class(data=request.data)

        if serializer.is_valid():
            invoice = serializer.save()

            # OCR
            words, boxes, image = extract_ocr_data(invoice.file.path)

            # Extract fields
            fields = extract_fields(words, boxes=boxes, image=image)
            fields = assign_field_boxes(words=list(words), boxes=list(boxes), fields=fields)

            # 🔥 ADD THIS BLOCK HERE
            invoice.invoice_number = (fields.get("invoice_number") or {}).get("value")
            invoice.date = (fields.get("date") or {}).get("value")
            invoice.vendor = (fields.get("vendor") or {}).get("value")
            invoice.amount = (fields.get("amount") or {}).get("value")
            invoice.save()

            return Response({
                "data": serializer.data,
                "words": words[:10],
                "boxes": boxes[:10],
                "extracted_fields": fields
            })

class UploadInvoicePageView(APIView):

    def get(self, request):
        return render(request, 'upload.html')

    def post(self, request):

        # 🔹 If saving edited data
        if "invoice_id" in request.POST:
            invoice = Invoice.objects.get(id=request.POST["invoice_id"])

            updates = {
                "invoice_number": request.POST.get("invoice_number") or None,
                "date": request.POST.get("date") or None,
                "vendor": request.POST.get("vendor") or None,
                "amount": request.POST.get("amount") or None,
            }

            # Human-in-the-loop: store corrections when users edit extracted values.
            for field_name, new_val in updates.items():
                old_val = getattr(invoice, field_name, None)
                if (old_val or None) != (new_val or None):
                    InvoiceCorrection.objects.create(
                        invoice=invoice,
                        field_name=field_name,
                        original_value=old_val,
                        corrected_value=new_val,
                    )
                setattr(invoice, field_name, new_val)
            invoice.save()

            return redirect(request.path)

        # 🔹 If uploading file
        file = request.FILES.get("file")

        if file:
            invoice = Invoice.objects.create(file=file)

            words, boxes, image = extract_ocr_data(invoice.file.path)
            fields = extract_fields(words, boxes=boxes, image=image)
            fields = assign_field_boxes(words=list(words), boxes=list(boxes), fields=fields)

            # ----- Error handling / warnings -----
            warnings: list[str] = []
            try:
                score = blur_score(image)
                if score < 70.0:
                    warnings.append("Blurry image detected — extraction may be inaccurate.")
            except Exception:
                pass

            if not words:
                warnings.append("No text detected — please upload a clearer image/PDF.")

            present = sum(1 for k in ["invoice_number", "date", "vendor", "amount"] if (fields.get(k) or {}).get("value"))
            if present <= 2 and words:
                warnings.append("Partial extraction — some fields were not found.")

            low_conf_fields = [
                k
                for k in ["invoice_number", "date", "vendor", "amount"]
                if float((fields.get(k) or {}).get("confidence") or 0.0) < 0.70 and (fields.get(k) or {}).get("value")
            ]
            if low_conf_fields:
                warnings.append("Low confidence — please verify highlighted fields.")

            # save to DB
            invoice.invoice_number = (fields.get("invoice_number") or {}).get("value")
            invoice.date = (fields.get("date") or {}).get("value")
            invoice.vendor = (fields.get("vendor") or {}).get("value")
            invoice.amount = (fields.get("amount") or {}).get("value")
            invoice.save()

            return render(request, 'upload.html', {
                "data": invoice,
                # Keep the template simple: pass plain strings for the form,
                # but also include the rich objects if you want to display confidence later.
                "fields": {k: (v or {}).get("value") for k, v in (fields or {}).items()},
                "fields_raw": fields,
                "preview_data_uri": pil_to_data_uri(image),
                "preview_w": image.size[0] if image else None,
                "preview_h": image.size[1] if image else None,
                "warnings": warnings,
            })

        return render(request, 'upload.html')


class InvoiceExportJsonView(APIView):
    def get(self, request, invoice_id: int):
        invoice = Invoice.objects.get(id=invoice_id)
        payload = {
            "id": invoice.id,
            "uploaded_at": invoice.uploaded_at.isoformat() if invoice.uploaded_at else None,
            "invoice_number": invoice.invoice_number,
            "date": invoice.date,
            "vendor": invoice.vendor,
            "amount": invoice.amount,
        }
        resp = JsonResponse(payload, json_dumps_params={"indent": 2})
        resp["Content-Disposition"] = f'attachment; filename="invoice_{invoice.id}.json"'
        return resp


class InvoiceExportCsvView(APIView):
    def get(self, request, invoice_id: int):
        invoice = Invoice.objects.get(id=invoice_id)
        out = io.StringIO()
        w = csv.writer(out)
        w.writerow(["id", "uploaded_at", "invoice_number", "date", "vendor", "amount"])
        w.writerow(
            [
                invoice.id,
                invoice.uploaded_at.isoformat() if invoice.uploaded_at else "",
                invoice.invoice_number or "",
                invoice.date or "",
                invoice.vendor or "",
                invoice.amount or "",
            ]
        )
        resp = HttpResponse(out.getvalue(), content_type="text/csv")
        resp["Content-Disposition"] = f'attachment; filename="invoice_{invoice.id}.csv"'
        return resp


class InvoiceErpExportSimulateView(APIView):
    def post(self, request, invoice_id: int):
        """
        Simulated ERP export payload (SAP/Excel style).
        """
        invoice = Invoice.objects.get(id=invoice_id)
        erp_payload = {
            "target": request.data.get("target") or request.POST.get("target") or "SAP",
            "documentType": "INVOICE",
            "companyCode": "IN",
            "vendorName": invoice.vendor,
            "invoiceNo": invoice.invoice_number,
            "invoiceDate": invoice.date,
            "currency": "INR",
            "amount": invoice.amount,
            "sourceInvoiceId": invoice.id,
        }
        # In a real integration this would push to SAP/Excel; we return a preview.
        return Response({"status": "SIMULATED_EXPORT_OK", "erp_payload": erp_payload})


class DashboardPageView(APIView):
    def get(self, request):
        # Lightweight stats for demo dashboard
        total = Invoice.objects.count()

        # Amounts are stored as strings; best-effort average.
        avg_amount = (
            Invoice.objects.exclude(amount__isnull=True)
            .exclude(amount__exact="")
            .annotate(amount_f=Cast("amount", FloatField()))
            .aggregate(v=Avg("amount_f"))
            .get("v")
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
            Invoice.objects.exclude(amount__isnull=True)
            .exclude(amount__exact="")
            .annotate(amount_f=Cast("amount", FloatField()))
            .aggregate(v=Avg("amount_f"))
            .get("v")
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
                "average_amount_inr": avg_amount,
                "vendors_detected": vendors,
            }
        )