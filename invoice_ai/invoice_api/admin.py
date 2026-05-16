from django.contrib import admin

from .models import Invoice, InvoiceCorrection


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ("id", "uploaded_at", "invoice_number", "date", "vendor", "amount")
    list_filter = ("uploaded_at",)
    search_fields = ("invoice_number", "vendor", "amount_raw", "date_raw")


@admin.register(InvoiceCorrection)
class InvoiceCorrectionAdmin(admin.ModelAdmin):
    list_display = ("id", "invoice", "field_name", "created_at")
    list_filter = ("field_name", "created_at")
