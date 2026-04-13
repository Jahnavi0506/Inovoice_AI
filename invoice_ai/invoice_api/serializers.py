from rest_framework import serializers
from .models import Invoice

class InvoiceSerializer(serializers.ModelSerializer):
    file = serializers.FileField()   # ⭐ IMPORTANT

    class Meta:
        model = Invoice
        fields = ['id', 'file', 'uploaded_at']