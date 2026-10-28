from django.urls import path

from .views import PatientDetailView, PatientListCreateView

urlpatterns = [
    path("", PatientListCreateView.as_view(), name="patient-list"),
    # <str:pk> (not <int:pk>) so malformed IDs return a JSON 404 from the view
    # instead of an HTML URL-resolver 404.
    path("<str:pk>/", PatientDetailView.as_view(), name="patient-detail"),
]
