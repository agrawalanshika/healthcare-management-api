from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import include, path
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.test import APITestCase
from rest_framework.views import APIView

User = get_user_model()


class ProtectedProbeView(APIView):
    """Test-only view used to prove JWT authentication works."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({"email": request.user.email})


# Test-only URLconf: real auth routes + one protected probe route.
urlpatterns = [
    path("api/auth/", include("accounts.urls")),
    path("probe/", ProtectedProbeView.as_view()),
]

REGISTER_URL = "/api/auth/register/"
LOGIN_URL = "/api/auth/login/"
VALID = {"name": "Alice Test", "email": "alice@example.com", "password": "Str0ngPass!234"}


@override_settings(ROOT_URLCONF="accounts.tests")
class RegistrationTests(APITestCase):
    def test_register_success(self):
        res = self.client.post(REGISTER_URL, VALID, format="json")
        self.assertEqual(res.status_code, 201)
        self.assertEqual(set(res.json().keys()), {"id", "name", "email"})
        self.assertNotIn("password", res.content.decode())
        user = User.objects.get(email="alice@example.com")
        self.assertNotEqual(user.password, VALID["password"])
        self.assertTrue(user.password.startswith("pbkdf2_"))
        self.assertTrue(user.check_password(VALID["password"]))

    def test_email_is_normalized(self):
        data = {**VALID, "email": "  Alice@Example.COM "}
        res = self.client.post(REGISTER_URL, data, format="json")
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.json()["email"], "alice@example.com")

    def test_missing_fields(self):
        for field in ("name", "email", "password"):
            data = {k: v for k, v in VALID.items() if k != field}
            res = self.client.post(REGISTER_URL, data, format="json")
            self.assertEqual(res.status_code, 400, field)
            self.assertIn(field, res.json())

    def test_blank_name_rejected(self):
        res = self.client.post(REGISTER_URL, {**VALID, "name": "   "}, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertIn("name", res.json())

    def test_invalid_email_rejected(self):
        res = self.client.post(REGISTER_URL, {**VALID, "email": "not-an-email"}, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertIn("email", res.json())

    def test_weak_password_rejected(self):
        for weak in ("short1", "12345678", "password"):
            res = self.client.post(REGISTER_URL, {**VALID, "password": weak}, format="json")
            self.assertEqual(res.status_code, 400, weak)
            self.assertIn("password", res.json())

    def test_duplicate_email_rejected(self):
        self.client.post(REGISTER_URL, VALID, format="json")
        for email in ("alice@example.com", "ALICE@example.com"):
            res = self.client.post(REGISTER_URL, {**VALID, "email": email}, format="json")
            self.assertEqual(res.status_code, 400, email)
            self.assertIn("email", res.json())
        self.assertEqual(User.objects.count(), 1)

    def test_non_string_values_rejected(self):
        res = self.client.post(REGISTER_URL, {**VALID, "name": {"a": 1}}, format="json")
        self.assertEqual(res.status_code, 400)

    def test_register_ignores_invalid_token(self):
        res = self.client.post(
            REGISTER_URL, VALID, format="json", HTTP_AUTHORIZATION="Bearer garbage"
        )
        self.assertEqual(res.status_code, 201)


@override_settings(ROOT_URLCONF="accounts.tests")
class LoginAndJWTTests(APITestCase):
    def setUp(self):
        User.objects.create_user(
            email="alice@example.com", password=VALID["password"], name="Alice Test"
        )

    def login(self, email="alice@example.com", password=VALID["password"]):
        return self.client.post(LOGIN_URL, {"email": email, "password": password}, format="json")

    def test_login_success_returns_access_token(self):
        res = self.login()
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertIn("access", body)
        self.assertNotIn("password", res.content.decode())
        self.assertEqual(body["user"]["email"], "alice@example.com")

    def test_login_email_case_insensitive(self):
        self.assertEqual(self.login(email="ALICE@Example.com").status_code, 200)

    def test_access_token_grants_access(self):
        token = self.login().json()["access"]
        res = self.client.get("/probe/", HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["email"], "alice@example.com")

    def test_wrong_password_fails_safely(self):
        res = self.login(password="WrongPass!999")
        self.assertEqual(res.status_code, 401)
        self.assertNotIn("access", res.json())

    def test_unknown_user_gets_same_error_as_wrong_password(self):
        wrong_pw = self.login(password="WrongPass!999")
        unknown = self.login(email="nobody@example.com")
        self.assertEqual(unknown.status_code, 401)
        self.assertEqual(wrong_pw.json(), unknown.json())

    def test_login_missing_fields(self):
        res = self.client.post(LOGIN_URL, {"email": "alice@example.com"}, format="json")
        self.assertEqual(res.status_code, 400)
        res = self.client.post(LOGIN_URL, {"password": "x"}, format="json")
        self.assertEqual(res.status_code, 400)

    def test_inactive_user_cannot_login(self):
        User.objects.filter(email="alice@example.com").update(is_active=False)
        self.assertEqual(self.login().status_code, 401)

    def test_protected_route_requires_token(self):
        self.assertEqual(self.client.get("/probe/").status_code, 401)

    def test_protected_route_rejects_invalid_token(self):
        res = self.client.get("/probe/", HTTP_AUTHORIZATION="Bearer not.a.token")
        self.assertEqual(res.status_code, 401)

    def test_protected_route_rejects_wrong_scheme(self):
        token = self.login().json()["access"]
        res = self.client.get("/probe/", HTTP_AUTHORIZATION=f"Token {token}")
        self.assertEqual(res.status_code, 401)
