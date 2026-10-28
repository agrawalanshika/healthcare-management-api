from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from patients.models import Patient

from .models import Doctor, PatientDoctorMapping

User = get_user_model()

URL = "/api/doctors/"
PASSWORD = "Str0ngPass!234"

VALID = {
    "name": "Dr. Test Doctor",
    "specialization": "Cardiology",
    "email": "doctor.one@example.com",
    "phone_number": "+919876543210",
    "years_of_experience": 12,
}


class DoctorBase(APITestCase):
    def setUp(self):
        self.alice = User.objects.create_user(email="alice@example.com", password=PASSWORD, name="Alice")
        self.bob = User.objects.create_user(email="bob@example.com", password=PASSWORD, name="Bob")
        self.as_user(self.alice)

    def as_user(self, user):
        self.client.credentials()
        res = self.client.post(
            "/api/auth/login/", {"email": user.email, "password": PASSWORD}, format="json"
        )
        self.assertEqual(res.status_code, 200)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {res.json()['access']}")

    def make_doctor(self, **overrides):
        return Doctor.objects.create(**{**VALID, **overrides})


class DoctorAuthTests(DoctorBase):
    def test_all_endpoints_require_authentication(self):
        doctor = self.make_doctor()
        self.client.credentials()
        detail = f"{URL}{doctor.id}/"
        self.assertEqual(self.client.get(URL).status_code, 401)
        self.assertEqual(self.client.post(URL, VALID, format="json").status_code, 401)
        self.assertEqual(self.client.get(detail).status_code, 401)
        self.assertEqual(self.client.put(detail, VALID, format="json").status_code, 401)
        self.assertEqual(self.client.delete(detail).status_code, 401)
        self.assertEqual(Doctor.objects.count(), 1)

    def test_invalid_token_rejected(self):
        self.client.credentials(HTTP_AUTHORIZATION="Bearer invalid.token.value")
        self.assertEqual(self.client.get(URL).status_code, 401)


class DoctorCreateTests(DoctorBase):
    def test_create_success(self):
        res = self.client.post(URL, VALID, format="json")
        self.assertEqual(res.status_code, 201)
        body = res.json()
        self.assertEqual(body["name"], VALID["name"])
        self.assertTrue(Doctor.objects.filter(id=body["id"]).exists())

    def test_id_cannot_be_set_by_client(self):
        res = self.client.post(URL, {**VALID, "id": 9999}, format="json")
        self.assertEqual(res.status_code, 201)
        self.assertNotEqual(res.json()["id"], 9999)

    def test_email_normalized_to_lowercase(self):
        res = self.client.post(URL, {**VALID, "email": " Doctor.One@Example.COM "}, format="json")
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.json()["email"], "doctor.one@example.com")

    def test_duplicate_email_rejected_case_insensitive(self):
        self.client.post(URL, VALID, format="json")
        for email in ("doctor.one@example.com", "DOCTOR.ONE@example.com"):
            res = self.client.post(URL, {**VALID, "email": email}, format="json")
            self.assertEqual(res.status_code, 400, email)
            self.assertIn("email", res.json())
        self.assertEqual(Doctor.objects.count(), 1)

    def test_required_fields(self):
        for field in VALID:
            data = {k: v for k, v in VALID.items() if k != field}
            res = self.client.post(URL, data, format="json")
            self.assertEqual(res.status_code, 400, field)
            self.assertIn(field, res.json())
        self.assertEqual(Doctor.objects.count(), 0)

    def test_invalid_values(self):
        cases = {
            "name": ["", "   ", None],
            "specialization": ["", "   "],
            "email": ["not-an-email", "a@", ""],
            "phone_number": ["abc", "123", "+1234567890123456789", ""],
            "years_of_experience": [-1, 71, "abc", 3.5, None],
        }
        for field, values in cases.items():
            for value in values:
                res = self.client.post(URL, {**VALID, field: value}, format="json")
                self.assertEqual(res.status_code, 400, f"{field}={value!r}")
                self.assertIn(field, res.json())
        self.assertEqual(Doctor.objects.count(), 0)

    def test_zero_experience_allowed(self):
        res = self.client.post(URL, {**VALID, "years_of_experience": 0}, format="json")
        self.assertEqual(res.status_code, 201)

    def test_malformed_json_rejected(self):
        res = self.client.post(URL, "{not json", content_type="application/json")
        self.assertEqual(res.status_code, 400)


class DoctorListTests(DoctorBase):
    def test_list_is_shared_across_users(self):
        d1 = self.make_doctor(email="d1@example.com")
        self.as_user(self.bob)
        d2 = self.client.post(URL, {**VALID, "email": "d2@example.com"}, format="json").json()
        self.as_user(self.alice)
        res = self.client.get(URL)
        self.assertEqual(res.status_code, 200)
        self.assertEqual([d["id"] for d in res.json()], [d1.id, d2["id"]])

    def test_list_empty(self):
        res = self.client.get(URL)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), [])


class DoctorDetailTests(DoctorBase):
    def test_retrieve(self):
        d = self.make_doctor()
        res = self.client.get(f"{URL}{d.id}/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["email"], VALID["email"])

    def test_any_authenticated_user_can_retrieve(self):
        d = self.make_doctor()
        self.as_user(self.bob)
        self.assertEqual(self.client.get(f"{URL}{d.id}/").status_code, 200)

    def test_nonexistent_and_malformed_ids_are_json_404(self):
        for bad in ("999999", "abc", "0", "-1", "99999999999999999999", "1.5"):
            for method in ("get", "put", "delete"):
                kwargs = {"format": "json"} if method == "put" else {}
                args = (f"{URL}{bad}/", VALID) if method == "put" else (f"{URL}{bad}/",)
                res = getattr(self.client, method)(*args, **kwargs)
                self.assertEqual(res.status_code, 404, f"{method} {bad}")
                self.assertIn("detail", res.json())

    def test_put_updates_and_persists(self):
        d = self.make_doctor()
        new = {**VALID, "name": "Dr. Renamed", "specialization": "Neurology", "years_of_experience": 20}
        res = self.client.put(f"{URL}{d.id}/", new, format="json")
        self.assertEqual(res.status_code, 200)
        d.refresh_from_db()
        self.assertEqual((d.name, d.specialization, d.years_of_experience), ("Dr. Renamed", "Neurology", 20))

    def test_put_can_keep_own_email(self):
        d = self.make_doctor()
        res = self.client.put(f"{URL}{d.id}/", {**VALID, "name": "Same Email"}, format="json")
        self.assertEqual(res.status_code, 200)

    def test_put_cannot_take_another_doctors_email(self):
        self.make_doctor(email="taken@example.com")
        d = self.make_doctor(email="mine@example.com")
        res = self.client.put(f"{URL}{d.id}/", {**VALID, "email": "TAKEN@example.com"}, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertIn("email", res.json())
        d.refresh_from_db()
        self.assertEqual(d.email, "mine@example.com")

    def test_put_validation(self):
        d = self.make_doctor()
        data = {k: v for k, v in VALID.items() if k != "name"}
        self.assertEqual(self.client.put(f"{URL}{d.id}/", data, format="json").status_code, 400)
        self.assertEqual(
            self.client.put(f"{URL}{d.id}/", {**VALID, "years_of_experience": 500}, format="json").status_code,
            400,
        )

    def test_delete_and_persistence(self):
        d = self.make_doctor()
        self.assertEqual(self.client.delete(f"{URL}{d.id}/").status_code, 204)
        self.assertFalse(Doctor.objects.filter(id=d.id).exists())
        self.assertEqual(self.client.get(f"{URL}{d.id}/").status_code, 404)
        self.assertEqual(self.client.delete(f"{URL}{d.id}/").status_code, 404)

    def test_delete_doctor_removes_its_mappings_not_patients(self):
        d = self.make_doctor()
        patient = Patient.objects.create(
            name="P", age=30, gender="F", contact_number="1234567", address="x", created_by=self.alice
        )
        PatientDoctorMapping.objects.create(patient=patient, doctor=d)
        self.assertEqual(self.client.delete(f"{URL}{d.id}/").status_code, 204)
        self.assertEqual(PatientDoctorMapping.objects.count(), 0)
        self.assertTrue(Patient.objects.filter(id=patient.id).exists())

    def test_unsupported_methods(self):
        d = self.make_doctor()
        self.assertEqual(self.client.patch(f"{URL}{d.id}/", {"name": "x"}, format="json").status_code, 405)
        self.assertEqual(self.client.post(f"{URL}{d.id}/", VALID, format="json").status_code, 405)
        self.assertEqual(self.client.put(URL, VALID, format="json").status_code, 405)
        self.assertEqual(self.client.delete(URL).status_code, 405)
