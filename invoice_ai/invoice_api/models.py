from django.db import models


class Invoice(models.Model):
    file = models.FileField(upload_to="invoices/")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    invoice_number = models.CharField(max_length=100, null=True, blank=True)
    date = models.DateField(null=True, blank=True)
    date_raw = models.CharField(max_length=100, null=True, blank=True)
    vendor = models.CharField(max_length=200, null=True, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    amount_raw = models.CharField(max_length=100, null=True, blank=True)

    def __str__(self) -> str:
        return f"Invoice {self.id}"


class InvoiceCorrection(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="corrections")
    field_name = models.CharField(max_length=64)
    original_value = models.TextField(null=True, blank=True)
    corrected_value = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"Correction(invoice={self.invoice_id}, field={self.field_name})"
