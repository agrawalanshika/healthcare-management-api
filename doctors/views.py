from rest_framework import status
from rest_framework.generics import (
    ListCreateAPIView,
    RetrieveUpdateDestroyAPIView,
    get_object_or_404,
)
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from patients.models import Patient

from .models import Doctor, PatientDoctorMapping
from .serializers import AssignedDoctorSerializer, DoctorSerializer, MappingSerializer


# --- Doctors -----------------------------------------------------------------
class DoctorListCreateView(ListCreateAPIView):
    """Shared doctor directory: any authenticated user can list and create."""

    queryset = Doctor.objects.all().order_by("id")
    serializer_class = DoctorSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "head", "options"]


class DoctorDetailView(RetrieveUpdateDestroyAPIView):
    """Any authenticated user can retrieve, update or delete a doctor (per the assignment)."""

    queryset = Doctor.objects.all().order_by("id")
    serializer_class = DoctorSerializer
    permission_classes = [IsAuthenticated]
    # PATCH is intentionally not exposed: the assignment specifies PUT only.
    http_method_names = ["get", "put", "delete", "head", "options"]


# --- Patient-doctor mappings -------------------------------------------------
class MappingListCreateView(ListCreateAPIView):
    """POST: assign a doctor to one of your patients.
    GET: list the mappings of the patients you own."""

    serializer_class = MappingSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        return (
            PatientDoctorMapping.objects.filter(patient__created_by=self.request.user)
            .select_related("patient", "doctor")
            .order_by("id")
        )


class MappingDetailView(APIView):
    """One URL shape, two meanings, decided by the HTTP method:

    GET    /api/mappings/<id>/  -> <id> is a PATIENT id; returns the doctors assigned to it.
    DELETE /api/mappings/<id>/  -> <id> is a MAPPING id; removes that assignment.
    """

    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "delete", "head", "options"]

    def get(self, request, pk):
        patient = get_object_or_404(Patient.objects.filter(created_by=request.user), pk=pk)
        mappings = (
            PatientDoctorMapping.objects.filter(patient=patient)
            .select_related("doctor")
            .order_by("id")
        )
        return Response(AssignedDoctorSerializer(mappings, many=True).data)

    def delete(self, request, pk):
        mapping = get_object_or_404(
            PatientDoctorMapping.objects.filter(patient__created_by=request.user), pk=pk
        )
        mapping.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
