from django.core.validators import MaxValueValidator
from django.db import models

from healthcare.validators import phone_validator
from patients.models import Patient


class Doctor(models.Model):
    name = models.CharField(max_length=150)
    specialization = models.CharField(max_length=150)
    email = models.EmailField(unique=True)
    phone_number = models.CharField(max_length=20, validators=[phone_validator])
    years_of_experience = models.PositiveSmallIntegerField(
        validators=[MaxValueValidator(70)]
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.name} ({self.specialization})"


class PatientDoctorMapping(models.Model):
    patient = models.ForeignKey(
        Patient,
        on_delete=models.CASCADE,
        related_name="doctor_mappings",
    )
    doctor = models.ForeignKey(
        Doctor,
        on_delete=models.CASCADE,
        related_name="patient_mappings",
    )
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=["patient", "doctor"], name="unique_patient_doctor_mapping"
            ),
        ]

    def __str__(self):
        return f"Patient #{self.patient_id} -> Doctor #{self.doctor_id}"
