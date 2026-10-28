from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from patients.models import Patient

from .models import Doctor, PatientDoctorMapping

User = get_user_model()

URL = "/api/mappings/"
PASSWORD = "Str0ngPass!234"


class MappingBase(APITestCase):
    def setUp(self):
        self.alice = User.objects.create_user(email="alice@example.com", password=PASSWORD, name="Alice")
        self.bob = User.objects.create_user(email="bob@example.com", password=PASSWORD, name="Bob")
        self.alice_patient = self.make_patient(self.alice, "Alice Patient")
        self.bob_patient = self.make_patient(self.bob, "Bob Patient")
        self.doc1 = self.make_doctor("d1@example.com")
        self.doc2 = self.make_doctor("d2@example.com")
        self.as_user(self.alice)

    def as_user(self, user):
        self.client.credentials()
        res = self.client.post(
            "/api/auth/login/", {"email": user.email, "password": PASSWORD}, format="json"
        )
        self.assertEqual(res.status_code, 200)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {res.json()['access']}")

    def make_patient(self, user, name):
        return Patient.objects.create(
            name=name, age=40, gender="M", contact_number="+911234567890",
            address="Fictional Street", created_by=user,
        )

    def make_doctor(self, email):
        return Doctor.objects.create(
            name=f"Dr. {email}", specialization="General", email=email,
            phone_number="+919876543210", years_of_experience=5,
        )

    def assign(self, patient, doctor):
        return PatientDoctorMapping.objects.create(patient=patient, doctor=doctor)

    def assign_with_distinct_id(self, patient, doctor):
        """Create a mapping whose id differs from the patient's id (so GET/DELETE semantics are provable)."""
        while True:
            mapping = self.assign(patient, doctor)
            if mapping.id != patient.id:
                return mapping
            mapping.delete()


class MappingAuthTests(MappingBase):
    def test_all_endpoints_require_authentication(self):
        m = self.assign(self.alice_patient, self.doc1)
        self.client.credentials()
        payload = {"patient": self.alice_patient.id, "doctor": self.doc2.id}
        self.assertEqual(self.client.post(URL, payload, format="json").status_code, 401)
        self.assertEqual(self.client.get(URL).status_code, 401)
        self.assertEqual(self.client.get(f"{URL}{self.alice_patient.id}/").status_code, 401)
        self.assertEqual(self.client.delete(f"{URL}{m.id}/").status_code, 401)
        self.assertEqual(PatientDoctorMapping.objects.count(), 1)

    def test_invalid_token_rejected(self):
        self.client.credentials(HTTP_AUTHORIZATION="Bearer invalid.token.value")
        self.assertEqual(self.client.get(URL).status_code, 401)


class MappingCreateTests(MappingBase):
    def test_create_success(self):
        res = self.client.post(
            URL, {"patient": self.alice_patient.id, "doctor": self.doc1.id}, format="json"
        )
        self.assertEqual(res.status_code, 201)
        body = res.json()
        self.assertEqual(body["patient"], self.alice_patient.id)
        self.assertEqual(body["doctor"], self.doc1.id)
        self.assertIn("assigned_at", body)
        self.assertTrue(
            PatientDoctorMapping.objects.filter(
                id=body["id"], patient=self.alice_patient, doctor=self.doc1
            ).exists()
        )

    def test_id_cannot_be_set_by_client(self):
        res = self.client.post(
            URL, {"id": 99999, "patient": self.alice_patient.id, "doctor": self.doc1.id}, format="json"
        )
        self.assertEqual(res.status_code, 201)
        self.assertNotEqual(res.json()["id"], 99999)

    def test_nonexistent_patient(self):
        res = self.client.post(URL, {"patient": 999999, "doctor": self.doc1.id}, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertIn("patient", res.json())

    def test_nonexistent_doctor(self):
        res = self.client.post(URL, {"patient": self.alice_patient.id, "doctor": 999999}, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertIn("doctor", res.json())

    def test_cannot_assign_to_another_users_patient(self):
        res = self.client.post(
            URL, {"patient": self.bob_patient.id, "doctor": self.doc1.id}, format="json"
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("patient", res.json())
        self.assertEqual(PatientDoctorMapping.objects.count(), 0)

    def test_missing_fields(self):
        for missing in ("patient", "doctor"):
            data = {"patient": self.alice_patient.id, "doctor": self.doc1.id}
            data.pop(missing)
            res = self.client.post(URL, data, format="json")
            self.assertEqual(res.status_code, 400, missing)
            self.assertIn(missing, res.json())
        self.assertEqual(self.client.post(URL, {}, format="json").status_code, 400)

    def test_invalid_types(self):
        for bad in ("abc", 1.5, True, None, [1], {"a": 1}, 99999999999999999999, -1, 0):
            for field in ("patient", "doctor"):
                data = {"patient": self.alice_patient.id, "doctor": self.doc1.id, field: bad}
                res = self.client.post(URL, data, format="json")
                self.assertEqual(res.status_code, 400, f"{field}={bad!r}")
                self.assertIn(field, res.json())
        self.assertEqual(PatientDoctorMapping.objects.count(), 0)

    def test_duplicate_assignment_rejected(self):
        payload = {"patient": self.alice_patient.id, "doctor": self.doc1.id}
        self.assertEqual(self.client.post(URL, payload, format="json").status_code, 201)
        res = self.client.post(URL, payload, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertIn("non_field_errors", res.json())
        self.assertEqual(PatientDoctorMapping.objects.count(), 1)

    def test_same_doctor_for_multiple_patients_and_multiple_doctors_per_patient(self):
        p2 = self.make_patient(self.alice, "Alice Patient 2")
        for patient, doctor in (
            (self.alice_patient, self.doc1),
            (self.alice_patient, self.doc2),
            (p2, self.doc1),
        ):
            res = self.client.post(URL, {"patient": patient.id, "doctor": doctor.id}, format="json")
            self.assertEqual(res.status_code, 201)

    def test_shared_doctor_usable_by_other_user_for_own_patient(self):
        self.client.post(URL, {"patient": self.alice_patient.id, "doctor": self.doc1.id}, format="json")
        self.as_user(self.bob)
        res = self.client.post(URL, {"patient": self.bob_patient.id, "doctor": self.doc1.id}, format="json")
        self.assertEqual(res.status_code, 201)

    def test_malformed_json_rejected(self):
        res = self.client.post(URL, "{not json", content_type="application/json")
        self.assertEqual(res.status_code, 400)


class MappingListTests(MappingBase):
    def test_list_returns_only_mappings_of_own_patients(self):
        mine = self.assign(self.alice_patient, self.doc1)
        self.assign(self.bob_patient, self.doc2)
        res = self.client.get(URL)
        self.assertEqual(res.status_code, 200)
        self.assertEqual([m["id"] for m in res.json()], [mine.id])
        row = res.json()[0]
        self.assertEqual(set(row), {"id", "patient", "patient_name", "doctor", "doctor_name", "assigned_at"})

    def test_list_empty(self):
        self.assertEqual(self.client.get(URL).json(), [])


class MappingByPatientTests(MappingBase):
    def test_returns_doctors_assigned_to_patient(self):
        m1 = self.assign_with_distinct_id(self.alice_patient, self.doc1)
        self.assign(self.alice_patient, self.doc2)
        res = self.client.get(f"{URL}{self.alice_patient.id}/")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(len(body), 2)
        self.assertEqual(body[0]["mapping_id"], m1.id)
        self.assertEqual(body[0]["doctor"]["id"], self.doc1.id)
        self.assertEqual(body[0]["doctor"]["email"], "d1@example.com")
        self.assertEqual({b["doctor"]["id"] for b in body}, {self.doc1.id, self.doc2.id})

    def test_patient_without_doctors_returns_empty_list(self):
        res = self.client.get(f"{URL}{self.alice_patient.id}/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), [])

    def test_get_interprets_identifier_as_patient_id_not_mapping_id(self):
        mapping = self.assign_with_distinct_id(self.alice_patient, self.doc1)
        # Using the MAPPING id in GET must NOT return that patient's doctors.
        res = self.client.get(f"{URL}{mapping.id}/")
        if Patient.objects.filter(id=mapping.id, created_by=self.alice).exists():
            self.assertNotEqual(res.json(), self.client.get(f"{URL}{self.alice_patient.id}/").json())
        else:
            self.assertEqual(res.status_code, 404)

    def test_other_users_patient_is_404(self):
        self.assign(self.bob_patient, self.doc1)
        self.assertEqual(self.client.get(f"{URL}{self.bob_patient.id}/").status_code, 404)

    def test_nonexistent_and_malformed_ids_are_json_404(self):
        for bad in ("999999", "abc", "0", "-1", "99999999999999999999", "1.5"):
            res = self.client.get(f"{URL}{bad}/")
            self.assertEqual(res.status_code, 404, bad)
            self.assertIn("detail", res.json())


class MappingDeleteTests(MappingBase):
    def test_delete_by_mapping_id(self):
        m = self.assign_with_distinct_id(self.alice_patient, self.doc1)
        res = self.client.delete(f"{URL}{m.id}/")
        self.assertEqual(res.status_code, 204)
        self.assertFalse(PatientDoctorMapping.objects.filter(id=m.id).exists())
        # Patient and doctor are untouched.
        self.assertTrue(Patient.objects.filter(id=self.alice_patient.id).exists())
        self.assertTrue(Doctor.objects.filter(id=self.doc1.id).exists())
        # No longer appears anywhere.
        self.assertEqual(self.client.get(URL).json(), [])
        self.assertEqual(self.client.get(f"{URL}{self.alice_patient.id}/").json(), [])
        self.assertEqual(self.client.delete(f"{URL}{m.id}/").status_code, 404)

    def test_delete_treats_identifier_as_mapping_id_not_patient_id(self):
        m = self.assign_with_distinct_id(self.alice_patient, self.doc1)
        PatientDoctorMapping.objects.filter(id=self.alice_patient.id).delete()
        res = self.client.delete(f"{URL}{self.alice_patient.id}/")  # patient id, not a mapping id
        self.assertEqual(res.status_code, 404)
        self.assertTrue(PatientDoctorMapping.objects.filter(id=m.id).exists())
        self.assertTrue(Patient.objects.filter(id=self.alice_patient.id).exists())

    def test_cannot_delete_other_users_mapping(self):
        m = self.assign(self.bob_patient, self.doc1)
        self.assertEqual(self.client.delete(f"{URL}{m.id}/").status_code, 404)
        self.assertTrue(PatientDoctorMapping.objects.filter(id=m.id).exists())

    def test_nonexistent_and_malformed_ids_are_json_404(self):
        for bad in ("999999", "abc", "0", "-1", "99999999999999999999", "1.5"):
            res = self.client.delete(f"{URL}{bad}/")
            self.assertEqual(res.status_code, 404, bad)
            self.assertIn("detail", res.json())

    def test_can_reassign_after_delete(self):
        payload = {"patient": self.alice_patient.id, "doctor": self.doc1.id}
        first = self.client.post(URL, payload, format="json").json()
        self.assertEqual(self.client.delete(f"{URL}{first['id']}/").status_code, 204)
        self.assertEqual(self.client.post(URL, payload, format="json").status_code, 201)

    def test_deleting_patient_via_api_removes_its_mappings(self):
        self.assign(self.alice_patient, self.doc1)
        self.assertEqual(self.client.delete(f"/api/patients/{self.alice_patient.id}/").status_code, 204)
        self.assertEqual(PatientDoctorMapping.objects.count(), 0)
        self.assertTrue(Doctor.objects.filter(id=self.doc1.id).exists())

    def test_unsupported_methods(self):
        m = self.assign(self.alice_patient, self.doc1)
        detail = f"{URL}{m.id}/"
        self.assertEqual(self.client.put(detail, {}, format="json").status_code, 405)
        self.assertEqual(self.client.patch(detail, {}, format="json").status_code, 405)
        self.assertEqual(self.client.post(detail, {}, format="json").status_code, 405)
        self.assertEqual(self.client.put(URL, {}, format="json").status_code, 405)
        self.assertEqual(self.client.patch(URL, {}, format="json").status_code, 405)
        self.assertEqual(self.client.delete(URL).status_code, 405)
