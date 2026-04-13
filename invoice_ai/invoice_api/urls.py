from django.urls import path
from .views import UploadInvoiceView, UploadInvoicePageView

urlpatterns = [
    path('upload/', UploadInvoiceView.as_view()),
    path('upload-page/', UploadInvoicePageView.as_view()),
]