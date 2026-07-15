import os

JWT_ALGORITHM = "HS256"
TOKEN_TTL_HOURS = int(os.environ.get("TOKEN_TTL_HOURS", "8"))
ROLES = ["doctor", "nurse", "psychologist", "receptionist", "biller", "admin"]
CLINICAL_ROLES = ("doctor", "nurse", "psychologist")
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_MINUTES = 15
INVOICE_STATUSES = {"in_transit", "paid", "denied", "unpaid", "void"}
FORM_STATUSES = {"sent", "pending", "received"}
FORMS_ROLES = ("doctor", "nurse", "psychologist", "receptionist", "biller")
FOLDERS_ROLES = ("doctor", "nurse", "psychologist", "receptionist", "biller")
EXT_CONTENT_TYPES = {
    "pdf": "application/pdf", "png": "image/png", "jpg": "image/jpeg",
    "jpeg": "image/jpeg", "webp": "image/webp", "txt": "text/plain",
    "doc": "application/msword",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "")
APP_NAME = "vpp-clinic"

ALL_TABS = ["dashboard", "patients", "appointments", "telehealth", "notes",
            "invoices", "cpt", "reports", "forms", "folders", "messages", "team", "audit", "claims", "assistant"]
DEFAULT_TABS = {
    "admin": ALL_TABS,
    "doctor": ["dashboard", "patients", "appointments", "telehealth", "notes", "forms", "folders", "messages", "assistant"],
    "nurse": ["dashboard", "patients", "appointments", "telehealth", "notes", "forms", "folders", "messages", "assistant"],
    "psychologist": ["dashboard", "appointments", "telehealth", "notes", "messages", "assistant"],
    "receptionist": ["dashboard", "patients", "appointments", "invoices", "forms", "folders", "messages"],
    "biller": ["dashboard", "invoices", "cpt", "reports", "messages"],
}

DEFAULT_SETTINGS = {
    "clinic_name": "Veterans of Puerto Plata",
    "tagline": "Health Clinic",
    "address": "Puerto Plata, Dominican Republic",
    "phone": "+1 (809) 555-0100",
    "email": "info@vpp-clinic.com",
    "whatsapp": "",
    "mailing_address": "",
    "primary_insurance": "",
    "logo": "",
}
