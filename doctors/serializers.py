from django.db import IntegrityError
from rest_framework import serializers

from patients.models import Patient

from .models import Doctor, PatientDoctorMapping

DUPLICATE_MAPPING_MESSAGE = "This doctor is already assigned to this patient."


class DoctorSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(max_length=254)

    class Meta:
        model = Doctor
        fields = (
            "id",
            "name",
            "specialization",
            "email",
            "phone_number",
            "years_of_experience",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def validate_email(self, value):
        email = value.strip().lower()
        duplicates = Doctor.objects.filter(email__iexact=email)
        if self.instance is not None:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists():
            raise serializers.ValidationError("A doctor with this email already exists.")
        return email

    def _duplicate_email_error(self):
        return serializers.ValidationError(
            {"email": ["A doctor with this email already exists."]}
        )

    def create(self, validated_data):
        try:
            return super().create(validated_data)
        except IntegrityError:  # race-condition safety net (DB unique constraint)
            raise self._duplicate_email_error()

    def update(self, instance, validated_data):
        try:
            return super().update(instance, validated_data)
        except IntegrityError:
            raise self._duplicate_email_error()


class MappingSerializer(serializers.ModelSerializer):
    """Create / list representation of a patient-doctor assignment."""

    patient = serializers.PrimaryKeyRelatedField(
        queryset=Patient.objects.none(),  # narrowed to the caller's patients in __init__
        error_messages={
            "does_not_exist": "Patient does not exist or you do not have access to it.",
            "incorrect_type": "Patient must be a valid patient ID (integer).",
        },
    )
    doctor = serializers.PrimaryKeyRelatedField(
        queryset=Doctor.objects.all(),
        error_messages={
            "does_not_exist": "Doctor does not exist.",
            "incorrect_type": "Doctor must be a valid doctor ID (integer).",
        },
    )
    patient_name = serializers.CharField(source="patient.name", read_only=True)
    doctor_name = serializers.CharField(source="doctor.name", read_only=True)

    class Meta:
        model = PatientDoctorMapping
        fields = ("id", "patient", "patient_name", "doctor", "doctor_name", "assigned_at")
        read_only_fields = ("id", "assigned_at")
        validators = []  # duplicate check is explicit in validate() for a clear message

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request is not None and request.user.is_authenticated:
            # Only the caller's own patients can be referenced.
            self.fields["patient"].queryset = Patient.objects.filter(created_by=request.user)

    def validate(self, attrs):
        if PatientDoctorMapping.objects.filter(
            patient=attrs["patient"], doctor=attrs["doctor"]
        ).exists():
            raise serializers.ValidationError(
                {"non_field_errors": [DUPLICATE_MAPPING_MESSAGE]}
            )
        return attrs

    def create(self, validated_data):
        try:
            return super().create(validated_data)
        except IntegrityError:  # race-condition safety net (DB unique constraint)
            raise serializers.ValidationError(
                {"non_field_errors": [DUPLICATE_MAPPING_MESSAGE]}
            )


class AssignedDoctorSerializer(serializers.ModelSerializer):
    """Representation used by GET /api/mappings/<patient_id>/."""

    mapping_id = serializers.IntegerField(source="id", read_only=True)
    doctor = DoctorSerializer(read_only=True)

    class Meta:
        model = PatientDoctorMapping
        fields = ("mapping_id", "doctor", "assigned_at")
