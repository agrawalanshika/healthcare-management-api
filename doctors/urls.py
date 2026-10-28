from django.urls import path

from .views import DoctorDetailView, DoctorListCreateView

urlpatterns = [
    path("", DoctorListCreateView.as_view(), name="doctor-list"),
    # <str:pk> so malformed IDs return a JSON 404 from the view.
    path("<str:pk>/", DoctorDetailView.as_view(), name="doctor-detail"),
]
