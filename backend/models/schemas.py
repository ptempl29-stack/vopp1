from typing import List, Optional
from pydantic import BaseModel, EmailStr


class LoginInput(BaseModel):
    email: EmailStr
    password: str


class RegisterInput(BaseModel):
    email: EmailStr
    password: str
    name: str
    role: str = "receptionist"
    allowed_tabs: Optional[List[str]] = None


class UpdateUserInput(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    role: Optional[str] = None
    password: Optional[str] = None


class PatientInput(BaseModel):
    first_name: str
    last_name: str
    dob: Optional[str] = None
    gender: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    notes: Optional[str] = None
    status: str = "active"


class AppointmentInput(BaseModel):
    patient_id: str
    provider: Optional[str] = None
    date: str
    time: Optional[str] = None
    reason: Optional[str] = None
    status: str = "scheduled"


class NoteInput(BaseModel):
    patient_id: str
    title: str
    content: str = ""
    note_type: str = "free"
    subjective: Optional[str] = None
    objective: Optional[str] = None
    assessment: Optional[str] = None
    plan: Optional[str] = None
    summary: Optional[str] = None
    signature: Optional[str] = None
    dob: Optional[str] = None
    gender: Optional[str] = None
    ssn: Optional[str] = None
    visit_date: Optional[str] = None
    reason_for_visit: Optional[str] = None
    attending_provider: Optional[str] = None
    referring_provider: Optional[str] = None
    icd10: Optional[str] = None


class SummarizeInput(BaseModel):
    content: str


class InvoiceItem(BaseModel):
    cpt_code: str = ""
    description: str = ""
    quantity: int = 1
    minutes: int = 0
    amount: float = 0


class CptInput(BaseModel):
    code: str
    description: str
    amount: float


class InvoiceInput(BaseModel):
    patient_id: Optional[str] = None
    patient_name: Optional[str] = None
    dob: Optional[str] = None
    ssn: Optional[str] = None
    policy_number: Optional[str] = None
    gender: Optional[str] = None
    invoice_number: Optional[str] = None
    service_date: Optional[str] = None
    visit_reason: Optional[str] = None
    icd10: Optional[str] = None
    provider: Optional[str] = None
    items: List[InvoiceItem]
    status: str = "unpaid"
    notes: Optional[str] = None


class MessageInput(BaseModel):
    to_user_id: str
    subject: Optional[str] = None
    body: str


class FormInput(BaseModel):
    patient_id: Optional[str] = None
    title: str
    form_type: str
    fields: Optional[dict] = None
    external_url: Optional[str] = None
    status: str = "sent"
    recipient_email: Optional[EmailStr] = None
    link_base: Optional[str] = None


class SettingsInput(BaseModel):
    clinic_name: str
    tagline: Optional[str] = ""
    address: Optional[str] = ""
    phone: Optional[str] = ""
    email: Optional[str] = ""
    whatsapp: Optional[str] = ""
    mailing_address: Optional[str] = ""
    primary_insurance: Optional[str] = ""
    logo: Optional[str] = ""


class FormSubmission(BaseModel):
    responses: dict
