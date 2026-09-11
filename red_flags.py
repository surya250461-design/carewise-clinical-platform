"""
red_flags.py
------------
The problem statement asks for a "rule-based and AI-assisted red-flag
engine" that identifies potentially urgent symptoms and alerts staff,
WITHOUT making an autonomous diagnosis. That distinction matters: we
flag for human attention, we never tell the patient what's wrong.

Two layers, in order of trust:
1. Rule-based keyword matching — always runs, has zero dependency on
   any API being up, and is instantly explainable ("flagged because
   the patient wrote 'chest pain'"). This is the layer you can demo
   confidently even if the internet or an API key is being difficult.
2. AI-assisted second pass — optional. If it fails for any reason
   (API down, quota, whatever), we silently fall back to rule-based
   only. It should never be the reason the whole intake fails.
"""

import re

# Keyword -> (reason, triage_level: "emergency" | "urgent")
RED_FLAG_KEYWORDS = {
    # Emergency: Immediate resuscitation or critical triage alert
    "chest pain": ("Possible acute coronary syndrome / cardiac emergency", "emergency"),
    "heart attack": ("Possible myocardial infarction", "emergency"),
    "pain radiating to left arm": ("Cardiovascular emergency (angina/STEMI)", "emergency"),
    "pain radiating to jaw": ("Cardiovascular emergency", "emergency"),
    "crushing chest": ("Acute coronary syndrome indicator", "emergency"),
    "seene me dard": ("Cardiovascular emergency reported (Hindi)", "emergency"),
    "chhati dard": ("Chest pain reported", "emergency"),
    "difficulty breathing": ("Acute respiratory distress", "emergency"),
    "shortness of breath": ("Respiratory distress", "emergency"),
    "can't breathe": ("Severe respiratory compromise", "emergency"),
    "saans lene me takleef": ("Respiratory distress reported (Hindi)", "emergency"),
    "stridor": ("Upper airway obstruction emergency", "emergency"),
    "blue lips": ("Cyanosis / Hypoxia emergency", "emergency"),
    "severe bleeding": ("Uncontrolled acute hemorrhage", "emergency"),
    "heavy bleeding": ("Uncontrolled acute hemorrhage", "emergency"),
    "vomiting blood": ("Acute gastrointestinal bleeding (hematemesis)", "emergency"),
    "khun ki ulti": ("Hematemesis reported (Hindi)", "emergency"),
    "coughing up blood": ("Hemoptysis emergency", "emergency"),
    "blood in stool": ("Lower GI bleeding indicator", "urgent"),
    "black tarry stool": ("Melena / internal bleeding indicator", "urgent"),
    "loss of consciousness": ("Neurological emergency / syncope", "emergency"),
    "unconscious": ("Neurological emergency / coma", "emergency"),
    "fainted": ("Syncope / collapse", "urgent"),
    "seizure": ("Active neurological seizure", "emergency"),
    "convulsion": ("Neurological emergency", "emergency"),
    "sudden weakness": ("Acute stroke indicator (FAST protocol)", "emergency"),
    "one side of the body": ("Hemiparesis / stroke indicator", "emergency"),
    "slurred speech": ("Acute stroke indicator", "emergency"),
    "facial droop": ("Acute stroke indicator", "emergency"),
    "severe allergic reaction": ("Possible anaphylactic shock", "emergency"),
    "anaphylaxis": ("Life-threatening anaphylaxis", "emergency"),
    "swelling of the throat": ("Airway compromise / anaphylaxis", "emergency"),
    "poisoning": ("Toxicology emergency", "emergency"),
    "overdose": ("Toxicology emergency", "emergency"),
    "suicidal": ("Acute psychiatric emergency", "emergency"),
    "kill myself": ("Acute psychiatric emergency", "emergency"),
    "self harm": ("Acute psychiatric emergency", "emergency"),
    "self-harm": ("Acute psychiatric emergency", "emergency"),

    # Urgent: Attention required promptly
    "severe abdominal pain": ("Acute abdomen / surgical urgency", "urgent"),
    "pet me tezz dard": ("Severe abdominal pain reported", "urgent"),
    "high fever": ("Severe infection or systemic sepsis", "urgent"),
    "stiff neck with fever": ("Possible meningitis", "emergency"),
    "sudden loss of vision": ("Ophthalmic emergency", "emergency"),
    "persistent vomiting": ("Risk of severe dehydration / electrolyte collapse", "urgent"),
}


def check_keywords(text: str):
    """
    Rule-based pass. Returns a list of {"keyword": ..., "reason": ..., "level": ...}
    for every match found.
    """
    if not text:
        return []
    lowered = text.lower()
    matches = []
    for keyword, (reason, level) in RED_FLAG_KEYWORDS.items():
        if re.search(re.escape(keyword), lowered):
            matches.append({"keyword": keyword, "reason": reason, "level": level})
    return matches


def check_with_ai(text: str, call_llm_fn):
    """
    AI-assisted second pass for subtle clinical urgency descriptions.
    """
    if not text:
        return None

    prompt = f"""You are an emergency triage clinical assistant in an OPD kiosk. Read the patient's words below and assess the urgency level.

Categories:
- "emergency": Immediate life threat (chest pain, stroke symptoms, acute dyspnea, heavy bleeding, anaphylaxis, suicide).
- "urgent": Needs rapid physician evaluation within 30 minutes (severe acute pain, high fever, altered state).
- "routine": Standard non-critical complaints.

Return ONLY valid JSON:
{{"urgent": true or false, "level": "emergency" or "urgent" or "routine", "reason": "concise clinical concern"}}

Patient's words:
---
{text[:3000]}
---
"""
    try:
        raw = call_llm_fn(prompt).strip()
        raw = re.sub(r"^```(json)?|```$", "", raw, flags=re.MULTILINE).strip()
        import json
        result = json.loads(raw)
        if result.get("urgent") or result.get("level") in ("emergency", "urgent"):
            return {
                "reason": result.get("reason") or "Flagged by clinical triage check",
                "level": result.get("level", "urgent"),
            }
        return None
    except Exception:
        return None


def evaluate(chief_complaint: str, present_illness: str, call_llm_fn=None):
    """
    Runs both rule-based and AI triage passes.
    Returns (is_flagged: bool, reasons: list[str], triage_level: str).
    triage_level is 'emergency', 'urgent', or 'routine'.
    """
    combined_text = f"{chief_complaint or ''} {present_illness or ''}"
    matches = check_keywords(combined_text)

    reasons = []
    levels = ["routine"]

    for match in matches:
        reasons.append(match["reason"])
        levels.append(match["level"])

    if call_llm_fn is not None:
        ai_res = check_with_ai(combined_text, call_llm_fn)
        if ai_res:
            reason = f"{ai_res['reason']} (AI-assisted)"
            if reason not in reasons:
                reasons.append(reason)
            levels.append(ai_res["level"])

    # Determine highest severity level
    if "emergency" in levels:
        triage_level = "emergency"
    elif "urgent" in levels:
        triage_level = "urgent"
    else:
        triage_level = "routine"

    # de-duplicate reasons
    seen = set()
    unique_reasons = []
    for r in reasons:
        if r not in seen:
            seen.add(r)
            unique_reasons.append(r)

    is_flagged = len(unique_reasons) > 0
    return (is_flagged, unique_reasons, triage_level)

