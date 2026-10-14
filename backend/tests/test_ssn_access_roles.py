import os
import sys
import uuid
sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")
load_dotenv("/app/frontend/.env")
import requests  # noqa: E402
from pymongo import MongoClient  # noqa: E402
from core.security import hash_password  # noqa: E402

db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
API = os.environ["REACT_APP_BACKEND_URL"] + "/api"
ok = True


def check(name, cond):
    global ok
    ok &= bool(cond)
    print(("PASS " if cond else "FAIL ") + name)


def login(email, pw):
    return {"Authorization": "Bearer " + requests.post(f"{API}/auth/login", json={"email": email, "password": pw}).json()["token"]}


REC = "zztest.reception@example.com"
if not db.users.find_one({"email": REC}):
    base = db.users.find_one({"email": "zztest.nurse@example.com"}, {"_id": 0})
    db.users.insert_one({**base, "id": str(uuid.uuid4()), "email": REC, "name": "ZZTEST Reception", "role": "receptionist",
                         "password_hash": hash_password("ZZtest-2026!"), "allowed_tabs": None, "must_change_password": False})
admin, rec, nurse = login("usvopp@yahoo.com", "Football2023?"), login(REC, "ZZtest-2026!"), login("zztest.nurse@example.com", "ZZtest-2026!")
pid = f"ZZTEST-SSNR-{uuid.uuid4()}"
db.patients.insert_one({"id": pid, "first_name": "ZZTEST", "last_name": "SsnRole", "ssn": "123-45-6789"})
orig = requests.get(f"{API}/settings/ssn-access", headers=admin).json()["full_roles"]
try:
    check("default: all roles have full access", set(orig) >= {"admin", "doctor", "nurse", "psychologist", "receptionist", "biller"})
    check("receptionist sees full SSN by default", requests.get(f"{API}/patients/{pid}", headers=rec).json()["ssn"] == "123-45-6789")
    check("non-admin cannot read setting", requests.get(f"{API}/settings/ssn-access", headers=rec).status_code == 403)
    check("non-admin cannot change setting", requests.put(f"{API}/settings/ssn-access", headers=nurse, json={"full_roles": ["nurse"]}).status_code == 403)
    r = requests.put(f"{API}/settings/ssn-access", headers=admin, json={"full_roles": ["doctor", "nurse", "psychologist", "biller"]}).json()
    check("admin unticks receptionist; admin always kept", "receptionist" not in r["full_roles"] and "admin" in r["full_roles"])
    check("audit logged", db.audit_logs.find_one({"resource_id": "ssn_access"}) is not None)
    me = requests.get(f"{API}/auth/me", headers=rec).json()
    check("/auth/me reports no access", me["can_view_full_ssn"] is False)
    p = requests.get(f"{API}/patients/{pid}", headers=rec).json()
    check("receptionist sees ***-**-6789", p["ssn"] == "***-**-6789")
    lst = requests.get(f"{API}/patients", headers=rec).json()
    check("patient list masked", next(x for x in lst if x["id"] == pid)["ssn"] == "***-**-6789"
          and all("*" in (x.get("ssn") or "*") for x in lst))
    check("nurse still sees full", requests.get(f"{API}/patients/{pid}", headers=nurse).json()["ssn"] == "123-45-6789")
    body = {k: p.get(k) for k in ("first_name", "last_name", "dob", "gender", "phone", "email", "address", "notes") if p.get(k)}
    r = requests.put(f"{API}/patients/{pid}", headers=rec, json={**body, "ssn": "***-**-6789", "phone": "555"})
    check("receptionist save keeps stored SSN", r.status_code == 200 and db.patients.find_one({"id": pid})["ssn"] == "123-45-6789"
          and db.patients.find_one({"id": pid})["phone"] == "555")
    requests.put(f"{API}/patients/{pid}", headers=rec, json={**body, "ssn": "999-99-9999"})
    check("receptionist cannot change SSN", db.patients.find_one({"id": pid})["ssn"] == "123-45-6789")
    r = requests.post(f"{API}/patients", headers=rec, json={**body, "first_name": "ZZTEST", "last_name": "SsnNew", "ssn": "111-11-1111"}).json()
    check("receptionist cannot enter SSN on new patient", db.patients.find_one({"id": r["id"]}).get("ssn") is None)
    db.patients.delete_one({"id": r["id"]})
    inv = requests.post(f"{API}/invoices", headers=rec, json={"patient_id": pid, "ssn": "***-**-6789", "items": [], "status": "draft"}).json()
    check("invoice response masked", inv.get("ssn") in (None, "***-**-6789"))
    check("invoice stores no masked SSN", "*" not in str(db.invoices.find_one({"id": inv["id"]}).get("ssn") or ""))
    got = requests.get(f"{API}/invoices/{inv['id']}", headers=rec).json()
    check("invoice view masked (from patient)", got["ssn"] == "***-**-6789")
    check("admin invoice view full", requests.get(f"{API}/invoices/{inv['id']}", headers=admin).json()["ssn"] == "123-45-6789")
    db.invoices.delete_one({"id": inv["id"]})
finally:
    requests.put(f"{API}/settings/ssn-access", headers=admin, json={"full_roles": orig})
    db.patients.delete_one({"id": pid})
check("setting restored", set(requests.get(f"{API}/settings/ssn-access", headers=admin).json()["full_roles"]) == set(orig))
print("ALL PASS" if ok else "SOME FAILED")
