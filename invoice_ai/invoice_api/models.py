from django.db import models

# Create your models here.
from django.db import models

from django.db import models

class Invoice(models.Model):
    file = models.FileField(upload_to='invoices/')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    # 🔥 NEW FIELDS
    invoice_number = models.CharField(max_length=100, null=True, blank=True)
    date = models.CharField(max_length=50, null=True, blank=True)
    vendor = models.CharField(max_length=200, null=True, blank=True)
    amount = models.CharField(max_length=50, null=True, blank=True)

    def __str__(self):
        return f"Invoice {self.id}"


class InvoiceCorrection(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="corrections")
    field_name = models.CharField(max_length=64)
    original_value = models.TextField(null=True, blank=True)
    corrected_value = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Correction(invoice={self.invoice_id}, field={self.field_name})"