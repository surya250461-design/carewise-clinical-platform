"""
database.py
------------
Everything about saving and reading patient records lives here.
We use SQLite with backward-compatible schema migrations for Starbucks.
"""

import sqlite3
import json
import secrets
from datetime import datetime

DB_PATH = "patient_cases.db"


def init_db():
    """Creates all tables if they don't already exist and safely migrates columns."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Core document records
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id TEXT NOT NULL,
            record_date TEXT,
            source_filename TEXT,
            stored_filename TEXT,
            doc_type TEXT DEFAULT 'prescription',
            diagnoses TEXT,
            medications TEXT,
            investigations TEXT,
            procedures TEXT,
            abnormal_flags TEXT DEFAULT '[]',
            drug_interactions TEXT DEFAULT '[]',
            raw_json TEXT
        )
    """)

    # Patient intake (Conversational, SOCRATES, AYUSH, DPDP Consent)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS intake (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id TEXT NOT NULL,
            chief_complaint TEXT,
            present_illness TEXT,
            past_history TEXT,
            medications TEXT,
            allergies TEXT,
            family_history TEXT,
            lifestyle TEXT,
            prakriti TEXT,
            vikriti TEXT,
            agni TEXT,
            ahara_vihara TEXT,
            dashavidha_pariksha TEXT,
            socrates_json TEXT DEFAULT '{}',
            ros_json TEXT DEFAULT '{}',
            triage_level TEXT DEFAULT 'routine',
            red_flag INTEGER DEFAULT 0,
            red_flag_reasons TEXT DEFAULT '[]',
            consent_dpdp INTEGER DEFAULT 1,
            consent_scope TEXT DEFAULT 'clinical_history,document_ocr,his_abdm_sharing',
            consent_timestamp TEXT,
            audio_consent_listened INTEGER DEFAULT 0,
            abha_id TEXT DEFAULT '',
            language TEXT DEFAULT 'en',
            submitted_at TEXT
        )
    """)

    # AI Clinical summaries & FHIR bundles
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS summaries (
            patient_id TEXT PRIMARY KEY,
            summary_text TEXT,
            patient_lang_summary TEXT DEFAULT '',
            doctor_notes TEXT DEFAULT '',
            approved INTEGER DEFAULT 0,
            approved_by TEXT DEFAULT '',
            approved_at TEXT,
            fhir_bundle TEXT DEFAULT '',
            his_push_status TEXT DEFAULT 'pending',
            updated_at TEXT
        )
    """)

    # User accounts
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            role TEXT NOT NULL,
            full_name TEXT,
            patient_id TEXT,
            abha_id TEXT DEFAULT '',
            abha_address TEXT DEFAULT '',
            created_at TEXT
        )
    """)

    # Sessions
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            created_at TEXT
        )
    """)

    # Live HIS OPD Queue (triage, status, routing)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS his_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id TEXT UNIQUE NOT NULL,
            abha_id TEXT DEFAULT '',
            patient_name TEXT DEFAULT '',
            triage_level TEXT DEFAULT 'routine',
            red_flag INTEGER DEFAULT 0,
            red_flag_reasons TEXT DEFAULT '[]',
            chief_complaint TEXT DEFAULT '',
            status TEXT DEFAULT 'Waiting',
            pushed_to_his INTEGER DEFAULT 0,
            his_reference_id TEXT DEFAULT '',
            created_at TEXT,
            updated_at TEXT
        )
    """)

    # DPDP Act 2023 Compliance & Security Audit Logs
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS dpdp_audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            action TEXT NOT NULL,
            patient_id TEXT,
            abha_id TEXT,
            details TEXT
        )
    """)

    # Migrations for existing databases
    migrations = [
        ("records", "stored_filename", "TEXT"),
        ("records", "doc_type", "TEXT DEFAULT 'prescription'"),
        ("records", "abnormal_flags", "TEXT DEFAULT '[]'"),
        ("records", "drug_interactions", "TEXT DEFAULT '[]'"),
        ("records", "encounter_id", "INTEGER DEFAULT NULL"),
        ("intake", "socrates_json", "TEXT DEFAULT '{}'"),
        ("intake", "ros_json", "TEXT DEFAULT '{}'"),
        ("intake", "triage_level", "TEXT DEFAULT 'routine'"),
        ("intake", "consent_dpdp", "INTEGER DEFAULT 1"),
        ("intake", "consent_scope", "TEXT DEFAULT 'clinical_history,document_ocr,his_abdm_sharing'"),
        ("intake", "consent_timestamp", "TEXT"),
        ("intake", "audio_consent_listened", "INTEGER DEFAULT 0"),
        ("intake", "abha_id", "TEXT DEFAULT ''"),
        ("intake", "language", "TEXT DEFAULT 'en'"),
        ("summaries", "patient_lang_summary", "TEXT DEFAULT ''"),
        ("summaries", "doctor_notes", "TEXT DEFAULT ''"),
        ("summaries", "approved_by", "TEXT DEFAULT ''"),
        ("summaries", "approved_at", "TEXT"),
        ("summaries", "fhir_bundle", "TEXT DEFAULT ''"),
        ("summaries", "his_push_status", "TEXT DEFAULT 'pending'"),
        ("users", "abha_id", "TEXT DEFAULT ''"),
        ("users", "abha_address", "TEXT DEFAULT ''"),
    ]

    for table, col, col_type in migrations:
        try:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}")
        except sqlite3.OperationalError:
            pass  # column already exists

    # Migrate intake table if it has patient_id as PRIMARY KEY instead of id
    try:
        cursor.execute("PRAGMA table_info(intake)")
        intake_info = cursor.fetchall()
        id_col = next((c for c in intake_info if c[1] == 'id'), None)
        if not id_col or any(c[1] == 'patient_id' and c[5] == 1 for c in intake_info):
            cursor.execute("""
                CREATE TABLE intake_v2 (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    patient_id TEXT NOT NULL,
                    chief_complaint TEXT,
                    present_illness TEXT,
                    past_history TEXT,
                    medications TEXT,
                    allergies TEXT,
                    family_history TEXT,
                    lifestyle TEXT,
                    prakriti TEXT,
                    vikriti TEXT,
                    agni TEXT,
                    ahara_vihara TEXT,
                    dashavidha_pariksha TEXT,
                    socrates_json TEXT DEFAULT '{}',
                    ros_json TEXT DEFAULT '{}',
                    triage_level TEXT DEFAULT 'routine',
                    red_flag INTEGER DEFAULT 0,
                    red_flag_reasons TEXT DEFAULT '[]',
                    consent_dpdp INTEGER DEFAULT 1,
                    consent_scope TEXT DEFAULT 'clinical_history,document_ocr,his_abdm_sharing',
                    consent_timestamp TEXT,
                    audio_consent_listened INTEGER DEFAULT 0,
                    abha_id TEXT DEFAULT '',
                    language TEXT DEFAULT 'en',
                    submitted_at TEXT
                )
            """)
            cursor.execute("""
                INSERT INTO intake_v2 (
                    patient_id, chief_complaint, present_illness, past_history, medications,
                    allergies, family_history, lifestyle, prakriti, vikriti, agni, ahara_vihara,
                    dashavidha_pariksha, socrates_json, ros_json, triage_level, red_flag,
                    red_flag_reasons, consent_dpdp, consent_scope, consent_timestamp,
                    audio_consent_listened, abha_id, language, submitted_at
                )
                SELECT
                    patient_id, chief_complaint, present_illness, past_history, medications,
                    allergies, family_history, lifestyle, prakriti, vikriti, agni, ahara_vihara,
                    dashavidha_pariksha,
                    COALESCE(socrates_json, '{}'),
                    COALESCE(ros_json, '{}'),
                    COALESCE(triage_level, 'routine'),
                    COALESCE(red_flag, 0),
                    COALESCE(red_flag_reasons, '[]'),
                    COALESCE(consent_dpdp, 1),
                    COALESCE(consent_scope, 'clinical_history,document_ocr,his_abdm_sharing'),
                    consent_timestamp,
                    COALESCE(audio_consent_listened, 0),
                    COALESCE(abha_id, ''),
                    COALESCE(language, 'en'),
                    submitted_at
                FROM intake
            """)
            cursor.execute("DROP TABLE intake")
            cursor.execute("ALTER TABLE intake_v2 RENAME TO intake")
    except Exception as e:
        print(f"Warning during intake table migration: {e}")

    conn.commit()
    conn.close()

    # Seed historical patient records
    seed_patient_history()


def save_record(patient_id: str, source_filename: str, stored_filename: str, extracted: dict, doc_type: str = "prescription", encounter_id: int = None):
    """
    Saves an extracted document's structured data along with abnormal value tags, drug interactions, and optional encounter_id link.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    abnormal_flags = extracted.get("abnormal_flags", [])
    drug_interactions = extracted.get("drug_interactions", [])

    cursor.execute("""
        INSERT INTO records
        (patient_id, record_date, source_filename, stored_filename, doc_type, diagnoses, medications, investigations, procedures, abnormal_flags, drug_interactions, raw_json, encounter_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        patient_id,
        extracted.get("record_date", "unknown"),
        source_filename,
        stored_filename,
        doc_type or extracted.get("doc_type", "prescription"),
        json.dumps(extracted.get("diagnoses", [])),
        json.dumps(extracted.get("medications", [])),
        json.dumps(extracted.get("investigations", [])),
        json.dumps(extracted.get("procedures", [])),
        json.dumps(abnormal_flags),
        json.dumps(drug_interactions),
        json.dumps(extracted),
        encounter_id,
    ))
    conn.commit()
    conn.close()

    log_dpdp_action(
        "DOCUMENT_DIGITIZED",
        patient_id=patient_id,
        abha_id=extracted.get("abha_id", ""),
        details=f"Digitized {doc_type}: {source_filename} with {len(abnormal_flags)} abnormal flags",
    )


def list_patients():
    """
    Returns every distinct patient ID that has a document record, submitted intake, or HIS queue entry.
    Tagged with triage_level, latest date, and unresolved red flag.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            p.patient_id,
            (SELECT MAX(record_date) FROM records WHERE patient_id = p.patient_id) as latest,
            (SELECT COUNT(*) FROM records WHERE patient_id = p.patient_id) as record_count,
            COALESCE((SELECT red_flag FROM intake WHERE patient_id = p.patient_id), 0) as red_flag,
            COALESCE((SELECT triage_level FROM intake WHERE patient_id = p.patient_id), 'routine') as triage_level,
            COALESCE((SELECT abha_id FROM intake WHERE patient_id = p.patient_id), '') as abha_id,
            COALESCE((SELECT full_name FROM users WHERE patient_id = p.patient_id), '') as full_name
        FROM (
            SELECT patient_id FROM records
            UNION
            SELECT patient_id FROM intake
            UNION
            SELECT patient_id FROM his_queue
        ) p
        ORDER BY
            CASE
                WHEN red_flag = 1 OR triage_level = 'emergency' THEN 1
                WHEN triage_level = 'urgent' THEN 2
                ELSE 3
            END ASC,
            (latest IS NULL), latest DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    return [
        {
            "patient_id": r[0],
            "latest_record_date": r[1] or "no records yet",
            "record_count": r[2],
            "red_flag": bool(r[3]),
            "triage_level": r[4] or "routine",
            "abha_id": r[5] or "",
            "full_name": r[6] or "",
        }
        for r in rows
    ]


def get_timeline(patient_id: str):
    """Returns all records for a patient, sorted by date ASC."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT record_date, source_filename, stored_filename, doc_type, diagnoses, medications, investigations, procedures, abnormal_flags, drug_interactions
        FROM records
        WHERE patient_id = ?
        ORDER BY record_date ASC
    """, (patient_id,))
    rows = cursor.fetchall()
    conn.close()

    timeline = []
    for row in rows:
        timeline.append({
            "record_date": row[0],
            "source_filename": row[1],
            "stored_filename": row[2],
            "doc_type": row[3] or "prescription",
            "diagnoses": json.loads(row[4] or "[]"),
            "medications": json.loads(row[5] or "[]"),
            "investigations": json.loads(row[6] or "[]"),
            "procedures": json.loads(row[7] or "[]"),
            "abnormal_flags": json.loads(row[8] or "[]"),
            "drug_interactions": json.loads(row[9] or "[]"),
        })
    return timeline


def get_patient_full_history(patient_id: str, abha_id: str = "") -> dict:
    """
    Returns unified prior medical history for a patient, matching by patient_id
    or associated ABHA ID.
    Includes:
      - Digitized prescriptions and lab investigation reports (from 'records')
      - Prior clinical consultations (from 'intake')
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Find all patient_ids linked to this patient_id or abha_id
    linked_ids = {patient_id} if patient_id else set()
    if abha_id:
        cursor.execute("SELECT patient_id FROM users WHERE abha_id = ?", (abha_id,))
        for r in cursor.fetchall():
            if r[0]:
                linked_ids.add(r[0])
        cursor.execute("SELECT patient_id FROM intake WHERE abha_id = ?", (abha_id,))
        for r in cursor.fetchall():
            if r[0]:
                linked_ids.add(r[0])

    if not linked_ids:
        conn.close()
        return {
            "patient_id": patient_id,
            "abha_id": abha_id,
            "total_documents": 0,
            "total_consultations": 0,
            "documents": [],
            "past_consultations": [],
        }

    placeholders = ",".join(["?"] * len(linked_ids))
    params = list(linked_ids)

    # 1. Fetch documents/records
    cursor.execute(f"""
        SELECT id, patient_id, record_date, source_filename, stored_filename, doc_type,
               diagnoses, medications, investigations, procedures, abnormal_flags, drug_interactions,
               encounter_id
        FROM records
        WHERE patient_id IN ({placeholders})
        ORDER BY record_date DESC, id DESC
    """, params)
    record_rows = cursor.fetchall()

    documents = []
    for row in record_rows:
        documents.append({
            "id": row[0],
            "patient_id": row[1],
            "record_date": row[2] or "Unknown date",
            "source_filename": row[3],
            "stored_filename": row[4],
            "doc_type": row[5] or "prescription",
            "diagnoses": json.loads(row[6] or "[]"),
            "medications": json.loads(row[7] or "[]"),
            "investigations": json.loads(row[8] or "[]"),
            "procedures": json.loads(row[9] or "[]"),
            "abnormal_flags": json.loads(row[10] or "[]"),
            "drug_interactions": json.loads(row[11] or "[]"),
            "encounter_id": row[12] if len(row) > 12 else None,
        })

    # 2. Fetch past intake consultations
    cursor.execute(f"""
        SELECT id, patient_id, chief_complaint, present_illness, past_history, medications,
               allergies, triage_level, red_flag, submitted_at, abha_id
        FROM intake
        WHERE patient_id IN ({placeholders})
        ORDER BY submitted_at DESC, id DESC
    """, params)
    intake_rows = cursor.fetchall()

    past_consultations = []
    for r in intake_rows:
        past_consultations.append({
            "id": r[0],
            "patient_id": r[1],
            "chief_complaint": r[2] or "",
            "present_illness": r[3] or "",
            "past_history": r[4] or "",
            "medications": r[5] or "",
            "allergies": r[6] or "",
            "triage_level": r[7] or "routine",
            "red_flag": bool(r[8]),
            "submitted_at": r[9] or "",
            "abha_id": r[10] or "",
        })

    # 3. Build unified encounters: each past consultation bundles its respective lab reports and prescriptions
    encounters = []
    assigned_doc_ids = set()

    def is_clinically_matched(c, d):
        # 1. Direct explicit encounter link (Strict: if set, only match that encounter)
        if d.get("encounter_id"):
            return d.get("encounter_id") == c.get("id")

        # 2. Exact clinical date match
        c_date = (c.get("submitted_at") or "")[:10]
        d_date = (d.get("record_date") or "")[:10]
        if c_date and d_date and c_date == d_date:
            return True

        # 3. Clinical condition keyword correlation based on chief complaint / present illness
        c_complaint = f"{c.get('chief_complaint', '')} {c.get('present_illness', '')}".lower()
        d_text = f"{' '.join(d.get('diagnoses', []))} {d.get('source_filename', '')}".lower()

        # Diabetes / metabolic match
        if any(w in c_complaint for w in ("diabet", "sugar", "metabolic", "insulin")) and \
           any(w in d_text for w in ("diabet", "sugar", "accuris", "pathology", "hba1c")):
            return True
        # Cardiac / hypertension / lipid match
        if any(w in c_complaint for w in ("cardiac", "hypertens", "bp", "dyspnea", "lipid", "cholesterol")) and \
           any(w in d_text for w in ("cardiac", "lipid", "hypertens", "ecg", "cholesterol")):
            return True
        # Respiratory / pharyngitis / swab match
        if any(w in c_complaint for w in ("throat", "cough", "cold", "pharyngitis", "rhinitis", "respiratory")) and \
           any(w in d_text for w in ("respiratory", "cbc", "swab", "pharyngitis", "rhinitis")):
            return True
        return False

    for idx, c in enumerate(past_consultations):
        c_date = (c.get("submitted_at") or "")[:10]
        attached_docs = []
        for d in documents:
            if d["id"] not in assigned_doc_ids:
                if is_clinically_matched(c, d):
                    attached_docs.append(d)
                    assigned_doc_ids.add(d["id"])

        encounters.append({
            "encounter_id": f"enc_{c.get('id', idx)}",
            "type": "opd_consultation",
            "date": c_date or "Previous Visit",
            "chief_complaint": c.get("chief_complaint") or "Routine Clinical Consultation",
            "present_illness": c.get("present_illness", ""),
            "past_history": c.get("past_history", ""),
            "medications": c.get("medications", ""),
            "allergies": c.get("allergies", ""),
            "triage_level": c.get("triage_level", "routine"),
            "documents": attached_docs,
        })

    # Any documents not associated with an intake consultation appear as standalone diagnostic encounters
    for d in documents:
        if d["id"] not in assigned_doc_ids:
            encounters.append({
                "encounter_id": f"doc_{d['id']}",
                "type": "diagnostic_record",
                "date": d.get("record_date") or "Diagnostic Record",
                "chief_complaint": f"Diagnostic Investigation ({d.get('doc_type', 'lab_report')})",
                "present_illness": "",
                "past_history": ", ".join(d.get("diagnoses", [])),
                "medications": ", ".join([m.get("name") if isinstance(m, dict) else str(m) for m in d.get("medications", [])]),
                "allergies": "",
                "triage_level": "routine",
                "documents": [d],
            })

    conn.close()

    return {
        "patient_id": patient_id,
        "abha_id": abha_id,
        "total_documents": len(documents),
        "total_consultations": len(past_consultations),
        "total_encounters": len(encounters),
        "documents": documents,
        "past_consultations": past_consultations,
        "encounters": encounters,
    }


INTAKE_FIELDS = [
    "chief_complaint", "present_illness", "past_history", "medications",
    "allergies", "family_history", "lifestyle", "prakriti", "vikriti",
    "agni", "ahara_vihara", "dashavidha_pariksha",
]


def save_intake(
    patient_id: str,
    fields: dict,
    red_flag: bool,
    red_flag_reasons: list,
    triage_level: str = "routine",
    socrates: dict = None,
    ros: dict = None,
    consent_info: dict = None,
    abha_id: str = "",
    language: str = "en",
):
    """
    Saves self-reported intake, SOCRATES history, AYUSH exam, and DPDP consent.
    Automatically updates the hospital triage queue.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    consent_info = consent_info or {}
    socrates_json = json.dumps(socrates or {})
    ros_json = json.dumps(ros or {})
    reasons_json = json.dumps(red_flag_reasons or [])

    # Fetch patient's full name from users if registered
    cursor.execute("SELECT full_name, abha_id FROM users WHERE patient_id = ?", (patient_id,))
    user_row = cursor.fetchone()
    patient_name = user_row[0] if user_row else patient_id
    linked_abha = abha_id or (user_row[1] if user_row else "")

    values = [fields.get(f, "") for f in INTAKE_FIELDS]
    now_iso = datetime.now().isoformat()

    cursor.execute(f"""
        INSERT INTO intake (
            patient_id, {', '.join(INTAKE_FIELDS)},
            socrates_json, ros_json, triage_level, red_flag, red_flag_reasons,
            consent_dpdp, consent_scope, consent_timestamp, audio_consent_listened,
            abha_id, language, submitted_at
        )
        VALUES (?, {', '.join(['?'] * len(INTAKE_FIELDS))}, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, [
        patient_id,
        *values,
        socrates_json,
        ros_json,
        triage_level,
        int(red_flag),
        reasons_json,
        int(consent_info.get("consent_dpdp", 1)),
        consent_info.get("consent_scope", "clinical_history,document_ocr,his_abdm_sharing"),
        consent_info.get("consent_timestamp", now_iso),
        int(consent_info.get("audio_consent_listened", 0)),
        linked_abha,
        language,
        now_iso,
    ])

    # Sync into live HIS Queue
    queue_status = "Triaged" if red_flag or triage_level in ("emergency", "urgent") else "Waiting"
    cursor.execute("""
        INSERT INTO his_queue (
            patient_id, abha_id, patient_name, triage_level, red_flag, red_flag_reasons,
            chief_complaint, status, pushed_to_his, his_reference_id, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, '', ?, ?)
        ON CONFLICT(patient_id) DO UPDATE SET
            abha_id=excluded.abha_id,
            patient_name=excluded.patient_name,
            triage_level=excluded.triage_level,
            red_flag=excluded.red_flag,
            red_flag_reasons=excluded.red_flag_reasons,
            chief_complaint=excluded.chief_complaint,
            status=excluded.status,
            updated_at=excluded.updated_at
    """, (
        patient_id,
        linked_abha,
        patient_name,
        triage_level,
        int(red_flag),
        reasons_json,
        fields.get("chief_complaint", ""),
        queue_status,
        now_iso,
        now_iso,
    ))

    conn.commit()
    conn.close()

    log_dpdp_action(
        "INTAKE_SUBMITTED",
        patient_id=patient_id,
        abha_id=linked_abha,
        details=f"Intake completed with triage: {triage_level}. Red flag: {red_flag}. Consent granted under DPDP Act 2023.",
    )


def get_intake(patient_id: str):
    """Returns the intake dict for a patient with all extended fields, or None."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(f"""
        SELECT {', '.join(INTAKE_FIELDS)}, red_flag, red_flag_reasons, submitted_at,
               socrates_json, ros_json, triage_level, consent_dpdp, consent_scope,
               consent_timestamp, audio_consent_listened, abha_id, language
        FROM intake WHERE patient_id = ?
        ORDER BY id DESC LIMIT 1
    """, (patient_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None

    idx = len(INTAKE_FIELDS)
    result = dict(zip(INTAKE_FIELDS, row[:idx]))
    result["red_flag"] = bool(row[idx])
    result["red_flag_reasons"] = json.loads(row[idx + 1] or "[]")
    result["submitted_at"] = row[idx + 2]
    result["socrates"] = json.loads(row[idx + 3] or "{}")
    result["ros"] = json.loads(row[idx + 4] or "{}")
    result["triage_level"] = row[idx + 5] or "routine"
    result["consent_dpdp"] = bool(row[idx + 6])
    result["consent_scope"] = row[idx + 7] or ""
    result["consent_timestamp"] = row[idx + 8] or ""
    result["audio_consent_listened"] = bool(row[idx + 9])
    result["abha_id"] = row[idx + 10] or ""
    result["language"] = row[idx + 11] or "en"
    return result


def save_summary(
    patient_id: str,
    summary_text: str,
    patient_lang_summary: str = "",
    doctor_notes: str = "",
    approved: bool = False,
    approved_by: str = "",
    fhir_bundle: dict = None,
    his_push_status: str = "pending",
):
    """Saves or updates clinical summary, patient explanation, and FHIR bundle."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    now_iso = datetime.now().isoformat()
    approved_at = now_iso if approved else None

    cursor.execute("""
        INSERT INTO summaries (
            patient_id, summary_text, patient_lang_summary, doctor_notes,
            approved, approved_by, approved_at, fhir_bundle, his_push_status, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(patient_id) DO UPDATE SET
            summary_text=excluded.summary_text,
            patient_lang_summary=excluded.patient_lang_summary,
            doctor_notes=excluded.doctor_notes,
            approved=excluded.approved,
            approved_by=excluded.approved_by,
            approved_at=COALESCE(excluded.approved_at, summaries.approved_at),
            fhir_bundle=excluded.fhir_bundle,
            his_push_status=excluded.his_push_status,
            updated_at=excluded.updated_at
    """, (
        patient_id,
        summary_text,
        patient_lang_summary,
        doctor_notes,
        int(approved),
        approved_by,
        approved_at,
        json.dumps(fhir_bundle or {}) if fhir_bundle else "",
        his_push_status,
        now_iso,
    ))
    conn.commit()
    conn.close()


def get_summary(patient_id: str):
    """Returns the clinical summary record or None."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT summary_text, patient_lang_summary, doctor_notes, approved,
               approved_by, approved_at, fhir_bundle, his_push_status, updated_at
        FROM summaries WHERE patient_id = ?
    """, (patient_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None

    fhir = {}
    if row[6]:
        try:
            fhir = json.loads(row[6])
        except Exception:
            pass

    return {
        "summary_text": row[0],
        "patient_lang_summary": row[1] or "",
        "doctor_notes": row[2] or "",
        "approved": bool(row[3]),
        "approved_by": row[4] or "",
        "approved_at": row[5] or "",
        "fhir_bundle": fhir,
        "his_push_status": row[7] or "pending",
        "updated_at": row[8],
    }


def get_his_queue():
    """
    Returns the real-time OPD patient queue ordered by triage urgency.
    Emergency level patients appear first, followed by urgent, then routine.
    Includes summary approval and his push status.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT h.patient_id, h.abha_id, h.patient_name, h.triage_level, h.red_flag,
               h.red_flag_reasons, h.chief_complaint, h.status, h.pushed_to_his, h.his_reference_id, h.created_at,
               s.approved, s.approved_by, s.approved_at, s.doctor_notes
        FROM his_queue h
        LEFT JOIN summaries s ON h.patient_id = s.patient_id
        ORDER BY
            CASE
                WHEN h.red_flag = 1 OR h.triage_level = 'emergency' THEN 1
                WHEN h.triage_level = 'urgent' THEN 2
                ELSE 3
            END ASC,
            h.created_at DESC
    """)
    rows = cursor.fetchall()
    conn.close()

    queue = []
    for r in rows:
        pushed = bool(r[8])
        approved = bool(r[11]) if r[11] is not None else False
        is_diagnosed = bool(pushed and approved)
        queue.append({
            "patient_id": r[0],
            "abha_id": r[1] or "",
            "patient_name": r[2] or r[0],
            "triage_level": r[3] or "routine",
            "red_flag": bool(r[4]),
            "red_flag_reasons": json.loads(r[5] or "[]"),
            "chief_complaint": r[6] or "",
            "status": "Diagnosed" if is_diagnosed else (r[7] or "Waiting"),
            "pushed_to_his": pushed,
            "his_reference_id": r[9] or "",
            "created_at": r[10] or "",
            "approved": approved,
            "approved_by": r[12] or "",
            "approved_at": r[13] or "",
            "doctor_notes": r[14] or "",
            "is_diagnosed": is_diagnosed,
        })
    return queue


def push_to_his(patient_id: str) -> dict:
    """
    Simulates HL7 / FHIR push to the Hospital Information System (HIS/EMR).
    Generates a reference ID and marks the status as pushed.
    """
    ref_id = f"HIS-EMR-{datetime.now().strftime('%Y%m')}-{secrets.token_hex(3).upper()}"
    now_iso = datetime.now().isoformat()

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE his_queue
        SET pushed_to_his = 1, his_reference_id = ?, status = 'Diagnosed', updated_at = ?
        WHERE patient_id = ?
    """, (ref_id, now_iso, patient_id))

    cursor.execute("""
        UPDATE summaries
        SET his_push_status = 'pushed', updated_at = ?
        WHERE patient_id = ?
    """, (now_iso, patient_id))

    conn.commit()
    conn.close()

    log_dpdp_action(
        "HIS_RECORD_PUSH",
        patient_id=patient_id,
        abha_id="",
        details=f"Clinical case successfully pushed to Hospital HIS/EMR with reference {ref_id}",
    )
    return {"status": "success", "his_reference_id": ref_id, "pushed_at": now_iso}


def update_queue_status(patient_id: str, status: str):
    """Updates status in his_queue (e.g., 'Waiting', 'In Consultation', 'Completed')."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE his_queue SET status = ?, updated_at = datetime('now') WHERE patient_id = ?", (status, patient_id))
    conn.commit()
    conn.close()


def log_dpdp_action(action: str, patient_id: str = "", abha_id: str = "", details: str = ""):
    """Logs security, consent, and access events for DPDP Act 2023 compliance audit."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO dpdp_audit_logs (timestamp, action, patient_id, abha_id, details)
            VALUES (?, ?, ?, ?, ?)
        """, (datetime.now().isoformat(), action, patient_id or "", abha_id or "", details or ""))
        conn.commit()
        conn.close()
    except Exception:
        pass


def get_dpdp_audit_logs(limit: int = 50):
    """Returns recent audit log entries for hospital compliance officers."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, timestamp, action, patient_id, abha_id, details FROM dpdp_audit_logs ORDER BY id DESC LIMIT ?", (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [
        {
            "id": r[0],
            "timestamp": r[1],
            "action": r[2],
            "patient_id": r[3],
            "abha_id": r[4],
            "details": r[5],
        }
        for r in rows
    ]


def purge_kiosk_session(token: str, patient_id: str):
    """
    DPDP Act 2023 session termination: deletes session tokens from the kiosk
    so that subsequent walk-in users cannot access prior health data.
    """
    delete_session(token)
    log_dpdp_action(
        "KIOSK_SESSION_TERMINATED",
        patient_id=patient_id,
        details="Temporary session data purged after patient submission",
    )


def seed_default_accounts():
    """
    Creates default staff accounts (doctor, admin) and sample walk-in patient.
    """
    import auth

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    count = cursor.fetchone()[0]
    conn.close()

    if count > 0:
        return

    for username, password, role, full_name in [
        ("doctor", "doctor123", "doctor", "Dr. A. Sharma (MD, Physician)"),
        ("admin", "admin123", "admin", "Hospital OPD Admin"),
    ]:
        digest, salt = auth.hash_password(password)
        create_user(username, digest, salt, role, full_name)


def seed_patient_history():
    """
    Ensures that authenticated patient 'chandra' (P7923 / ABHA: 14-8921-3310-7762)
    has a complete, realistic clinical history with 3 distinct past visits and their
    respective, clinically-matched diagnostic lab reports.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Check how many historical encounters chandra has
    cursor.execute("SELECT COUNT(*) FROM intake WHERE patient_id = 'P7923'")
    count = cursor.fetchone()[0]

    if count < 3:
        cursor.execute("DELETE FROM intake WHERE patient_id = 'P7923'")
        cursor.execute("DELETE FROM records WHERE patient_id = 'P7923'")

        # 1. Encounter 1 (2026-08-15): Type 2 Diabetes Review
        enc1_fields = {
            "chief_complaint": "Quarterly Type 2 Diabetes Review & Chronic Weakness",
            "present_illness": "Known Type 2 Diabetic for 4 years presenting for routine quarterly metabolic review. Reports generalized fatigue and mild lower leg cramping for 3 weeks. No polyuria or polydipsia.",
            "past_history": "Type 2 Diabetes Mellitus (dx 2022), Microcytic Anemia",
            "medications": "Metformin 500mg BD, Insulin Glargine 10 units at bedtime",
            "allergies": "No known drug allergies",
            "family_history": "Father had Type 2 Diabetes and Hypertension",
            "lifestyle": "Sedentary desk work, non-smoker, vegetarian diet",
            "prakriti": "Kapha-Pitta",
            "vikriti": "Kapha Vriddhi",
            "agni": "Manda Agni",
            "ahara_vihara": "Regular meal timings, low physical exercise",
            "dashavidha_pariksha": "Madhyama Bala, Vaya: Madhyama",
        }
        cursor.execute(f"""
            INSERT INTO intake (
                patient_id, {', '.join(INTAKE_FIELDS)},
                socrates_json, ros_json, triage_level, red_flag, red_flag_reasons,
                consent_dpdp, consent_scope, consent_timestamp, audio_consent_listened,
                abha_id, language, submitted_at
            )
            VALUES (?, {', '.join(['?'] * len(INTAKE_FIELDS))}, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            "P7923",
            *[enc1_fields.get(f, "") for f in INTAKE_FIELDS],
            json.dumps({"site": "Generalized", "onset": "Gradual over 3 weeks", "severity": "4/10"}),
            json.dumps({"constitutional": "Fatigue", "endocrine": "Polydipsia denied"}),
            "routine",
            0,
            "[]",
            1,
            "clinical_history,document_ocr,his_abdm_sharing",
            "2026-08-15T10:30:00",
            0,
            "14-8921-3310-7762",
            "en",
            "2026-08-15T10:30:00",
        ])
        enc1_id = cursor.lastrowid

        # Attach respective Pathology Report (sterling-accuris-pathology-sample-report-unlocked.pdf)
        cursor.execute("""
            INSERT INTO records (
                patient_id, record_date, source_filename, stored_filename, doc_type,
                diagnoses, medications, investigations, procedures, abnormal_flags,
                drug_interactions, raw_json, encounter_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "P7923",
            "2026-08-15",
            "sterling-accuris-pathology-sample-report-unlocked.pdf",
            "P7923_fd8b10a1.pdf",
            "lab_report",
            json.dumps(["Type 2 Diabetes Mellitus", "Microcytic Anemia"]),
            json.dumps([{"name": "Insulin Glargine", "dosage": "10 units HS", "duration": "ongoing"}, {"name": "Metformin", "dosage": "500mg BD", "duration": "ongoing"}]),
            json.dumps([
                {"test": "Fasting Blood Sugar", "value": "162 mg/dL", "reference_range": "70 - 99 mg/dL"},
                {"test": "HbA1c", "value": "7.8 %", "reference_range": "4.0 - 5.6 %"},
                {"test": "Hemoglobin", "value": "14.5 g/dL", "reference_range": "13.0 - 17.0 g/dL"},
            ]),
            json.dumps([]),
            json.dumps(["High Fasting Blood Sugar (162 mg/dL)", "Elevated HbA1c (7.8%)"]),
            json.dumps([]),
            json.dumps({"source": "NABL Accredited Pathology Laboratory"}),
            enc1_id,
        ))

        # 2. Encounter 2 (2026-08-28): Cardiology Follow-up & Hypertension
        enc2_fields = {
            "chief_complaint": "Cardiology Follow-up: Exertional Dyspnea & Hypertension Evaluation",
            "present_illness": "Patient presents with mild shortness of breath on climbing 2 flights of stairs for 10 days. Monitored BP in clinic 142/90 mmHg. No resting chest pain, palpitations, or pedal edema.",
            "past_history": "Essential Hypertension Stage 1, Hyperlipidemia",
            "medications": "Telmisartan 40mg OD, Atorvastatin 10mg HS",
            "allergies": "No known drug allergies",
            "family_history": "Maternal history of coronary artery disease",
            "lifestyle": "Moderate stress, salt restriction advised",
            "prakriti": "Vata-Pitta",
            "vikriti": "Vata Prakopa",
            "agni": "Vishama Agni",
            "ahara_vihara": "Low-sodium diet",
            "dashavidha_pariksha": "Madhyama Bala",
        }
        cursor.execute(f"""
            INSERT INTO intake (
                patient_id, {', '.join(INTAKE_FIELDS)},
                socrates_json, ros_json, triage_level, red_flag, red_flag_reasons,
                consent_dpdp, consent_scope, consent_timestamp, audio_consent_listened,
                abha_id, language, submitted_at
            )
            VALUES (?, {', '.join(['?'] * len(INTAKE_FIELDS))}, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            "P7923",
            *[enc2_fields.get(f, "") for f in INTAKE_FIELDS],
            json.dumps({"site": "Chest / Cardiovascular", "onset": "10 days ago with exertion", "severity": "3/10"}),
            json.dumps({"cardiovascular": "Exertional dyspnea", "respiratory": "No orthopnea"}),
            "routine",
            0,
            "[]",
            1,
            "clinical_history,document_ocr,his_abdm_sharing",
            "2026-08-28T11:15:00",
            0,
            "14-8921-3310-7762",
            "en",
            "2026-08-28T11:15:00",
        ])
        enc2_id = cursor.lastrowid

        # Attach respective Cardiac & Lipid Profile Report (cardiac-lipid-profile-ecg-report.pdf)
        cursor.execute("""
            INSERT INTO records (
                patient_id, record_date, source_filename, stored_filename, doc_type,
                diagnoses, medications, investigations, procedures, abnormal_flags,
                drug_interactions, raw_json, encounter_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "P7923",
            "2026-08-28",
            "cardiac-lipid-profile-ecg-report.pdf",
            "P7923_cardiac_lipid_ecg.pdf",
            "lab_report",
            json.dumps(["Essential Hypertension", "Dyslipidemia"]),
            json.dumps([{"name": "Telmisartan", "dosage": "40mg OD", "duration": "ongoing"}, {"name": "Atorvastatin", "dosage": "10mg HS", "duration": "ongoing"}]),
            json.dumps([
                {"test": "Total Cholesterol", "value": "224 mg/dL", "reference_range": "< 200 mg/dL"},
                {"test": "LDL Cholesterol", "value": "148 mg/dL", "reference_range": "< 100 mg/dL"},
                {"test": "Triglycerides", "value": "182 mg/dL", "reference_range": "< 150 mg/dL"},
                {"test": "Resting 12-Lead ECG", "value": "Normal sinus rhythm, 76 bpm", "reference_range": "Normal"},
            ]),
            json.dumps([]),
            json.dumps(["High Total Cholesterol (224 mg/dL)", "Elevated LDL (148 mg/dL)", "Elevated Triglycerides (182 mg/dL)"]),
            json.dumps([]),
            json.dumps({"source": "Apex Cardiology & Metabolic Center"}),
            enc2_id,
        ))

        # 3. Encounter 3 (2026-09-04): Acute Upper Respiratory & Pharyngitis
        enc3_fields = {
            "chief_complaint": "Acute Sore Throat, Persistent Dry Cough & Rhinorrhea",
            "present_illness": "Sudden onset dry hacking cough with scratchy sore throat and clear nasal discharge for 4 days. Mild low-grade fever on day 1 (99.8°F), afebrile since. Chest auscultation clear bilaterally.",
            "past_history": "Seasonal Allergic Rhinitis, Viral Pharyngitis",
            "medications": "Levocetirizine 5mg OD, Dextromethorphan Cough Syrup 10ml TDS",
            "allergies": "None reported",
            "family_history": "No familial pulmonary disease",
            "lifestyle": "Hydration maintained",
            "prakriti": "Kapha-Vata",
            "vikriti": "Kapha-Vata",
            "agni": "Manda Agni",
            "ahara_vihara": "Warm fluids and steam inhalation",
            "dashavidha_pariksha": "Madhyama Bala",
        }
        cursor.execute(f"""
            INSERT INTO intake (
                patient_id, {', '.join(INTAKE_FIELDS)},
                socrates_json, ros_json, triage_level, red_flag, red_flag_reasons,
                consent_dpdp, consent_scope, consent_timestamp, audio_consent_listened,
                abha_id, language, submitted_at
            )
            VALUES (?, {', '.join(['?'] * len(INTAKE_FIELDS))}, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            "P7923",
            *[enc3_fields.get(f, "") for f in INTAKE_FIELDS],
            json.dumps({"site": "Throat / Upper Respiratory", "onset": "4 days ago", "severity": "4/10"}),
            json.dumps({"ent": "Sore throat, rhinorrhea", "pulmonary": "Dry cough, lungs clear"}),
            "routine",
            0,
            "[]",
            1,
            "clinical_history,document_ocr,his_abdm_sharing",
            "2026-09-04T09:45:00",
            0,
            "14-8921-3310-7762",
            "en",
            "2026-09-04T09:45:00",
        ])
        enc3_id = cursor.lastrowid

        # Attach respective CBC & Respiratory Swab Report (cbc-respiratory-swab-report.pdf)
        cursor.execute("""
            INSERT INTO records (
                patient_id, record_date, source_filename, stored_filename, doc_type,
                diagnoses, medications, investigations, procedures, abnormal_flags,
                drug_interactions, raw_json, encounter_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "P7923",
            "2026-09-04",
            "cbc-respiratory-swab-report.pdf",
            "P7923_cbc_respiratory_swab.pdf",
            "lab_report",
            json.dumps(["Acute Viral Pharyngitis", "Allergic Rhinitis"]),
            json.dumps([{"name": "Levocetirizine", "dosage": "5mg OD", "duration": "5 days"}, {"name": "Dextromethorphan Syrup", "dosage": "10ml TDS", "duration": "5 days"}]),
            json.dumps([
                {"test": "Total Leukocyte Count (WBC)", "value": "7,800 /uL", "reference_range": "4,000 - 11,000 /uL"},
                {"test": "Absolute Neutrophil Count", "value": "4,500 /uL", "reference_range": "2,000 - 7,000 /uL"},
                {"test": "Platelet Count", "value": "235,000 /uL", "reference_range": "150,000 - 450,000 /uL"},
                {"test": "Rapid Throat Swab Culture", "value": "Negative for Strep pyogenes; normal flora", "reference_range": "Negative"},
            ]),
            json.dumps([]),
            json.dumps([]),
            json.dumps([]),
            json.dumps({"source": "AIIMS / Partner Diagnostic Laboratories"}),
            enc3_id,
        ))

        conn.commit()

    conn.close()


def create_user(username: str, password_hash: str, salt: str, role: str, full_name: str, patient_id: str = None, abha_id: str = "", abha_address: str = ""):
    """Creates a user account with optional ABHA link."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO users (username, password_hash, salt, role, full_name, patient_id, abha_id, abha_address, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
    """, (username, password_hash, salt, role, full_name, patient_id, abha_id, abha_address))
    conn.commit()
    conn.close()


def get_user_by_username(username: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, username, password_hash, salt, role, full_name, patient_id, abha_id, abha_address
        FROM users WHERE username = ?
    """, (username,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    return {
        "id": row[0], "username": row[1], "password_hash": row[2], "salt": row[3],
        "role": row[4], "full_name": row[5], "patient_id": row[6],
        "abha_id": row[7] or "", "abha_address": row[8] or "",
    }


def get_user_by_patient_id(patient_id: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, username, role, full_name, patient_id, abha_id, abha_address
        FROM users WHERE patient_id = ?
    """, (patient_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    return {
        "id": row[0], "username": row[1], "role": row[2], "full_name": row[3],
        "patient_id": row[4], "abha_id": row[5] or "", "abha_address": row[6] or "",
    }


def list_users():
    """For the admin panel — never includes password hashes."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT username, role, full_name, patient_id, abha_id, created_at FROM users ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()
    return [
        {"username": r[0], "role": r[1], "full_name": r[2], "patient_id": r[3], "abha_id": r[4] or "", "created_at": r[5]}
        for r in rows
    ]


def create_session(token: str, user_id: int, role: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO sessions (token, user_id, role, created_at) VALUES (?, ?, ?, datetime('now'))
    """, (token, user_id, role))
    conn.commit()
    conn.close()


def get_session(token: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT u.id, u.username, u.role, u.full_name, u.patient_id, u.abha_id
        FROM sessions s JOIN users u ON s.user_id = u.id
        WHERE s.token = ?
    """, (token,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    return {
        "id": row[0], "username": row[1], "role": row[2],
        "full_name": row[3], "patient_id": row[4], "abha_id": row[5] or "",
    }


def delete_session(token: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM sessions WHERE token = ?", (token,))
    conn.commit()
    conn.close()


def get_stats():
    """For admin statistics dashboard."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    stats = {}
    for label, query in [
        ("total_patients", "SELECT COUNT(DISTINCT patient_id) FROM (SELECT patient_id FROM records UNION SELECT patient_id FROM intake)"),
        ("total_records", "SELECT COUNT(*) FROM records"),
        ("total_red_flags", "SELECT COUNT(*) FROM intake WHERE red_flag = 1"),
        ("emergency_triage_count", "SELECT COUNT(*) FROM intake WHERE triage_level = 'emergency'"),
        ("total_abha_linked", "SELECT COUNT(DISTINCT abha_id) FROM intake WHERE abha_id != ''"),
        ("total_users", "SELECT COUNT(*) FROM users"),
        ("total_audit_events", "SELECT COUNT(*) FROM dpdp_audit_logs"),
    ]:
        try:
            cursor.execute(query)
            stats[label] = cursor.fetchone()[0]
        except Exception:
            stats[label] = 0
    conn.close()
    return stats


def reset_all_data():
    """Wipes patient data, intake, summaries, his_queue, and logs for demo resets."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    for table in ["records", "intake", "summaries", "his_queue", "dpdp_audit_logs"]:
        try:
            cursor.execute(f"DELETE FROM {table}")
        except Exception:
            pass
    conn.commit()
    conn.close()

