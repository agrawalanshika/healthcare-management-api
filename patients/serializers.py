from rest_framework import serializers

from .models import Patient


class PatientSerializer(serializers.ModelSerializer):
    class Meta:
        model = Patient
        fields = (
            "id",
            "name",
            "age",
            "gender",
            "contact_number",
            "address",
            "medical_history",
            "created_by",
            "created_at",
            "updated_at",
        )
        # Ownership and server-generated fields can never be set by the client.
        read_only_fields = ("id", "created_by", "created_at", "updated_at")
