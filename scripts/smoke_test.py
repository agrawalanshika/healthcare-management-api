"""End-to-end API check using only the Python standard library.

Usage (server must be running, venv active):
    python scripts/smoke_test.py                  # full workflow + failure cases (self-cleaning)
    python scripts/smoke_test.py seed             # create persistent sample data
    python scripts/smoke_test.py check            # after a server restart: verify data survived, then clean up
    python scripts/smoke_test.py http://127.0.0.1:8000   # optional base URL as first argument
"""
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

args = [a for a in sys.argv[1:]]
BASE = next((a for a in args if a.startswith("http")), "http://127.0.0.1:8000").rstrip("/")
MODE = next((a for a in args if a in ("seed", "check")), "run")
STATE_FILE = Path(__file__).with_name(".persist_state.json")
PASSWORD = "Str0ngPass!234"

results = []


def call(method, path, body=None, token=None, raw_body=None):
    data = raw_body if raw_body is not None else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req) as resp:
            status, text = resp.status, resp.read().decode()
    except urllib.error.HTTPError as err:
        status, text = err.code, err.read().decode()
    try:
        payload = json.loads(text) if text else None
    except ValueError:
        payload = text
    return status, payload


def check(name, condition, detail=""):
    results.append(bool(condition))
    print(f"  [{'PASS' if condition else 'FAIL'}] {name}" + ("" if condition else f"  -> {detail}"))


def expect(name, response, status, extra=True):
    code, body = response
    check(name, code == status and extra, f"got {code}: {body}")
    return body


def register_login(email, name):
    code, _ = call("POST", "/api/auth/register/", {"name": name, "email": email, "password": PASSWORD})
    code, body = call("POST", "/api/auth/login/", {"email": email, "password": PASSWORD})
    return body["access"] if code == 200 else None


PATIENT = {
    "name": "Test Patient", "age": 34, "gender": "F", "contact_number": "+911234567890",
    "address": "12 Fictional Street", "medical_history": "None",
}


def doctor_payload(email):
    return {
        "name": "Dr. Test Doctor", "specialization": "Cardiology", "email": email,
        "phone_number": "+919876543210", "years_of_experience": 12,
    }


def run_full():
    stamp = int(time.time())
    a_email, b_email, d_email = f"e2e_a_{stamp}@example.com", f"e2e_b_{stamp}@example.com", f"e2e_doc_{stamp}@example.com"

    print("\n== 1. Authentication (POST register, POST login)")
    reg = call("POST", "/api/auth/register/", {"name": "Alice E2E", "email": a_email, "password": PASSWORD})
    expect("register user A -> 201, no password in response", reg, 201, "password" not in json.dumps(reg[1]))
    expect("duplicate email -> 400", call("POST", "/api/auth/register/", {"name": "X", "email": a_email.upper(), "password": PASSWORD}), 400)
    expect("missing fields -> 400", call("POST", "/api/auth/register/", {}), 400)
    expect("register user B -> 201", call("POST", "/api/auth/register/", {"name": "Bob E2E", "email": b_email, "password": PASSWORD}), 201)
    login = call("POST", "/api/auth/login/", {"email": a_email, "password": PASSWORD})
    expect("login A -> 200 with access token", login, 200, bool(login[1] and login[1].get("access")))
    ta = login[1]["access"]
    tb = call("POST", "/api/auth/login/", {"email": b_email, "password": PASSWORD})[1]["access"]
    expect("wrong password -> 401", call("POST", "/api/auth/login/", {"email": a_email, "password": "Wrong!Pass999"}), 401)
    expect("unknown user -> 401", call("POST", "/api/auth/login/", {"email": "nobody@example.com", "password": PASSWORD}), 401)

    print("\n== 2. Token enforcement")
    expect("no token -> 401", call("GET", "/api/patients/"), 401)
    expect("invalid token -> 401", call("GET", "/api/patients/", token="not.a.token"), 401)
    expect("no token on doctors -> 401", call("GET", "/api/doctors/"), 401)
    expect("no token on mappings -> 401", call("GET", "/api/mappings/"), 401)

    print("\n== 3. Patients (POST, GET list, GET one, PUT, DELETE)")
    p = expect("POST /api/patients/ -> 201", call("POST", "/api/patients/", PATIENT, ta), 201)
    pid = p["id"]
    check("created_by is the authenticated user", p["created_by"] == reg[1]["id"])
    lst = call("GET", "/api/patients/", token=ta)
    expect("GET /api/patients/ -> 200 and includes patient", lst, 200, pid in [x["id"] for x in lst[1]])
    expect("GET /api/patients/<id>/ -> 200", call("GET", f"/api/patients/{pid}/", token=ta), 200)
    upd = call("PUT", f"/api/patients/{pid}/", {**PATIENT, "name": "Updated Patient", "age": 35}, ta)
    expect("PUT /api/patients/<id>/ -> 200 and persisted", upd, 200, upd[1]["name"] == "Updated Patient")
    check("update persisted", call("GET", f"/api/patients/{pid}/", token=ta)[1]["age"] == 35)
    expect("invalid patient data -> 400", call("POST", "/api/patients/", {**PATIENT, "age": 500, "gender": "Z"}, ta), 400)
    expect("missing patient fields -> 400", call("POST", "/api/patients/", {}, ta), 400)
    expect("malformed patient id -> 404", call("GET", "/api/patients/abc/", token=ta), 404)
    expect("nonexistent patient id -> 404", call("GET", "/api/patients/999999/", token=ta), 404)
    expect("PATCH not allowed -> 405", call("PATCH", f"/api/patients/{pid}/", {"name": "x"}, ta), 405)
    print("  -- cross-user isolation")
    expect("B cannot GET A's patient -> 404", call("GET", f"/api/patients/{pid}/", token=tb), 404)
    expect("B cannot PUT A's patient -> 404", call("PUT", f"/api/patients/{pid}/", PATIENT, tb), 404)
    expect("B cannot DELETE A's patient -> 404", call("DELETE", f"/api/patients/{pid}/", token=tb), 404)
    expect("B's list excludes A's patient", call("GET", "/api/patients/", token=tb), 200, call("GET", "/api/patients/", token=tb)[1] == [])

    print("\n== 4. Doctors (POST, GET list, GET one, PUT, DELETE)")
    d = expect("POST /api/doctors/ -> 201", call("POST", "/api/doctors/", doctor_payload(d_email), ta), 201)
    did = d["id"]
    dl = call("GET", "/api/doctors/", token=tb)
    expect("GET /api/doctors/ (shared, as B) -> 200", dl, 200, did in [x["id"] for x in dl[1]])
    expect("GET /api/doctors/<id>/ -> 200", call("GET", f"/api/doctors/{did}/", token=ta), 200)
    du = call("PUT", f"/api/doctors/{did}/", {**doctor_payload(d_email), "specialization": "Neurology"}, ta)
    expect("PUT /api/doctors/<id>/ -> 200", du, 200, du[1]["specialization"] == "Neurology")
    expect("duplicate doctor email -> 400", call("POST", "/api/doctors/", doctor_payload(d_email.upper()), ta), 400)
    expect("invalid doctor data -> 400", call("POST", "/api/doctors/", {**doctor_payload("x@example.com"), "years_of_experience": 99, "phone_number": "abc"}, ta), 400)
    expect("nonexistent doctor -> 404", call("GET", "/api/doctors/999999/", token=ta), 404)
    expect("malformed doctor id -> 404", call("GET", "/api/doctors/abc/", token=ta), 404)

    print("\n== 5. Mappings (POST, GET list, GET by patient, DELETE)")
    m = expect("POST /api/mappings/ -> 201", call("POST", "/api/mappings/", {"patient": pid, "doctor": did}, ta), 201)
    mid = m["id"]
    expect("duplicate mapping -> 400", call("POST", "/api/mappings/", {"patient": pid, "doctor": did}, ta), 400)
    expect("nonexistent patient -> 400", call("POST", "/api/mappings/", {"patient": 999999, "doctor": did}, ta), 400)
    expect("nonexistent doctor -> 400", call("POST", "/api/mappings/", {"patient": pid, "doctor": 999999}, ta), 400)
    expect("B cannot assign to A's patient -> 400", call("POST", "/api/mappings/", {"patient": pid, "doctor": did}, tb), 400)
    expect("invalid types -> 400", call("POST", "/api/mappings/", {"patient": "abc", "doctor": True}, ta), 400)
    ml = call("GET", "/api/mappings/", token=ta)
    expect("GET /api/mappings/ -> 200 and includes mapping", ml, 200, mid in [x["id"] for x in ml[1]])
    expect("B's mapping list is empty", call("GET", "/api/mappings/", token=tb), 200, call("GET", "/api/mappings/", token=tb)[1] == [])
    by_patient = call("GET", f"/api/mappings/{pid}/", token=ta)
    expect("GET /api/mappings/<patient_id>/ -> doctors for patient", by_patient, 200,
           [x["doctor"]["id"] for x in by_patient[1]] == [did] and by_patient[1][0]["mapping_id"] == mid)
    expect("B cannot view A's patient mappings -> 404", call("GET", f"/api/mappings/{pid}/", token=tb), 404)
    expect("B cannot delete A's mapping -> 404", call("DELETE", f"/api/mappings/{mid}/", token=tb), 404)
    expect("PUT on mapping not allowed -> 405", call("PUT", f"/api/mappings/{mid}/", {}, ta), 405)
    expect("DELETE /api/mappings/<mapping_id>/ -> 204", call("DELETE", f"/api/mappings/{mid}/", token=ta), 204)
    expect("mapping no longer listed for patient", call("GET", f"/api/mappings/{pid}/", token=ta), 200, call("GET", f"/api/mappings/{pid}/", token=ta)[1] == [])
    expect("deleting it again -> 404", call("DELETE", f"/api/mappings/{mid}/", token=ta), 404)
    expect("malformed mapping id -> 404", call("DELETE", "/api/mappings/abc/", token=ta), 404)

    print("\n== 6. Deletion endpoints")
    expect("DELETE /api/patients/<id>/ -> 204", call("DELETE", f"/api/patients/{pid}/", token=ta), 204)
    expect("deleted patient -> 404", call("GET", f"/api/patients/{pid}/", token=ta), 404)
    expect("DELETE /api/doctors/<id>/ -> 204", call("DELETE", f"/api/doctors/{did}/", token=ta), 204)
    expect("deleted doctor -> 404", call("GET", f"/api/doctors/{did}/", token=ta), 404)


def run_seed():
    token = register_login("persist@example.com", "Persist User")
    check("login persistent user", token is not None)
    code, p = call("POST", "/api/patients/", PATIENT, token)
    check("create patient", code == 201, p)
    code, d = call("POST", "/api/doctors/", doctor_payload(f"persist_doc_{int(time.time())}@example.com"), token)
    check("create doctor", code == 201, d)
    code, m = call("POST", "/api/mappings/", {"patient": p["id"], "doctor": d["id"]}, token)
    check("create mapping", code == 201, m)
    STATE_FILE.write_text(json.dumps({"patient": p["id"], "doctor": d["id"], "mapping": m["id"]}))
    print(f"\n  Seeded patient={p['id']} doctor={d['id']} mapping={m['id']}.")
    print("  Now STOP the Django server, START it again, then run:  python scripts/smoke_test.py check")


def run_check():
    if not STATE_FILE.exists():
        print("No seed data found. Run: python scripts/smoke_test.py seed")
        sys.exit(1)
    state = json.loads(STATE_FILE.read_text())
    code, body = call("POST", "/api/auth/login/", {"email": "persist@example.com", "password": PASSWORD})
    check("login still works after restart", code == 200, body)
    token = body["access"]
    check("patient persisted", call("GET", f"/api/patients/{state['patient']}/", token=token)[0] == 200)
    check("doctor persisted", call("GET", f"/api/doctors/{state['doctor']}/", token=token)[0] == 200)
    code, listing = call("GET", f"/api/mappings/{state['patient']}/", token=token)
    check("mapping persisted", code == 200 and [x["mapping_id"] for x in listing] == [state["mapping"]], listing)
    print("\n  Cleaning up seeded records...")
    check("delete mapping", call("DELETE", f"/api/mappings/{state['mapping']}/", token=token)[0] == 204)
    check("delete patient", call("DELETE", f"/api/patients/{state['patient']}/", token=token)[0] == 204)
    check("delete doctor", call("DELETE", f"/api/doctors/{state['doctor']}/", token=token)[0] == 204)
    STATE_FILE.unlink()


if __name__ == "__main__":
    print(f"Target: {BASE}  |  mode: {MODE}")
    try:
        {"run": run_full, "seed": run_seed, "check": run_check}[MODE]()
    except urllib.error.URLError as exc:
        print(f"Cannot reach the server at {BASE}: {exc}. Is `python manage.py runserver` running?")
        sys.exit(2)
    passed, total = sum(results), len(results)
    print(f"\nRESULT: {passed}/{total} checks passed")
    sys.exit(0 if passed == total else 1)
