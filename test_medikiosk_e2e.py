import os
import sys
import io

sys.stdout.reconfigure(encoding='utf-8')

# Add workspace to path
workspace_dir = r"c:\Users\SURYA\Desktop\patient-case-taking"
if workspace_dir not in sys.path:
    sys.path.insert(0, workspace_dir)

from starlette.testclient import TestClient
import main
import database
import auth

client = TestClient(main.app)

def test_full_pipeline():
    print("========================================")
    print("STARTING STARBUCKS END-TO-END VERIFICATION")
    print("========================================")

    # 0. Test Admin Login and Stats
    print("\n--- [Step 0] Admin Authentication & Stats ---")
    admin_login = client.post("/auth/login", json={"username": "admin", "password": "admin123"})
    assert admin_login.status_code == 200, f"Admin login failed: {admin_login.text}"
    admin_cookie = admin_login.cookies
    print("[PASS] Admin logged in successfully")

    stats = client.get("/admin/stats", cookies=admin_cookie)
    assert stats.status_code == 200
    print("[PASS] Admin stats retrieved:", stats.json())

    # 1. Module D & Auth: ABHA Verification for Walk-in Patient
    print("\n--- [Step 1] Module D: ABHA Walk-in & OTP Verification ---")
    abha_payload = {
        "abha_id": "91-4523-8819-2041",
        "full_name": "Ramesh Chandra",
        "otp": "123456"
    }
    abha_res = client.post("/auth/abha-verify", json=abha_payload)
    assert abha_res.status_code == 200, f"ABHA verify failed: {abha_res.text}"
    patient_data = abha_res.json()
    patient_id = patient_data["patient_id"]
    patient_cookie = abha_res.cookies
    print(f"[PASS] ABHA Verified: {patient_data['abha_id']} -> Assigned Patient ID: {patient_id}")

    # 2. Module D: DPDP Act 2023 Explicit Consent
    print("\n--- [Step 2] Module D: DPDP Act 2023 Consent Recording ---")
    consent_payload = {
        "patient_id": patient_id,
        "consent_scope": "clinical_history_taking_and_abdm_sharing",
        "audio_consent_listened": True
    }
    consent_res = client.post("/api/patient/consent", json=consent_payload, cookies=patient_cookie)
    assert consent_res.status_code == 200
    print("[PASS] DPDP 2023 Consent recorded with audit trail")

    # 3. Module A: Conversational SOCRATES Adaptive Engine
    print("\n--- [Step 3] Module A: Adaptive SOCRATES Questioning ---")
    socrates_payload = {
        "chief_complaint": "Severe retrosternal chest pain radiating to left arm",
        "answers_so_far": {
            "site": "center of chest",
            "onset": "sudden 2 hours ago"
        },
        "language": "en"
    }
    probe_res = client.post("/api/converse/next-question", json=socrates_payload)
    assert probe_res.status_code == 200
    probe_data = probe_res.json()
    q_val = probe_data.get("question") or probe_data.get("question_text")
    print(f"[PASS] SOCRATES Probe Generated: [{probe_data['dimension'].upper()}] - {q_val}")
    print(f"  Touch Quick Options: {probe_data.get('options', [])}")

    # 4. Module A: Patient Intake Submission (with Emergency Red Flags & AYUSH)
    print("\n--- [Step 4] Module A: Intake Submission with Red Flags & Dashavidha Pariksha ---")
    intake_payload = {
        "chief_complaint": "Acute severe crushing chest pain, radiating to left arm, shortness of breath, and profuse cold sweating",
        "present_illness": "Started suddenly 2 hours ago at rest, worsening over time with nausea and diaphoresis",
        "past_history": "Hypertension for 5 years, Type 2 Diabetes Mellitus for 3 years",
        "medications": "Amlodipine 5mg, Metformin 500mg, Warfarin 2mg daily",
        "allergies": "Penicillin (rash)",
        "family_history": "Father had MI at age 52",
        "lifestyle": "Sedentary, former smoker",
        "prakriti": "Pitta-Vata",
        "vikriti": "Vata-Kapha vitiation with Hridroga lakshanas",
        "agni": "Mandagni",
        "ahara_vihara": "Irregular meal timings, high salt and oily diet",
        "dashavidha_pariksha": "Dushya: Rasa and Rakta; Desha: Sadharana; Bala: Madhyama; Kala: Sheeta; Sara: Madhyama; Samhanana: Madhyama; Pramana: Madhyama; Satmya: Katu-Lavana; Satwa: Avara; Ahara-shakti: Avara",
        "socrates": {
            "site": "Retrosternal",
            "onset": "Sudden",
            "character": "Crushing / pressure",
            "radiation": "Left arm and jaw",
            "associations": "Shortness of breath, sweating, nausea",
            "time_course": "Continuous 2 hours",
            "exacerbating": "No relief with rest",
            "severity": "9/10"
        },
        "ros": {
            "cardiovascular": "Severe chest pain, palpitations",
            "respiratory": "Dyspnea on minimal exertion",
            "neurological": "No focal weakness"
        },
        "consent_info": {
            "dpdp_consented": True,
            "scope": "opd_consultation",
            "audio_played": True
        },
        "abha_id": "91-4523-8819-2041",
        "language": "en"
    }

    intake_res = client.post(f"/intake/{patient_id}", json=intake_payload, cookies=patient_cookie)
    assert intake_res.status_code == 200, f"Intake submission failed: {intake_res.text}"
    intake_out = intake_res.json()
    print("[PASS] Intake submitted successfully")
    print(f"  Emergency Red Flag Detected: {intake_out['red_flag']}")
    print(f"  Triage Level Assigned: {intake_out['triage_level'].upper()}")
    print(f"  Red Flag Reasons: {intake_out['red_flag_reasons']}")
    assert intake_out["red_flag"] is True, "Emergency red flag should be True for crushing chest pain!"
    assert intake_out["triage_level"] == "emergency", f"Expected triage 'emergency', got '{intake_out['triage_level']}'"

    # 5. Module B: Document Digitization, Abnormal Lab Value & Drug Interaction Extraction
    print("\n--- [Step 5] Module B: Document OCR, Abnormal Lab Values & Drug Interaction Screening ---")
    simulated_report = """
    CENTRAL HOSPITAL CLINICAL LAB & PRESCRIPTION
    Patient Name: Ramesh Chandra | Date: 2026-09-08
    
    DIAGNOSES:
    - Acute Coronary Syndrome (Suspected NSTEMI)
    - Uncontrolled Type 2 Diabetes Mellitus
    
    INVESTIGATIONS:
    - HbA1c: 9.4 % (Ref: <5.7 normal, >6.5 diabetic)
    - Fasting Blood Sugar: 215 mg/dL (Ref: 70-99)
    - Serum Creatinine: 2.1 mg/dL (Ref: 0.7-1.3)
    - Troponin-I: 1.85 ng/mL (Ref: <0.04)
    - Hemoglobin: 13.8 g/dL (Ref: 13.0-17.0)
    
    CURRENT RX MEDICATIONS:
    - Aspirin 150 mg OD
    - Warfarin 5 mg OD
    - Metformin 1000 mg BD
    - Atorvastatin 40 mg HS
    
    PROCEDURES:
    - 12-lead Electrocardiogram (ECG) performed
    """

    doc_file = io.BytesIO(simulated_report.encode("utf-8"))
    upload_res = client.post(
        "/upload-case",
        data={"patient_id": patient_id, "doc_type": "lab_report"},
        files={"file": ("lab_report_2026.txt", doc_file, "text/plain")},
        cookies=admin_cookie
    )
    assert upload_res.status_code == 200, f"Document upload failed: {upload_res.text}"
    upload_out = upload_res.json()
    print("[PASS] Document successfully digitized and parsed")
    print(f"  Extracted Diagnoses: {upload_out['extracted']['diagnoses']}")
    print(f"  Abnormal Lab Value Flags: {upload_out.get('abnormal_flags', [])}")
    print(f"  Adverse Drug Interactions Detected: {upload_out.get('drug_interactions', [])}")

    assert len(upload_out.get("abnormal_flags", [])) > 0, "Expected abnormal lab flags!"
    assert len(upload_out.get("drug_interactions", [])) > 0, "Expected Aspirin + Warfarin drug interaction!"

    # 6. Module C: Physician Clinical Summary & Bilingual Regional Translation
    print("\n--- [Step 6] Module C: AI Structured Clinical Summary & Physician Approval ---")
    doctor_login = client.post("/auth/login", json={"username": "doctor", "password": "doctor123"})
    assert doctor_login.status_code == 200
    doctor_cookie = doctor_login.cookies

    summary_res = client.get(f"/summary/{patient_id}", cookies=doctor_cookie)
    assert summary_res.status_code == 200
    summary_data = summary_res.json()["summary"]
    print("[PASS] AI Generated Structured Clinical Summary:")
    print("--- Physician English Standard ---")
    print(summary_data["summary_text"][:300] + "...\n")
    print("--- Patient Plain-Language Briefing ---")
    print(summary_data["patient_lang_summary"][:200] + "...\n")

    # Physician edits and signs off
    edit_payload = {
        "summary_text": summary_data["summary_text"] + "\n[Dr. Sharma Note]: Patient prioritized for immediate Cath Lab / Cardiology consult.",
        "patient_lang_summary": summary_data["patient_lang_summary"],
        "doctor_notes": "Immediate ECG, aspirin withheld due to warfarin interaction, cardiology alerted.",
        "approved": True
    }
    update_res = client.put(f"/summary/{patient_id}", json=edit_payload, cookies=doctor_cookie)
    assert update_res.status_code == 200
    print("[PASS] Clinical summary signed and approved by Attending Physician")

    # 7. Module D: HL7 FHIR R4 Bundle Generation
    print("\n--- [Step 7] Module D: HL7 FHIR R4 Bundle Export ---")
    fhir_res = client.get(f"/api/fhir/{patient_id}", cookies=doctor_cookie)
    assert fhir_res.status_code == 200
    bundle = fhir_res.json()
    assert bundle["resourceType"] == "Bundle", "Expected FHIR Bundle"
    assert bundle["type"] == "document"
    resource_types = [entry["resource"]["resourceType"] for entry in bundle["entry"]]
    print("[PASS] HL7 FHIR R4 Bundle Generated successfully:")
    print(f"  Bundle ID: {bundle['id']}")
    print(f"  Included Resources: {set(resource_types)}")
    assert "Patient" in resource_types
    assert "Condition" in resource_types
    assert "MedicationStatement" in resource_types
    assert "Observation" in resource_types

    # 8. Module D: Live HIS OPD Triage Queue
    print("\n--- [Step 8] Module D: Live HIS OPD Queue Prioritization ---")
    queue_res = client.get("/api/his/queue", cookies=doctor_cookie)
    assert queue_res.status_code == 200
    queue = queue_res.json()["queue"]
    print(f"[PASS] Live HIS OPD Queue length: {len(queue)}")
    assert len(queue) > 0
    top_patient = queue[0]
    print(f"  Top Priority Queue Patient: {top_patient['patient_name']} (Triage: {top_patient['triage_level'].upper()})")
    assert top_patient["triage_level"] == "emergency", "Emergency patient must be at the top of the OPD queue!"

    # 9. Module D: Push to Hospital Information System (HIS / EMR)
    print("\n--- [Step 9] Module D: Push to HIS / EMR ---")
    push_res = client.post(f"/api/his/push/{patient_id}", cookies=doctor_cookie)
    assert push_res.status_code == 200
    push_data = push_res.json()
    print(f"[PASS] Pushed to HIS successfully. Reference ID: {push_data['his_reference_id']}")

    # 10. Module D: DPDP Act 2023 Kiosk Session Wipe & Audit Trail
    print("\n--- [Step 10] Module D: DPDP Session Wipe & Audit Log Verification ---")
    term_res = client.post("/api/patient/terminate-session", cookies=patient_cookie)
    assert term_res.status_code == 200
    print("[PASS] Kiosk session securely purged to prevent walk-in data leakage")

    audit_res = client.get("/admin/audit-logs", cookies=admin_cookie)
    assert audit_res.status_code == 200
    logs = audit_res.json()["audit_logs"]
    actions = [l["action"] for l in logs]
    print(f"[PASS] DPDP Audit Trail contains {len(logs)} recorded events:")
    for l in logs[:6]:
        print(f"   [{l['timestamp'][:19]}] {l['action']} - Patient: {l['patient_id']} - {l['details'][:60]}")

    assert "ABHA_AUTHENTICATED" in actions
    assert "DPDP_CONSENT_GRANTED" in actions
    assert "INTAKE_SUBMITTED" in actions
    assert "DOCUMENT_DIGITIZED" in actions
    assert "HIS_RECORD_PUSH" in actions
    assert "KIOSK_SESSION_TERMINATED" in actions

    print("\n========================================")
    print("ALL 10 VERIFICATION CHECKS PASSED WITH 100% SUCCESS!")
    print("========================================")

if __name__ == "__main__":
    test_full_pipeline()
