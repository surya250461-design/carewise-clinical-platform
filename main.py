"""
main.py
-------
Starbucks AI Clinical History Software Platform:
Main FastAPI traffic controller exposing:
1. Patient Authentication (Password & ABHA ID / ABDM simulation).
2. DPDP Act 2023 Consent Management & Kiosk Session Termination.
3. Multimodal Conversational History Engine (Adaptive SOCRATES probing & touch chips).
4. Medical Document Digitization with OCR, Abnormal Value Highlighting & Drug Interactions.
5. Structured Clinical Summary Generator (Bilingual output).
6. HL7 FHIR R4 Bundle Export & Hospital Information System (HIS/EMR) Queue Routing.
"""

import os
import shutil
import uuid
from datetime import datetime
from typing import Optional
from fastapi import FastAPI, UploadFile, File, Form, Depends, Request, Response, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import database
import extract
import red_flags
import auth
import consultation

app = FastAPI(title="Starbucks AI Clinical History Software Platform")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def all_exceptions_as_json(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"status": "error", "message": f"{type(exc).__name__}: {exc}"},
    )


UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


@app.on_event("startup")
def startup():
    database.init_db()
    database.seed_default_accounts()


# ---------- Auth Helpers ----------

def get_current_user(request: Request):
    """
    Validates session token cookie or Authorization bearer token for kiosk APIs.
    """
    token = request.cookies.get("session_token")
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]

    if not token:
        raise HTTPException(status_code=401, detail="Not logged in.")
    user = database.get_session(token)
    if not user:
        raise HTTPException(status_code=401, detail="Session expired or invalid. Please log in again.")
    return user


def require_role(*allowed_roles):
    def checker(user: dict = Depends(get_current_user)):
        if user["role"] not in allowed_roles:
            raise HTTPException(status_code=403, detail=f"This requires one of: {', '.join(allowed_roles)}.")
        return user
    return checker


# ---------- Request Models ----------

class LoginRequest(BaseModel):
    username: str
    password: str


class AbhaVerifyRequest(BaseModel):
    abha_id: str
    otp: str = "123456"
    full_name: str = ""


class RegisterPatientRequest(BaseModel):
    username: str
    password: str
    full_name: str = ""
    abha_id: str = ""


class CreateStaffRequest(BaseModel):
    username: str
    password: str
    full_name: str = ""
    role: str  # "doctor" or "admin"


class SocratesNextQuestionRequest(BaseModel):
    chief_complaint: str = ""
    answers_so_far: dict = Field(default_factory=dict)
    language: str = "en"


class ChatConsultRequest(BaseModel):
    message: str
    conversation_history: list = Field(default_factory=list)
    current_state: dict = Field(default_factory=dict)
    language: str = "en"


class DPDPRecordConsentRequest(BaseModel):
    patient_id: str
    consent_scope: str = "clinical_history,document_ocr,his_abdm_sharing"
    audio_consent_listened: bool = False


class IntakeSubmission(BaseModel):
    chief_complaint: str = ""
    present_illness: str = ""
    past_history: str = ""
    medications: str = ""
    allergies: str = ""
    family_history: str = ""
    lifestyle: str = ""
    prakriti: str = ""
    vikriti: str = ""
    agni: str = ""
    ahara_vihara: str = ""
    dashavidha_pariksha: str = ""
    socrates: dict = Field(default_factory=dict)
    ros: dict = Field(default_factory=dict)
    consent_info: dict = Field(default_factory=dict)
    abha_id: str = ""
    language: str = "en"


class SummaryUpdate(BaseModel):
    summary_text: str
    patient_lang_summary: str = ""
    doctor_notes: str = ""
    approved: bool = False


# ---------- Authentication & ABHA Endpoints ----------

@app.post("/auth/login")
async def login(payload: LoginRequest, response: Response):
    user = database.get_user_by_username(payload.username)
    if not user or not auth.verify_password(payload.password, user["password_hash"], user["salt"]):
        raise HTTPException(status_code=401, detail="Incorrect username or password.")

    token = auth.generate_token()
    database.create_session(token, user["id"], user["role"])
    response.set_cookie(key="session_token", value=token, httponly=True, samesite="lax")
    return {
        "status": "success",
        "role": user["role"],
        "full_name": user["full_name"],
        "patient_id": user["patient_id"],
        "abha_id": user.get("abha_id", ""),
    }


@app.post("/auth/abha-verify")
async def abha_verify(payload: AbhaVerifyRequest, response: Response):
    """
    Verifies ABHA ID (or generates a validated test ABHA ID) and signs in the patient
    at Starbucks with zero friction for walk-ins.
    """
    raw_abha = payload.abha_id.strip()
    if not raw_abha:
        raw_abha = auth.generate_abha_id()

    formatted_abha = auth.format_abha(raw_abha)
    if not auth.verify_abdm_otp(formatted_abha, payload.otp):
        raise HTTPException(status_code=400, detail="Invalid ABDM OTP code. Enter a 6-digit number.")

    # Check if patient exists with this ABHA
    patient_name = payload.full_name or "Walk-in Patient"
    existing_user = database.get_user_by_username(formatted_abha)

    if not existing_user:
        patient_id = auth.generate_patient_id()
        digest, salt = auth.hash_password("abha-kiosk-guest")
        abha_address = auth.generate_abha_address(patient_name)
        database.create_user(
            username=formatted_abha,
            password_hash=digest,
            salt=salt,
            role="patient",
            full_name=patient_name,
            patient_id=patient_id,
            abha_id=formatted_abha,
            abha_address=abha_address,
        )
        user = database.get_user_by_username(formatted_abha)
    else:
        user = existing_user
        patient_id = user["patient_id"]

    token = auth.generate_token()
    database.create_session(token, user["id"], "patient")
    response.set_cookie(key="session_token", value=token, httponly=True, samesite="lax")

    database.log_dpdp_action(
        "ABHA_AUTHENTICATED",
        patient_id=patient_id,
        abha_id=formatted_abha,
        details=f"Patient authenticated via ABDM ABHA ID: {formatted_abha}",
    )

    return {
        "status": "success",
        "role": "patient",
        "full_name": user["full_name"],
        "patient_id": patient_id,
        "abha_id": formatted_abha,
    }


@app.post("/auth/register-patient")
async def register_patient(payload: RegisterPatientRequest, response: Response):
    existing = database.get_user_by_username(payload.username)
    if existing:
        raise HTTPException(status_code=400, detail="That username is already taken.")

    digest, salt = auth.hash_password(payload.password)
    patient_id = auth.generate_patient_id()
    while database.get_user_by_username(patient_id):
        patient_id = auth.generate_patient_id()

    formatted_abha = auth.format_abha(payload.abha_id) if payload.abha_id else auth.generate_abha_id()
    abha_address = auth.generate_abha_address(payload.full_name)

    database.create_user(
        username=payload.username,
        password_hash=digest,
        salt=salt,
        role="patient",
        full_name=payload.full_name,
        patient_id=patient_id,
        abha_id=formatted_abha,
        abha_address=abha_address,
    )
    user = database.get_user_by_username(payload.username)

    token = auth.generate_token()
    database.create_session(token, user["id"], "patient")
    response.set_cookie(key="session_token", value=token, httponly=True, samesite="lax")
    return {
        "status": "success",
        "role": "patient",
        "full_name": user["full_name"],
        "patient_id": patient_id,
        "abha_id": formatted_abha,
    }


@app.post("/auth/logout")
async def logout(request: Request, response: Response):
    token = request.cookies.get("session_token")
    if token:
        database.delete_session(token)
    response.delete_cookie("session_token")
    return {"status": "success"}


@app.get("/auth/me")
async def read_current_user(user: dict = Depends(get_current_user)):
    return user


# ---------- DPDP Act 2023 Consent & Kiosk Session Termination ----------

@app.post("/api/patient/consent")
async def record_patient_consent(payload: DPDPRecordConsentRequest, user: dict = Depends(get_current_user)):
    """Records explicit consent under the DPDP Act 2023 and ABDM framework."""
    patient_id = user["patient_id"] if user["role"] == "patient" else payload.patient_id
    database.log_dpdp_action(
        "DPDP_CONSENT_GRANTED",
        patient_id=patient_id,
        abha_id=user.get("abha_id", ""),
        details=f"Scope: {payload.consent_scope}. Audio consent listened: {payload.audio_consent_listened}",
    )
    return {"status": "success", "consented_at": datetime.now().isoformat()}


@app.post("/api/patient/terminate-session")
async def terminate_kiosk_session(request: Request, response: Response, user: dict = Depends(get_current_user)):
    """
    DPDP privacy protection: Clears session cookie and destroys kiosk session
    immediately after form submission so the next walk-in patient cannot see prior data.
    """
    token = request.cookies.get("session_token")
    patient_id = user.get("patient_id", "kiosk-patient")
    if token:
        database.purge_kiosk_session(token, patient_id)
    response.delete_cookie("session_token")
    return {"status": "success", "message": "Kiosk session securely purged."}


# ---------- Module A: Multimodal Conversational History Engine ----------

@app.post("/api/converse/next-question")
async def converse_next_question(payload: SocratesNextQuestionRequest):
    """
    Adaptive questioning engine (SOCRATES): analyzes chief complaint and prior answers
    to dynamically return the next probe with quick-tap touch chips and audio text.
    """
    probe = extract.generate_socrates_probe(
        chief_complaint=payload.chief_complaint,
        answers_so_far=payload.answers_so_far,
        language=payload.language,
    )
    return probe


@app.post("/api/converse/chat-consult")
async def converse_chat_consult(payload: ChatConsultRequest):
    """
    Conversational AI Doctor Consultation Engine:
    - Validates medical input (filters inappropriate, gibberish, and off-topic messages).
    - Asks adaptive follow-up questions dynamically tailored to the primary complaint.
    - Generates disease-specific response suggestion chips.
    - Extracts live clinical telemetry for the physician chart.
    """
    result = consultation.process_consultation_turn(
        message=payload.message,
        conversation_history=payload.conversation_history,
        current_state=payload.current_state,
        language=payload.language,
    )
    return result


# ---------- Module B: Document Upload & Intelligence ----------

@app.post("/upload-case")
async def upload_case(
    patient_id: str = Form(...),
    doc_type: str = Form("prescription"),
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    """
    Document Digitization Pipeline:
    1. Saves unique uploaded file
    2. Runs OCR on handwritten/printed scans or direct PDF parsing
    3. Extracts structured entities (diagnoses, medications, lab values, procedures)
    4. Evaluates abnormal lab values against clinical reference ranges
    5. Screens for adverse drug-drug interactions
    6. Saves structured records in chronological medical ledger
    """
    if user["role"] == "patient":
        patient_id = user["patient_id"]

    file_extension = os.path.splitext(file.filename)[1]
    stored_filename = f"{patient_id}_{uuid.uuid4().hex[:8]}{file_extension}"
    filepath = os.path.join(UPLOAD_DIR, stored_filename)

    with open(filepath, "wb") as f:
        shutil.copyfileobj(file.file, f)

    raw_text = extract.extract_text_from_file(filepath)
    structured_data = extract.extract_entities(raw_text)
    structured_data["doc_type"] = doc_type

    database.save_record(
        patient_id=patient_id,
        source_filename=file.filename,
        stored_filename=stored_filename,
        extracted=structured_data,
        doc_type=doc_type,
    )

    return {
        "status": "success",
        "doc_type": doc_type,
        "extracted": structured_data,
        "abnormal_flags": structured_data.get("abnormal_flags", []),
        "drug_interactions": structured_data.get("drug_interactions", []),
    }


@app.get("/api/patient/my-records")
async def get_patient_my_records(
    patient_id: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    """
    Returns unified previous medical records, past digitized prescriptions/lab reports,
    and prior OPD consultations for the authenticated patient (or specified patient if doctor/admin).
    """
    target_patient_id = user.get("patient_id") or ""
    target_abha_id = user.get("abha_id") or ""

    if user["role"] in ("doctor", "admin") and patient_id:
        target_patient_id = patient_id
        target_abha_id = ""

    return database.get_patient_full_history(target_patient_id, target_abha_id)


# ---------- Module C & D: Intake, Triage & Structured Summaries ----------

@app.post("/intake/{patient_id}")
async def submit_intake(patient_id: str, submission: IntakeSubmission, user: dict = Depends(get_current_user)):
    """
    Saves patient intake, conducts emergency red-flag triage assessment,
    pre-computes clinical summary and FHIR bundle, and routes to HIS OPD queue.
    """
    if user["role"] == "patient":
        patient_id = user["patient_id"]

    fields = submission.model_dump()
    socrates = fields.pop("socrates", {})
    ros = fields.pop("ros", {})
    consent_info = fields.pop("consent_info", {})
    abha_id = fields.pop("abha_id", "")
    language = fields.pop("language", "en")

    # Evaluate Emergency Red Flags & Triage Priority Level
    try:
        is_flagged, reasons, triage_level = red_flags.evaluate(
            fields["chief_complaint"], fields["present_illness"], call_llm_fn=extract.call_llm
        )
    except Exception:
        is_flagged, reasons, triage_level = red_flags.evaluate(
            fields["chief_complaint"], fields["present_illness"]
        )

    database.save_intake(
        patient_id=patient_id,
        fields=fields,
        red_flag=is_flagged,
        red_flag_reasons=reasons,
        triage_level=triage_level,
        socrates=socrates,
        ros=ros,
        consent_info=consent_info,
        abha_id=abha_id,
        language=language,
    )

    # Pre-generate summary & FHIR bundle for immediate physician consultation
    intake_data = database.get_intake(patient_id)
    timeline_data = database.get_timeline(patient_id)
    summary_pack = extract.generate_summary(intake_data, timeline_data, language=language)
    fhir_bundle = extract.generate_fhir_bundle(patient_id, intake_data, timeline_data)

    database.save_summary(
        patient_id=patient_id,
        summary_text=summary_pack["physician_summary"],
        patient_lang_summary=summary_pack["patient_summary"],
        approved=False,
        fhir_bundle=fhir_bundle,
    )

    return {
        "status": "success",
        "red_flag": is_flagged,
        "red_flag_reasons": reasons,
        "triage_level": triage_level,
        "patient_summary": summary_pack["patient_summary"],
    }


@app.get("/intake/{patient_id}")
async def read_intake(patient_id: str, user: dict = Depends(require_role("doctor", "admin"))):
    return {"patient_id": patient_id, "intake": database.get_intake(patient_id)}


@app.post("/summary/{patient_id}")
async def create_summary(patient_id: str, user: dict = Depends(require_role("doctor", "admin"))):
    """Regenerates the physician clinical summary, patient explanation, and FHIR bundle."""
    intake = database.get_intake(patient_id)
    timeline = database.get_timeline(patient_id)
    lang = intake.get("language", "en") if intake else "en"

    summary_pack = extract.generate_summary(intake, timeline, language=lang)
    fhir_bundle = extract.generate_fhir_bundle(patient_id, intake, timeline)

    database.save_summary(
        patient_id=patient_id,
        summary_text=summary_pack["physician_summary"],
        patient_lang_summary=summary_pack["patient_summary"],
        approved=False,
        fhir_bundle=fhir_bundle,
    )
    return {
        "status": "success",
        "summary_text": summary_pack["physician_summary"],
        "patient_lang_summary": summary_pack["patient_summary"],
        "approved": False,
    }


@app.put("/summary/{patient_id}")
async def update_summary(patient_id: str, update: SummaryUpdate, user: dict = Depends(require_role("doctor", "admin"))):
    """Saves physician edits, clinical notes, and approval/sign-off."""
    database.save_summary(
        patient_id=patient_id,
        summary_text=update.summary_text,
        patient_lang_summary=update.patient_lang_summary,
        doctor_notes=update.doctor_notes,
        approved=update.approved,
        approved_by=user.get("full_name") or user["username"],
    )
    return {"status": "success"}


@app.get("/summary/{patient_id}")
async def read_summary(patient_id: str, user: dict = Depends(require_role("doctor", "admin"))):
    return {"patient_id": patient_id, "summary": database.get_summary(patient_id)}


# ---------- Interoperability: FHIR & HIS / EMR Integration ----------

@app.get("/api/fhir/{patient_id}")
async def get_fhir_bundle(patient_id: str, user: dict = Depends(require_role("doctor", "admin"))):
    """Exports compliant HL7 FHIR R4 JSON Bundle for the patient."""
    summary_record = database.get_summary(patient_id)
    if summary_record and summary_record.get("fhir_bundle"):
        return summary_record["fhir_bundle"]

    intake = database.get_intake(patient_id)
    timeline = database.get_timeline(patient_id)
    bundle = extract.generate_fhir_bundle(patient_id, intake, timeline)
    return bundle


@app.get("/api/his/queue")
async def get_his_queue(user: dict = Depends(require_role("doctor", "admin"))):
    """Returns the live hospital OPD triage queue ordered by medical urgency."""
    return {"queue": database.get_his_queue()}


@app.post("/api/his/push/{patient_id}")
async def push_patient_to_his(patient_id: str, user: dict = Depends(require_role("doctor", "admin"))):
    """Pushes structured clinical history to the Hospital Information System (HIS / EMR)."""
    result = database.push_to_his(patient_id)
    return result


@app.get("/patients")
async def list_patients(user: dict = Depends(require_role("doctor", "admin"))):
    return {"patients": database.list_patients()}


@app.get("/timeline/{patient_id}")
async def get_timeline(patient_id: str, user: dict = Depends(require_role("doctor", "admin"))):
    timeline = database.get_timeline(patient_id)
    return {"patient_id": patient_id, "timeline": timeline}


# ---------- Admin & Compliance Endpoints ----------

@app.get("/admin/users")
async def admin_list_users(admin: dict = Depends(require_role("admin"))):
    return {"users": database.list_users()}


@app.post("/admin/users")
async def admin_create_staff(payload: CreateStaffRequest, admin: dict = Depends(require_role("admin"))):
    if payload.role not in ("doctor", "admin"):
        raise HTTPException(status_code=400, detail="Role must be 'doctor' or 'admin'.")
    if database.get_user_by_username(payload.username):
        raise HTTPException(status_code=400, detail="That username is already taken.")
    digest, salt = auth.hash_password(payload.password)
    database.create_user(payload.username, digest, salt, payload.role, payload.full_name)
    return {"status": "success"}


@app.get("/admin/stats")
async def admin_stats(admin: dict = Depends(require_role("admin"))):
    return database.get_stats()


@app.get("/admin/audit-logs")
async def admin_audit_logs(admin: dict = Depends(require_role("admin"))):
    """DPDP Act 2023 Compliance Audit Trail."""
    logs = database.get_dpdp_audit_logs(100)
    return {"logs": logs, "audit_logs": logs}


@app.post("/admin/reset")
async def admin_reset(admin: dict = Depends(require_role("admin"))):
    database.reset_all_data()
    return {"status": "success"}


# ---------- Static Frontend Files ----------

app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")


NO_CACHE_HEADERS = {
    "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
}


@app.get("/")
async def serve_root_gateway():
    """Primary Gateway: Starbucks Unified Login & Check-in Portal."""
    return FileResponse("static/login.html", headers=NO_CACHE_HEADERS)


@app.get("/login")
async def serve_login_page():
    return FileResponse("static/login.html", headers=NO_CACHE_HEADERS)


@app.get("/doctor")
async def serve_doctor_station():
    """Physician Clinical Station & Triage Monitor."""
    return FileResponse("static/index.html", headers=NO_CACHE_HEADERS)


@app.get("/portal")
async def serve_portal_alias():
    return FileResponse("static/index.html", headers=NO_CACHE_HEADERS)


@app.get("/intake")
async def serve_intake_page(request: Request):
    """
    Patient Kiosk Clinical Intake.
    Directly accessible for self-service walk-in patients and physicians.
    If no active session exists, an anonymous walk-in guest session is automatically
    initialized and set as a cookie so the kiosk immediately works without a login wall.
    """
    token = request.cookies.get("session_token")
    user = database.get_session(token) if token else None

    resp = FileResponse("static/intake.html", headers=NO_CACHE_HEADERS)

    if not user:
        guest_token = auth.generate_token()
        guest_patient_id = auth.generate_patient_id()
        guest_abha = auth.generate_abha_id()
        guest_username = f"walkin_{guest_patient_id}"

        digest, salt = auth.hash_password("kiosk-guest")
        database.create_user(
            username=guest_username,
            password_hash=digest,
            salt=salt,
            role="patient",
            full_name="Walk-in Patient",
            patient_id=guest_patient_id,
            abha_id=guest_abha,
            abha_address=auth.generate_abha_address("Walk-in Patient"),
        )
        created_user = database.get_user_by_username(guest_username)
        database.create_session(guest_token, created_user["id"], "patient")
        resp.set_cookie(key="session_token", value=guest_token, httponly=True, samesite="lax")

    return resp


@app.get("/admin")
async def serve_admin_page():
    return FileResponse("static/admin.html", headers=NO_CACHE_HEADERS)


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)


