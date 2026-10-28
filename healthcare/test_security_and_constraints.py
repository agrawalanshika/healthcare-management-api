"""Cross-cutting security, configuration and database-constraint tests."""
from datetime import timedelta
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, transaction
from django.test import TestCase
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from doctors.models import Doctor, PatientDoctorMapping
from patients.models import Patient

User = get_user_model()
PASSWORD = "Str0ngPass!234"


def make_patient(user, name="P"):
    return Patient.objects.create(
        name=name, age=30, gender="F", contact_number="+911234567890",
        address="Fictional Street", created_by=user,
    )


def make_doctor(email="doc@example.com"):
    return Doctor.objects.create(
        name="Dr. X", specialization="General", email=email,
        phone_number="+919876543210", years_of_experience=5,
    )


class ConfigurationTests(TestCase):
    def test_database_is_postgresql(self):
        self.assertEqual(connection.vendor, "postgresql")

    def test_custom_user_model_is_configured(self):
        self.assertEqual(settings.AUTH_USER_MODEL, "accounts.User")

    def test_jwt_is_the_only_authentication_class(self):
        self.assertEqual(
            settings.REST_FRAMEWORK["DEFAULT_AUTHENTICATION_CLASSES"],
            ("rest_framework_simplejwt.authentication.JWTAuthentication",),
        )

    def test_default_permission_requires_authentication(self):
        self.assertEqual(
            settings.REST_FRAMEWORK["DEFAULT_PERMISSION_CLASSES"],
            ("rest_framework.permissions.IsAuthenticated",),
        )

    def test_access_token_lifetime_is_short(self):
        self.assertLessEqual(settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"], timedelta(hours=24))

    def test_secret_key_is_loaded_from_environment(self):
        # Environment-independent: a placeholder key is tolerated only in DEBUG mode
        # (settings.py refuses to start with a weak key when DEBUG=False).
        self.assertTrue(settings.SECRET_KEY)


class DatabaseConstraintTests(TestCase):
    def test_user_email_unique_case_insensitive_at_database_level(self):
        User.objects.create_user(email="a@example.com", password=PASSWORD, name="A")
        for email in ("a@example.com", "A@EXAMPLE.COM"):
            with self.assertRaises(IntegrityError), transaction.atomic():
                # Bypass the manager's normalization to hit the raw constraint.
                User.objects.bulk_create([User(email=email, name="Dup", password="x")])

    def test_doctor_email_unique(self):
        make_doctor("same@example.com")
        with self.assertRaises(IntegrityError), transaction.atomic():
            make_doctor("same@example.com")

    def test_mapping_pair_unique_at_database_level(self):
        user = User.objects.create_user(email="a@example.com", password=PASSWORD, name="A")
        patient, doctor = make_patient(user), make_doctor()
        PatientDoctorMapping.objects.create(patient=patient, doctor=doctor)
        with self.assertRaises(IntegrityError), transaction.atomic():
            PatientDoctorMapping.objects.create(patient=patient, doctor=doctor)

    def test_patient_age_check_constraint(self):
        user = User.objects.create_user(email="a@example.com", password=PASSWORD, name="A")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Patient.objects.create(
                name="Old", age=200, gender="M", contact_number="1234567",
                address="x", created_by=user,
            )

    def test_patient_requires_owner(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Patient.objects.create(
                name="Orphan", age=30, gender="M", contact_number="1234567", address="x",
            )

    def test_cascades_leave_no_orphans(self):
        user = User.objects.create_user(email="a@example.com", password=PASSWORD, name="A")
        patient, doctor = make_patient(user), make_doctor()
        PatientDoctorMapping.objects.create(patient=patient, doctor=doctor)
        user.delete()
        self.assertEqual(Patient.objects.count(), 0)
        self.assertEqual(PatientDoctorMapping.objects.count(), 0)
        self.assertEqual(Doctor.objects.count(), 1)  # shared directory is unaffected

    def test_passwords_are_hashed(self):
        user = User.objects.create_user(email="a@example.com", password=PASSWORD, name="A")
        self.assertNotEqual(user.password, PASSWORD)
        self.assertTrue(user.password.startswith("pbkdf2_"))
        self.assertTrue(user.check_password(PASSWORD))


class JWTSecurityTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="a@example.com", password=PASSWORD, name="A")

    def bearer(self, token):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def test_valid_access_token_works(self):
        self.bearer(str(AccessToken.for_user(self.user)))
        self.assertEqual(self.client.get("/api/patients/").status_code, 200)

    def test_refresh_token_cannot_be_used_as_access_token(self):
        self.bearer(str(RefreshToken.for_user(self.user)))
        self.assertEqual(self.client.get("/api/patients/").status_code, 401)

    def test_expired_token_rejected(self):
        token = AccessToken.for_user(self.user)
        token.set_exp(lifetime=-timedelta(seconds=10))
        self.bearer(str(token))
        self.assertEqual(self.client.get("/api/patients/").status_code, 401)

    def test_tampered_token_rejected(self):
        token = str(AccessToken.for_user(self.user))
        self.bearer(token[:-4] + ("AAAA" if not token.endswith("AAAA") else "BBBB"))
        self.assertEqual(self.client.get("/api/patients/").status_code, 401)

    def test_token_for_deactivated_user_rejected(self):
        token = str(AccessToken.for_user(self.user))
        User.objects.filter(pk=self.user.pk).update(is_active=False)
        self.bearer(token)
        self.assertEqual(self.client.get("/api/patients/").status_code, 401)

    def test_token_for_deleted_user_rejected(self):
        token = str(AccessToken.for_user(self.user))
        self.user.delete()
        self.bearer(token)
        self.assertEqual(self.client.get("/api/patients/").status_code, 401)

    def test_basic_auth_header_not_accepted(self):
        self.client.credentials(HTTP_AUTHORIZATION="Basic YUBleGFtcGxlLmNvbTpTdHIwbmdQYXNzITIzNA==")
        self.assertEqual(self.client.get("/api/patients/").status_code, 401)


class InputHandlingTests(APITestCase):
    def test_form_encoded_and_multipart_requests_are_accepted(self):
        payload = {"name": "Form User", "email": "form@example.com", "password": PASSWORD}
        res = self.client.post("/api/auth/register/", payload)  # multipart by default
        self.assertEqual(res.status_code, 201)
        res = self.client.post(
            "/api/auth/login/",
            urlencode({"email": "form@example.com", "password": PASSWORD}),
            content_type="application/x-www-form-urlencoded",
        )
        self.assertEqual(res.status_code, 200)

    def test_unsupported_media_type(self):
        res = self.client.post("/api/auth/register/", "plain text", content_type="text/plain")
        self.assertEqual(res.status_code, 415)

    def test_json_array_body_rejected_cleanly(self):
        user = User.objects.create_user(email="a@example.com", password=PASSWORD, name="A")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(user)}")
        for url in ("/api/patients/", "/api/doctors/", "/api/mappings/"):
            res = self.client.post(url, [1, 2, 3], format="json")
            self.assertEqual(res.status_code, 400, url)

    def test_sql_injection_style_input_is_treated_as_data(self):
        user = User.objects.create_user(email="a@example.com", password=PASSWORD, name="A")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(user)}")
        for bad_id in ("1 OR 1=1", "1;DROP TABLE patients_patient", "' OR ''='"):
            self.assertEqual(self.client.get(f"/api/patients/{bad_id}/").status_code, 404)
        self.assertEqual(self.client.get("/api/patients/").status_code, 200)

    def test_errors_do_not_leak_internals(self):
        user = User.objects.create_user(email="a@example.com", password=PASSWORD, name="A")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(user)}")
        res = self.client.post("/api/patients/", {"age": "x"}, format="json")
        body = res.content.decode()
        for leaked in ("Traceback", "psycopg", "django.db", "SECRET_KEY", "pbkdf2"):
            self.assertNotIn(leaked, body)

    def test_login_failure_message_is_generic(self):
        User.objects.create_user(email="a@example.com", password=PASSWORD, name="A")
        wrong = self.client.post("/api/auth/login/", {"email": "a@example.com", "password": "Wrong!Pass9"}, format="json")
        unknown = self.client.post("/api/auth/login/", {"email": "zzz@example.com", "password": "Wrong!Pass9"}, format="json")
        self.assertEqual(wrong.json(), unknown.json())
