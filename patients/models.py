from django.conf import settings
from django.core.validators import MaxValueValidator
from django.db import models

from healthcare.validators import phone_validator


class Patient(models.Model):
    class Gender(models.TextChoices):
        MALE = "M", "Male"
        FEMALE = "F", "Female"
        OTHER = "O", "Other"

    name = models.CharField(max_length=150)
    age = models.PositiveSmallIntegerField(validators=[MaxValueValidator(150)])
    gender = models.CharField(max_length=1, choices=Gender.choices)
    contact_number = models.CharField(max_length=20, validators=[phone_validator])
    address = models.TextField()
    medical_history = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="patients",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(age__lte=150), name="patient_age_lte_150"
            ),
        ]

    def __str__(self):
        return f"{self.name} (#{self.pk})"
