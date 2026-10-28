from django.contrib import admin

from .models import Doctor, PatientDoctorMapping


@admin.register(Doctor)
class DoctorAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "specialization", "email", "years_of_experience")
    search_fields = ("name", "specialization", "email")


@admin.register(PatientDoctorMapping)
class PatientDoctorMappingAdmin(admin.ModelAdmin):
    list_display = ("id", "patient", "doctor", "assigned_at")
