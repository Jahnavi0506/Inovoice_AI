from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from .models import Invoice
from .serializers import InvoiceSerializer
from .utils import extract_ocr_data
from .layoutlm_utils import extract_fields
from django.shortcuts import render, redirect
from .models import Invoice
from .utils import extract_ocr_data
from .layoutlm_utils import extract_fields

class UploadInvoiceView(APIView):
    parser_classes = [MultiPartParser, FormParser]
    serializer_class = InvoiceSerializer

    def post(self, request):
        print("FILES:", request.FILES)

        serializer = self.serializer_class(data=request.data)

        if serializer.is_valid():
            invoice = serializer.save()

            # OCR
            words, boxes = extract_ocr_data(invoice.file.path)

            # Extract fields
            fields = extract_fields(words)

            # 🔥 ADD THIS BLOCK HERE
            invoice.invoice_number = fields["invoice_number"]
            invoice.date = fields["date"]
            invoice.vendor = fields["vendor"]
            invoice.amount = fields["amount"]
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

            invoice.invoice_number = request.POST["invoice_number"]
            invoice.date = request.POST["date"]
            invoice.vendor = request.POST["vendor"]
            invoice.amount = request.POST["amount"]
            invoice.save()

            return redirect(request.path)

        # 🔹 If uploading file
        file = request.FILES.get("file")

        if file:
            invoice = Invoice.objects.create(file=file)

            words, boxes = extract_ocr_data(invoice.file.path)
            fields = extract_fields(words)

            # save to DB
            invoice.invoice_number = fields["invoice_number"]
            invoice.date = fields["date"]
            invoice.vendor = fields["vendor"]
            invoice.amount = fields["amount"]
            invoice.save()

            return render(request, 'upload.html', {
                "data": invoice,
                "fields": fields
            })

        return render(request, 'upload.html')