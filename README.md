# 📑 Healthcare Backend API

A secure healthcare backend built for the WhatBytes Full Stack Intern assignment. Users can register, log in, and manage patient records, a shared doctor directory, and patient-to-doctor assignments. Authentication uses JWT, and all data is stored in PostgreSQL.

## 🛠️ Technology stack

- Python 3.10+ (developed and tested on 3.12 and 3.13)
- Django 5.2 (LTS) and Django REST Framework
- PostgreSQL (via `psycopg` 3) with the Django ORM
- `djangorestframework-simplejwt` for JWT authentication
- `python-dotenv` for environment variables

## 📌 Features

- Registration (name, email, password) and login that returns a JWT access token
- Patient CRUD, private to the user who created each patient
- Doctor CRUD in a shared directory (any authenticated user)
- Patient-doctor mappings with a database-level duplicate constraint
- Serializer validation, consistent JSON errors, and no leakage of internals
- 115 automated tests, a Postman collection, and a terminal smoke-test script

## 📂 Project structure

```text
manage.py
requirements.txt
.env.example            # placeholders only; copy to .env
healthcare/             # project: settings, root urls, shared validators, security tests
accounts/               # custom email-based User model, register and login
patients/               # Patient model and API
doctors/                # Doctor and PatientDoctorMapping models and APIs
postman/                # Postman collection
scripts/smoke_test.py   # end-to-end check using only the standard library
```

## 🔗 Prerequisites

- Python 3.10 or newer
- PostgreSQL 14 or newer, with `psql` available
- Git (optional)

## ⚙️ Installation

All commands run from the project folder.

### 1. Create and activate a virtual environment

```text
python -m venv .venv
```

Activate it:

| Shell | Command |
|---|---|
| Windows Command Prompt | `.venv\Scripts\activate.bat` |
| Windows PowerShell | `.venv\Scripts\Activate.ps1` |
| Git Bash / macOS / Linux | `source .venv/Scripts/activate` (Git Bash) or `source .venv/bin/activate` |

### 2. Install dependencies

```text
pip install -r requirements.txt
```

### 3. Create the PostgreSQL database

Open `psql` as a superuser (for example `psql -U postgres -h localhost`) and run, choosing your own password:

```sql
CREATE USER healthcare_user WITH PASSWORD 'choose-a-password' CREATEDB;
CREATE DATABASE healthcare_db OWNER healthcare_user;
```

`CREATEDB` lets Django create its temporary test database when you run the tests.

### 4. Configure environment variables

Copy the template, then edit the new `.env`:

```text
copy .env.example .env        (Windows Command Prompt)
cp .env.example .env          (macOS, Linux, Git Bash)
```

| Variable | Meaning |
|---|---|
| `SECRET_KEY` | Django secret key. Generate one with the command below. |
| `DEBUG` | `True` for local development, `False` otherwise. |
| `ALLOWED_HOSTS` | Comma-separated hosts, e.g. `127.0.0.1,localhost`. |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD` | The database and user created in step 3. |
| `DB_HOST`, `DB_PORT` | Usually `localhost` and `5432`. |

Generate a secret key:

```text
python -c "from django.core.management.utils import get_random_secret_key as g; print(g())"
```

`.env` is listed in `.gitignore` and must never be committed. With `DEBUG=False` the app refuses to start if `SECRET_KEY` is a placeholder or shorter than 32 characters.

### 5. Apply migrations

```text
python manage.py migrate
```

### 6. Run the development server

```text
python manage.py runserver
```

The API is served at `http://127.0.0.1:8000/`. Optionally create an admin user with `python manage.py createsuperuser` and use `/admin/`.

> **Important:** every endpoint path ends with a trailing slash (for example `/api/patients/`). Requests without it will not work for POST, PUT or DELETE.

## 🔐 Authentication

1. Register with `POST /api/auth/register/`.
2. Log in with `POST /api/auth/login/` and copy the `access` token from the response.
3. Send it on every other request:

```http
Authorization: Bearer <access_token>
```

Access tokens are valid for 1 hour; log in again when one expires. Requests with a missing, invalid, expired or tampered token return `401`.

## 🔎 API reference

JSON is the primary format. Form-encoded and multipart bodies are also accepted.

| # | Method | Endpoint | Auth | Description |
|---|---|---|---|---|
| 1 | POST | `/api/auth/register/` | No | Register a user |
| 2 | POST | `/api/auth/login/` | No | Log in, returns a JWT access token |
| 3 | POST | `/api/patients/` | Yes | Create a patient (owner set automatically) |
| 4 | GET | `/api/patients/` | Yes | List your patients |
| 5 | GET | `/api/patients/<id>/` | Yes | Retrieve one of your patients |
| 6 | PUT | `/api/patients/<id>/` | Yes | Update one of your patients |
| 7 | DELETE | `/api/patients/<id>/` | Yes | Delete one of your patients |
| 8 | POST | `/api/doctors/` | Yes | Create a doctor |
| 9 | GET | `/api/doctors/` | Yes | List all doctors (shared directory) |
| 10 | GET | `/api/doctors/<id>/` | Yes | Retrieve a doctor |
| 11 | PUT | `/api/doctors/<id>/` | Yes | Update a doctor |
| 12 | DELETE | `/api/doctors/<id>/` | Yes | Delete a doctor |
| 13 | POST | `/api/mappings/` | Yes | Assign a doctor to one of your patients |
| 14 | GET | `/api/mappings/` | Yes | List mappings for your patients |
| 15 | GET | `/api/mappings/<patient_id>/` | Yes | Doctors assigned to a patient |
| 16 | DELETE | `/api/mappings/<id>/` | Yes | Remove an assignment (`<id>` is the mapping id) |

### Authentication examples

**Register** `POST /api/auth/register/`

```json
{ "name": "Alice Test", "email": "alice@example.com", "password": "Str0ngPass!234" }
```

Response `201 Created` (the password is never returned):

```json
{ "id": 1, "name": "Alice Test", "email": "alice@example.com" }
```

Rules: all three fields are required; the email must be valid and unique (case-insensitive, stored in lowercase); the password must pass Django's validators (minimum length 8, not too common, not entirely numeric, not too similar to your details). A duplicate email returns `400`:

```json
{ "email": ["A user with this email already exists."] }
```

**Login** `POST /api/auth/login/`

```json
{ "email": "alice@example.com", "password": "Str0ngPass!234" }
```

Response `200 OK`:

```json
{
  "access": "<jwt access token>",
  "user": { "id": 1, "name": "Alice Test", "email": "alice@example.com" }
}
```

Wrong credentials and unknown emails return the same generic `401`, so the response does not reveal which accounts exist:

```json
{ "detail": "No active account found with the given credentials" }
```

### Patients

**Create** `POST /api/patients/`

```json
{
  "name": "Test Patient",
  "age": 34,
  "gender": "F",
  "contact_number": "+911234567890",
  "address": "12 Fictional Street",
  "medical_history": "None"
}
```

Response `201 Created`:

```json
{
  "id": 1,
  "name": "Test Patient",
  "age": 34,
  "gender": "F",
  "contact_number": "+911234567890",
  "address": "12 Fictional Street",
  "medical_history": "None",
  "created_by": 1,
  "created_at": "2026-10-28T01:25:41.485072+05:30",
  "updated_at": "2026-10-28T01:25:41.485098+05:30"
}
```

| Field | Rules |
|---|---|
| `name`, `address` | Required, not blank |
| `age` | Required integer, 0 to 150 |
| `gender` | Required: `M`, `F` or `O` |
| `contact_number` | Required: 7 to 15 digits, optional leading `+` |
| `medical_history` | Optional |
| `created_by`, `id`, timestamps | Read-only; any value sent is ignored |

`PUT` replaces the record and needs all required fields. `PATCH` is not supported (`405`). `DELETE` returns `204 No Content`.

### Doctors

**Create** `POST /api/doctors/`

```json
{
  "name": "Dr. Test Doctor",
  "specialization": "Cardiology",
  "email": "doctor.one@example.com",
  "phone_number": "+919876543210",
  "years_of_experience": 12
}
```

Response `201 Created` returns the same fields plus `id`, `created_at` and `updated_at`.

| Field | Rules |
|---|---|
| `name`, `specialization` | Required, not blank |
| `email` | Required, valid, unique (case-insensitive, stored in lowercase) |
| `phone_number` | Required: 7 to 15 digits, optional leading `+` |
| `years_of_experience` | Required integer, 0 to 70 |

Per the assignment, any authenticated user can create, update or delete doctors. Deleting a doctor also removes that doctor's mappings, but never any patients.

### Mappings

**Assign** `POST /api/mappings/`

```json
{ "patient": 1, "doctor": 1 }
```

Response `201 Created`:

```json
{
  "id": 1,
  "patient": 1,
  "patient_name": "Test Patient",
  "doctor": 1,
  "doctor_name": "Dr. Test Doctor",
  "assigned_at": "2026-10-28T01:59:03.067735+05:30"
}
```

**Doctors for a patient** `GET /api/mappings/<patient_id>/` returns `200 OK`:

```json
[
  {
    "mapping_id": 1,
    "doctor": {
      "id": 1,
      "name": "Dr. Test Doctor",
      "specialization": "Cardiology",
      "email": "doctor.one@example.com",
      "phone_number": "+919876543210",
      "years_of_experience": 12,
      "created_at": "2026-10-28T01:37:18.696075+05:30",
      "updated_at": "2026-10-28T01:37:18.696108+05:30"
    },
    "assigned_at": "2026-10-28T01:59:03.067735+05:30"
  }
]
```

An empty list means the patient has no doctors yet.

#### GET and DELETE on the same URL: how routing works

`GET /api/mappings/<id>/` and `DELETE /api/mappings/<id>/` share one URL shape but mean different things. A single route (`path("<str:pk>/", MappingDetailView)`) is handled by one view class, and the HTTP method decides how `<id>` is interpreted:

| Method | `<id>` means | Behavior |
|---|---|---|
| `GET` | **Patient id** | Returns the doctors assigned to that patient (your patients only) |
| `DELETE` | **Mapping id** | Deletes that assignment (your patients' mappings only) |
| `PUT`, `PATCH`, `POST` | n/a | `405 Method Not Allowed` |

The mapping id is the `id` returned when you create the assignment, and also appears as `mapping_id` in the `GET /api/mappings/<patient_id>/` response. Automated tests prove that the two meanings never get mixed up.

## 🧩 Ownership and access rules

- **Patients are private.** Every patient query is filtered by the authenticated user. Another user's patient returns `404` on read, update and delete, so its existence is never revealed. `created_by` cannot be set or changed through the API.
- **Doctors are shared.** Any authenticated user can list, view, create, update and delete doctors.
- **Mappings follow patient ownership.** You can only assign doctors to your own patients, list mappings for your own patients, view doctors for your own patients and delete mappings of your own patients. Assigning to a patient you do not own returns the same `400` as a nonexistent patient, again so nothing is revealed.
- **`GET /api/mappings/` returns only the mappings of your patients.** The assignment says "all mappings"; returning every user's mappings would expose other users' patient data, so results are scoped to the caller.
- Duplicate assignments are rejected with a clear `400` and also blocked by a database unique constraint on `(patient, doctor)`.

## 🔑 Validation and error handling

| Status | Meaning |
|---|---|
| `200` | Successful read or update |
| `201` | Created |
| `204` | Deleted (no body) |
| `400` | Invalid input, duplicate email or duplicate mapping, invalid reference, malformed JSON |
| `401` | Missing, invalid or expired token; wrong login credentials |
| `404` | Record not found, malformed id, or a record that belongs to another user |
| `405` | HTTP method not supported on that URL |
| `415` | Unsupported content type |

Error bodies are JSON and never contain stack traces, database details or secrets:

```json
{ "age": ["Ensure this value is less than or equal to 150."], "gender": ["\"Z\" is not a valid choice."] }
```

```json
{ "detail": "Authentication credentials were not provided." }
```

```json
{ "detail": "No Patient matches the given query." }
```

```json
{ "non_field_errors": ["This doctor is already assigned to this patient."] }
```

## 🚀 Automated tests

```text
python manage.py check
python manage.py test
```

115 tests cover registration and login, JWT handling (expired, tampered, refresh-as-access, deleted and deactivated users), patient ownership isolation, doctor CRUD, mappings (including the GET/DELETE routing), database constraints, cascades and input handling. Django creates and destroys a separate `test_...` database, so your development data is never touched. The run takes a minute or two.

### End-to-end smoke test

With the server running in another terminal:

```text
python scripts/smoke_test.py
```

It exercises all 16 endpoint/method combinations plus failure cases and cross-user access. To prove data survives a restart:

```text
python scripts/smoke_test.py seed
```

Stop and restart the server, then run:

```text
python scripts/smoke_test.py check
```

## 🎯 Postman collection

1. In Postman choose **Import** and select `postman/healthcare_api_collection.json`.
2. If the server is not at `http://127.0.0.1:8000`, edit the `base_url` collection variable.
3. Run the folders in order, or use the Collection Runner on the whole collection.

The collection registers fresh users on every run, saves the access tokens and ids automatically, and includes a folder of failure and security cases (missing or invalid token, cross-user access, duplicates, invalid references) and a final folder that tests deletion. All of its tests should pass.

## 💡 Design decisions and assumptions

The assignment does not prescribe model fields or response shapes, so these are the defaults used:

- A custom `User` model with `email` as the login identifier plus a `name` field.
- Patient fields: name, age, gender, contact number, address, medical history.
- Doctor fields: name, specialization, email, phone number, years of experience.
- Only PUT (not PATCH) is exposed for updates, matching the assignment.
- Login returns an access token only; there is no refresh endpoint.
- Lists are not paginated.

## ⚠️ Known limitations

- No rate limiting on login or registration.
- Because the assignment requires it, any authenticated user can edit or delete any doctor.
- HTTPS redirect and HSTS are not configured; they belong to the deployment environment, which is out of scope.
- Registration reveals whether an email is already taken, which is inherent to rejecting duplicate registrations.

## 🔮 Future improvements

- **Login protection:** add rate limiting (DRF throttling) on login and registration, and temporary lockout after repeated failures.
- **Token lifecycle:** add refresh tokens, logout with token blacklisting, and token rotation.
- **Role-based access:** introduce roles (for example admin, doctor, staff) so only authorized users can edit or delete doctor records.
- **Pagination, search and filtering:** paginate list endpoints and add filters, such as patients by name or doctors by specialization.
- **Partial updates:** support `PATCH` alongside `PUT`.
- **Audit and safety:** keep an audit log of changes to patient data and use soft deletes so records can be recovered.
- **API documentation:** generate an OpenAPI/Swagger schema and interactive docs (for example with `drf-spectacular`).
- **Deployment readiness:** add a production server (such as gunicorn), Docker setup, HTTPS redirect and HSTS settings, and structured logging.
- **Healthcare features:** appointments and scheduling, and richer patient records such as visit notes.

## 👧🏻 Author 

### Anshika Agrawal
