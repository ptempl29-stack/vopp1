CPT_LIBRARY = [
    {"code": "99202", "description": "New patient office visit, 15-29 min", "amount": 75.00},
    {"code": "99203", "description": "New patient office visit, 30-44 min", "amount": 110.00},
    {"code": "99213", "description": "Established patient visit, 20-29 min", "amount": 90.00},
    {"code": "99214", "description": "Established patient visit, 30-39 min", "amount": 130.00},
    {"code": "99396", "description": "Preventive visit, 40-64 yrs", "amount": 160.00},
    {"code": "90686", "description": "Influenza vaccine", "amount": 35.00},
    {"code": "80053", "description": "Comprehensive metabolic panel", "amount": 55.00},
    {"code": "85025", "description": "Complete blood count (CBC)", "amount": 40.00},
    {"code": "93000", "description": "Electrocardiogram (ECG)", "amount": 65.00},
    {"code": "36415", "description": "Routine venipuncture", "amount": 20.00},
]

DEMO_USERS = [
    {"email": "doctor@vpp.com", "password": "doctor123", "name": "Dr. Elena Marte", "role": "doctor"},
    {"email": "nurse@vpp.com", "password": "nurse123", "name": "Rosa Fernández", "role": "nurse"},
    {"email": "psych@vpp.com", "password": "psych123", "name": "Dr. Luis Herrera", "role": "psychologist"},
    {"email": "reception@vpp.com", "password": "reception123", "name": "Carlos Núñez", "role": "receptionist"},
    {"email": "biller@vpp.com", "password": "biller123", "name": "María Santos", "role": "biller"},
]

FORM_TEMPLATES = {
    "Intake": [
        {"name": "full_name", "en": "Full Name", "es": "Nombre Completo", "type": "text", "required": True},
        {"name": "dob", "en": "Date of Birth", "es": "Fecha de Nacimiento", "type": "date", "required": True},
        {"name": "phone", "en": "Phone", "es": "Teléfono", "type": "text", "required": False},
        {"name": "reason", "en": "Reason for Visit", "es": "Motivo de la Visita", "type": "textarea", "required": True},
        {"name": "medications", "en": "Current Medications", "es": "Medicamentos Actuales", "type": "textarea", "required": False},
        {"name": "allergies", "en": "Allergies", "es": "Alergias", "type": "text", "required": False},
        {"name": "signature", "en": "Patient Signature", "es": "Firma del Paciente", "type": "signature", "required": True},
    ],
    "Consent": [
        {"name": "patient_name", "en": "Patient Name", "es": "Nombre del Paciente", "type": "text", "required": True},
        {"name": "consent", "en": "I consent to treatment", "es": "Consiento al tratamiento", "type": "checkbox", "required": True},
        {"name": "signature", "en": "Signature", "es": "Firma", "type": "signature", "required": True},
        {"name": "date", "en": "Date", "es": "Fecha", "type": "date", "required": True},
    ],
    "Medical History": [
        {"name": "conditions", "en": "Chronic Conditions", "es": "Condiciones Crónicas", "type": "textarea", "required": False},
        {"name": "surgeries", "en": "Past Surgeries", "es": "Cirugías Previas", "type": "textarea", "required": False},
        {"name": "family_history", "en": "Family History", "es": "Historia Familiar", "type": "textarea", "required": False},
        {"name": "smoking", "en": "Do you smoke?", "es": "¿Fuma?", "type": "select", "required": True,
         "options": [{"value": "no", "en": "No", "es": "No"}, {"value": "yes", "en": "Yes", "es": "Sí"}, {"value": "former", "en": "Former", "es": "Ex-fumador"}]},
        {"name": "signature", "en": "Patient Signature", "es": "Firma del Paciente", "type": "signature", "required": True},
    ],
    "Insurance": [
        {"name": "provider", "en": "Insurance Provider", "es": "Aseguradora", "type": "text", "required": True},
        {"name": "policy_number", "en": "Policy Number", "es": "Número de Póliza", "type": "text", "required": True},
        {"name": "group_number", "en": "Group Number", "es": "Número de Grupo", "type": "text", "required": False},
        {"name": "subscriber", "en": "Subscriber Name", "es": "Nombre del Titular", "type": "text", "required": True},
        {"name": "signature", "en": "Patient Signature", "es": "Firma del Paciente", "type": "signature", "required": True},
    ],
    "Referral": [
        {"name": "referring_provider", "en": "Referring Provider", "es": "Médico que Refiere", "type": "text", "required": True},
        {"name": "specialty", "en": "Specialty", "es": "Especialidad", "type": "text", "required": True},
        {"name": "reason", "en": "Reason for Referral", "es": "Motivo de la Referencia", "type": "textarea", "required": True},
        {"name": "signature", "en": "Patient Signature", "es": "Firma del Paciente", "type": "signature", "required": True},
    ],
}
