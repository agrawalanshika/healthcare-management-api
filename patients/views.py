from rest_framework.generics import ListCreateAPIView, RetrieveUpdateDestroyAPIView
from rest_framework.permissions import IsAuthenticated

from .models import Patient
from .serializers import PatientSerializer


class OwnedPatientQuerysetMixin:
    """Restrict every query to patients created by the authenticated user.

    Records owned by other users are simply not in the queryset, so they
    return 404 (their existence is not revealed).
    """

    permission_classes = [IsAuthenticated]
    serializer_class = PatientSerializer

    def get_queryset(self):
        return Patient.objects.filter(created_by=self.request.user).order_by("id")


class PatientListCreateView(OwnedPatientQuerysetMixin, ListCreateAPIView):
    http_method_names = ["get", "post", "head", "options"]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class PatientDetailView(OwnedPatientQuerysetMixin, RetrieveUpdateDestroyAPIView):
    # PATCH is intentionally not exposed: the assignment specifies PUT only.
    http_method_names = ["get", "put", "delete", "head", "options"]
