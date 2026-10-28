from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from .models import Patient

User = get_user_model()

URL = "/api/patients/"
PASSWORD = "Str0ngPass!234"

VALID = {
    "name": "Test Patient",
    "age": 34,
    "gender": "F",
    "contact_number": "+911234567890",
    "address": "12 Fictional Street, Testville",
    "medical_history": "No known allergies",
}


class PatientBase(APITestCase):
    def setUp(self):
        self.alice = User.objects.create_user(email="alice@example.com", password=PASSWORD, name="Alice")
        self.bob = User.objects.create_user(email="bob@example.com", password=PASSWORD, name="Bob")
        self.as_user(self.alice)

    def as_user(self, user):
        """Authenticate through the real login endpoint to exercise JWT end to end."""
        self.client.credentials()
        res = self.client.post(
            "/api/auth/login/", {"email": user.email, "password": PASSWORD}, format="json"
        )
        self.assertEqual(res.status_code, 200)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {res.json()['access']}")

    def make_patient(self, user, **overrides):
        data = {**VALID, **overrides}
        return Patient.objects.create(created_by=user, **data)


class PatientAuthTests(PatientBase):
    def test_all_endpoints_require_authentication(self):
        patient = self.make_patient(self.alice)
        self.client.credentials()
        detail = f"{URL}{patient.id}/"
        self.assertEqual(self.client.get(URL).status_code, 401)
        self.assertEqual(self.client.post(URL, VALID, format="json").status_code, 401)
        self.assertEqual(self.client.get(detail).status_code, 401)
        self.assertEqual(self.client.put(detail, VALID, format="json").status_code, 401)
        self.assertEqual(self.client.delete(detail).status_code, 401)

    def test_invalid_token_rejected(self):
        self.client.credentials(HTTP_AUTHORIZATION="Bearer invalid.token.value")
        self.assertEqual(self.client.get(URL).status_code, 401)


class PatientCreateTests(PatientBase):
    def test_create_success_sets_owner(self):
        res = self.client.post(URL, VALID, format="json")
        self.assertEqual(res.status_code, 201)
        body = res.json()
        self.assertEqual(body["created_by"], self.alice.id)
        self.assertEqual(body["name"], VALID["name"])
        self.assertTrue(Patient.objects.filter(id=body["id"], created_by=self.alice).exists())

    def test_owner_cannot_be_set_via_payload(self):
        res = self.client.post(
            URL, {**VALID, "created_by": self.bob.id, "id": 9999}, format="json"
        )
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.json()["created_by"], self.alice.id)
        self.assertNotEqual(res.json()["id"], 9999)
        self.assertEqual(Patient.objects.filter(created_by=self.bob).count(), 0)

    def test_medical_history_is_optional(self):
        data = {k: v for k, v in VALID.items() if k != "medical_history"}
        res = self.client.post(URL, data, format="json")
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.json()["medical_history"], "")

    def test_required_fields(self):
        for field in ("name", "age", "gender", "contact_number", "address"):
            data = {k: v for k, v in VALID.items() if k != field}
            res = self.client.post(URL, data, format="json")
            self.assertEqual(res.status_code, 400, field)
            self.assertIn(field, res.json())
        self.assertEqual(Patient.objects.count(), 0)

    def test_invalid_values(self):
        cases = {
            "age": [-1, 151, "abc", 12.5, None, True],
            "gender": ["X", "", "male"],
            "contact_number": ["abc", "123", "+1234567890123456789", ""],
            "name": ["", "   ", None],
            "address": ["", "   "],
        }
        for field, values in cases.items():
            for value in values:
                res = self.client.post(URL, {**VALID, field: value}, format="json")
                self.assertEqual(res.status_code, 400, f"{field}={value!r}")
                self.assertIn(field, res.json())
        self.assertEqual(Patient.objects.count(), 0)

    def test_malformed_json_rejected(self):
        res = self.client.post(URL, "{not json", content_type="application/json")
        self.assertEqual(res.status_code, 400)


class PatientListTests(PatientBase):
    def test_list_returns_only_own_patients(self):
        mine = self.make_patient(self.alice, name="Mine")
        self.make_patient(self.bob, name="Bobs")
        res = self.client.get(URL)
        self.assertEqual(res.status_code, 200)
        ids = [p["id"] for p in res.json()]
        self.assertEqual(ids, [mine.id])

    def test_list_empty(self):
        res = self.client.get(URL)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), [])


class PatientDetailTests(PatientBase):
    def test_retrieve_own(self):
        p = self.make_patient(self.alice)
        res = self.client.get(f"{URL}{p.id}/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["id"], p.id)

    def test_retrieve_other_users_patient_is_404(self):
        p = self.make_patient(self.bob)
        self.assertEqual(self.client.get(f"{URL}{p.id}/").status_code, 404)

    def test_nonexistent_and_malformed_ids_are_json_404(self):
        for bad in ("999999", "abc", "0", "-1", "99999999999999999999", "1.5"):
            res = self.client.get(f"{URL}{bad}/")
            self.assertEqual(res.status_code, 404, bad)
            self.assertIn("detail", res.json(), bad)

    def test_put_updates_own_and_persists(self):
        p = self.make_patient(self.alice)
        new = {**VALID, "name": "Renamed", "age": 40, "gender": "M"}
        res = self.client.put(f"{URL}{p.id}/", new, format="json")
        self.assertEqual(res.status_code, 200)
        p.refresh_from_db()
        self.assertEqual((p.name, p.age, p.gender), ("Renamed", 40, "M"))
        self.assertEqual(p.created_by, self.alice)

    def test_put_cannot_change_owner(self):
        p = self.make_patient(self.alice)
        res = self.client.put(
            f"{URL}{p.id}/", {**VALID, "created_by": self.bob.id}, format="json"
        )
        self.assertEqual(res.status_code, 200)
        p.refresh_from_db()
        self.assertEqual(p.created_by, self.alice)

    def test_put_other_users_patient_is_404_and_unchanged(self):
        p = self.make_patient(self.bob, name="Original")
        res = self.client.put(f"{URL}{p.id}/", {**VALID, "name": "Hacked"}, format="json")
        self.assertEqual(res.status_code, 404)
        p.refresh_from_db()
        self.assertEqual(p.name, "Original")

    def test_put_validation(self):
        p = self.make_patient(self.alice)
        data = {k: v for k, v in VALID.items() if k != "name"}
        self.assertEqual(self.client.put(f"{URL}{p.id}/", data, format="json").status_code, 400)
        self.assertEqual(
            self.client.put(f"{URL}{p.id}/", {**VALID, "age": 500}, format="json").status_code, 400
        )

    def test_delete_own(self):
        p = self.make_patient(self.alice)
        res = self.client.delete(f"{URL}{p.id}/")
        self.assertEqual(res.status_code, 204)
        self.assertFalse(Patient.objects.filter(id=p.id).exists())
        self.assertEqual(self.client.delete(f"{URL}{p.id}/").status_code, 404)

    def test_delete_other_users_patient_is_404_and_kept(self):
        p = self.make_patient(self.bob)
        self.assertEqual(self.client.delete(f"{URL}{p.id}/").status_code, 404)
        self.assertTrue(Patient.objects.filter(id=p.id).exists())

    def test_second_user_isolated_both_directions(self):
        a = self.make_patient(self.alice, name="A")
        self.as_user(self.bob)
        self.assertEqual(self.client.get(f"{URL}{a.id}/").status_code, 404)
        self.assertEqual(self.client.get(URL).json(), [])

    def test_unsupported_methods(self):
        p = self.make_patient(self.alice)
        self.assertEqual(self.client.patch(f"{URL}{p.id}/", {"name": "x"}, format="json").status_code, 405)
        self.assertEqual(self.client.post(f"{URL}{p.id}/", VALID, format="json").status_code, 405)
        self.assertEqual(self.client.put(URL, VALID, format="json").status_code, 405)
        self.assertEqual(self.client.delete(URL).status_code, 405)
