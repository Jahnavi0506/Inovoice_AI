from django.urls import path
from .views import (
    UploadInvoiceView,
    UploadInvoicePageView,
    InvoiceExportJsonView,
    InvoiceExportCsvView,
    InvoiceErpExportSimulateView,
    DashboardPageView,
    DashboardStatsApiView,
)

urlpatterns = [
    path('upload/', UploadInvoiceView.as_view()),
    path('upload-page/', UploadInvoicePageView.as_view()),
    path("invoice/<int:invoice_id>/export/json/", InvoiceExportJsonView.as_view()),
    path("invoice/<int:invoice_id>/export/csv/", InvoiceExportCsvView.as_view()),
    path("invoice/<int:invoice_id>/export/erp/simulate/", InvoiceErpExportSimulateView.as_view()),
    path("dashboard/", DashboardStatsApiView.as_view()),
    path("dashboard-page/", DashboardPageView.as_view()),
]