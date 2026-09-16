"""
consultation.py
---------------
Interactive Doctor-Patient Consultation Engine for Carewise.
Transforms step-by-step intake into an adaptive conversation:
1. Validates medical input (filters inappropriate, gibberish, and off-topic messages).
2. Generates dynamic, multi-turn doctor questions based on prior answers.
3. Produces specialized quick-response chips tailored to the specific health concern.
4. Extracts structured clinical telemetry (SOCRATES, history, medications, AYUSH).
5. Detects acute red flags and computes clinical history completeness.
"""

import re
import difflib
from typing import Dict, List, Any, Optional

import consultation_translations as ct

# -------------------------------------------------------------
# 1. Inappropriate & Invalid Input Detection
# -------------------------------------------------------------

NON_MEDICAL_PHRASES = {
    "hello", "hi", "hey", "hola", "namaste", "good morning", "good evening",
    "who are you", "what is your name", "tell me a joke", "are you ai", "are you robot",
    "football", "cricket", "movie", "pizza", "burger", "car", "bike", "money",
    "test", "testing", "asdf", "qwerty", "nothing", "ok", "okay", "bye", "goodbye",
    "google", "chatgpt", "gemini", "weather", "help"
}

PROFANITIES = {
    "fuck", "shit", "bitch", "bastard", "idiot", "stupid", "dumb", "hate",
    "chutiya", "madarchod", "bhosdike", "harami", "kutta", "gandu"
}

COMMON_MEDICAL_KEYWORDS = [
    # Cold & Respiratory
    "cold", "cough", "phlegm", "mucus", "sneeze", "sneezing", "runny nose", "congestion",
    "sore throat", "throat pain", "hoarseness", "wheeze", "wheezing", "breathless",
    "shortness of breath", "breathing", "saans", "khansi", "sardi", "jukham", "gala",
    "kaph", "bronchitis", "asthma", "pneumonia",
    # Fever & Infection
    "fever", "chills", "shivering", "high temp", "temperature", "sweats", "bukhar",
    "thand", "jwara", "dengue", "malaria", "typhoid", "infection", "viral",
    # Chest & Cardiac
    "chest pain", "chest pressure", "chest tightness", "chest heaviness", "crushing",
    "heart pain", "palpitation", "heart racing", "angina", "cardiac", "heart attack",
    "seene me dard", "chhati dard", "dil", "left arm pain", "radiating pain",
    # Gastro & Abdominal
    "stomach pain", "abdominal pain", "belly ache", "pet dard", "acidity", "heartburn",
    "gas", "bloating", "nausea", "vomit", "vomiting", "diarrhea", "loose motion",
    "constipation", "kabz", "dast", "ulti", "apach", "indigestion", "ulcer", "gerd",
    # Neuro & Head
    "headache", "migraine", "dizziness", "dizzy", "vertigo", "spinning", "lightheaded",
    "fainted", "unconscious", "blackout", "sar dard", "chakkar", "behoshi", "adhasisi",
    "numbness", "tingling", "weakness in face", "stroke",
    # Joints & Bones
    "joint pain", "knee pain", "back pain", "backache", "neck pain", "shoulder pain",
    "swelling", "stiffness", "arthritis", "gout", "uric acid", "guthna", "kamar dard",
    "jod dard", "sujan", "crepitus", "sciatica",
    # General / Chronic
    "diabetes", "sugar", "blood pressure", "hypertension", "bp", "fatigue", "tiredness",
    "weakness", "kamjori", "rash", "itching", "khujli", "allergy", "thyroid"
] + ct.MULTILINGUAL_MEDICAL_KEYWORDS

# -------------------------------------------------------------
# Medical Typo Auto-Correction Knowledgebase & Fuzzy Matcher
# -------------------------------------------------------------
CANONICAL_SYMPTOMS_MAP = {
    "cold": ("cold", "cold"),
    "cough": ("cough", "cold"),
    "runny nose": ("runny nose", "cold"),
    "sore throat": ("sore throat", "cold"),
    "sneezing": ("sneezing", "cold"),
    "fever": ("fever", "fever"),
    "chills": ("chills", "fever"),
    "shivering": ("shivering", "fever"),
    "chest pain": ("chest pain", "cardiac"),
    "chest tightness": ("chest tightness", "cardiac"),
    "heart pain": ("heart pain", "cardiac"),
    "palpitations": ("palpitations", "cardiac"),
    "shortness of breath": ("shortness of breath", "cardiac"),
    "breathlessness": ("breathlessness", "cardiac"),
    "stomach ache": ("stomach ache", "gastro"),
    "stomach pain": ("stomach pain", "gastro"),
    "abdominal pain": ("abdominal pain", "gastro"),
    "vomiting": ("vomiting", "gastro"),
    "nausea": ("nausea", "gastro"),
    "diarrhea": ("diarrhea", "gastro"),
    "loose motions": ("loose motions", "gastro"),
    "acidity": ("acidity", "gastro"),
    "indigestion": ("indigestion", "gastro"),
    "headache": ("headache", "neuro"),
    "migraine": ("migraine", "neuro"),
    "dizziness": ("dizziness", "neuro"),
    "vertigo": ("vertigo", "neuro"),
    "knee pain": ("knee pain", "ortho"),
    "joint pain": ("joint pain", "ortho"),
    "back pain": ("back pain", "ortho"),
    "body ache": ("body ache", "fever"),
    "weakness": ("weakness", "general"),
    "fatigue": ("fatigue", "general"),
    "tiredness": ("tiredness", "general"),
}

SYMPTOM_TYPO_MAP = {
    # Cold & Cough typos
    "cld": ("cold", "cold"),
    "clod": ("cold", "cold"),
    "codl": ("cold", "cold"),
    "cole": ("cold", "cold"),
    "cldd": ("cold", "cold"),
    "coldd": ("cold", "cold"),
    "cgf": ("cough", "cold"),
    "coug": ("cough", "cold"),
    "cogh": ("cough", "cold"),
    "coughh": ("cough", "cold"),
    "caugh": ("cough", "cold"),
    "cuff": ("cough", "cold"),
    "cugh": ("cough", "cold"),
    "khasi": ("cough", "cold"),
    "khansi": ("cough", "cold"),
    "sardi": ("cold", "cold"),
    "sali": ("cold", "cold"),
    "runy nos": ("runny nose", "cold"),
    "ronny nose": ("runny nose", "cold"),
    "runi nose": ("runny nose", "cold"),
    "sneez": ("sneezing", "cold"),
    "snezing": ("sneezing", "cold"),
    "throt": ("sore throat", "cold"),
    "sor throt": ("sore throat", "cold"),
    "sore throt": ("sore throat", "cold"),
    "phlegm": ("cough with phlegm", "cold"),
    "flegm": ("cough with phlegm", "cold"),

    # Fever & Chills typos
    "fvr": ("fever", "fever"),
    "fevr": ("fever", "fever"),
    "fevrr": ("fever", "fever"),
    "feverr": ("fever", "fever"),
    "febr": ("fever", "fever"),
    "febre": ("fever", "fever"),
    "bukhra": ("fever", "fever"),
    "bukhr": ("fever", "fever"),
    "bukhar": ("fever", "fever"),
    "kaychal": ("fever", "fever"),
    "kaichal": ("fever", "fever"),
    "chil": ("chills", "fever"),
    "chils": ("chills", "fever"),
    "shivr": ("shivering", "fever"),
    "shiverng": ("shivering", "fever"),
    "temprature": ("high temperature", "fever"),
    "tempratur": ("high temperature", "fever"),
    "temp": ("fever", "fever"),

    # Chest Pain & Cardiac typos
    "chst": ("chest pain", "cardiac"),
    "ches": ("chest pain", "cardiac"),
    "chst pain": ("chest pain", "cardiac"),
    "chset pain": ("chest pain", "cardiac"),
    "ches pain": ("chest pain", "cardiac"),
    "chestpain": ("chest pain", "cardiac"),
    "chect pain": ("chest pain", "cardiac"),
    "hart pain": ("heart pain", "cardiac"),
    "heartpain": ("heart pain", "cardiac"),
    "hart": ("heart pain", "cardiac"),
    "nenju vali": ("chest pain", "cardiac"),
    "nenju": ("chest pain", "cardiac"),
    "palpitasion": ("palpitations", "cardiac"),
    "palpitation": ("palpitations", "cardiac"),
    "brth": ("shortness of breath", "cardiac"),
    "breth": ("shortness of breath", "cardiac"),
    "brethless": ("breathlessness", "cardiac"),
    "shorness": ("shortness of breath", "cardiac"),
    "sort of breath": ("shortness of breath", "cardiac"),

    # Stomach / Gastro typos
    "stmch": ("stomach ache", "gastro"),
    "stomac": ("stomach ache", "gastro"),
    "stmc": ("stomach ache", "gastro"),
    "stomache": ("stomach ache", "gastro"),
    "stomc pain": ("stomach pain", "gastro"),
    "stomach pain": ("stomach pain", "gastro"),
    "belly pan": ("belly pain", "gastro"),
    "pet dard": ("stomach pain", "gastro"),
    "vayiru vali": ("stomach pain", "gastro"),
    "vayiru": ("stomach pain", "gastro"),
    "vomt": ("vomiting", "gastro"),
    "vomting": ("vomiting", "gastro"),
    "vomet": ("vomiting", "gastro"),
    "vometing": ("vomiting", "gastro"),
    "ulti": ("vomiting", "gastro"),
    "nause": ("nausea", "gastro"),
    "nausia": ("nausea", "gastro"),
    "diarhea": ("diarrhea", "gastro"),
    "diahrea": ("diarrhea", "gastro"),
    "diareha": ("diarrhea", "gastro"),
    "lose motion": ("loose motions", "gastro"),
    "loose motion": ("loose motions", "gastro"),
    "acydity": ("acidity", "gastro"),
    "aciditi": ("acidity", "gastro"),
    "gas prob": ("gastric problem", "gastro"),

    # Headache / Neuro typos
    "hedache": ("headache", "neuro"),
    "headac": ("headache", "neuro"),
    "hedach": ("headache", "neuro"),
    "headche": ("headache", "neuro"),
    "head pain": ("headache", "neuro"),
    "headpain": ("headache", "neuro"),
    "migran": ("migraine", "neuro"),
    "migren": ("migraine", "neuro"),
    "sar dard": ("headache", "neuro"),
    "sir dard": ("headache", "neuro"),
    "thalai vali": ("headache", "neuro"),
    "thalavali": ("headache", "neuro"),
    "dizzy": ("dizziness", "neuro"),
    "dizines": ("dizziness", "neuro"),
    "chakar": ("dizziness", "neuro"),

    # Musculoskeletal / Joint typos
    "kne pain": ("knee pain", "ortho"),
    "kne": ("knee pain", "ortho"),
    "joint pan": ("joint pain", "ortho"),
    "jont pain": ("joint pain", "ortho"),
    "muttu vali": ("knee pain", "ortho"),
    "bady ache": ("body ache", "fever"),
    "bodyache": ("body ache", "fever"),
    "badan dard": ("body ache", "fever"),
    "udal vali": ("body ache", "fever"),

    # General / Fatigue typos
    "weknss": ("weakness", "general"),
    "weaknes": ("weakness", "general"),
    "fatig": ("fatigue", "general"),
    "fatige": ("fatigue", "general"),
    "tierd": ("tiredness", "general"),
    "tierdness": ("tiredness", "general"),
}

def find_medical_typo(text: str, language: str = "en") -> Optional[Dict[str, str]]:
    """Detects medical typos in patient messages and returns the intended symptom and clinical category."""
    cleaned = (text or "").strip().lower()
    if not cleaned:
        return None
    
    # 1. Direct dictionary match
    if cleaned in SYMPTOM_TYPO_MAP:
        corrected, category = SYMPTOM_TYPO_MAP[cleaned]
        if cleaned != corrected.lower():
            return {"original": text.strip(), "corrected": corrected, "category": category}

    # 2. Fuzzy match with canonical list
    words = cleaned.split()
    if len(words) <= 3:
        matches = difflib.get_close_matches(cleaned, CANONICAL_SYMPTOMS_MAP.keys(), n=1, cutoff=0.72)
        if matches:
            match_key = matches[0]
            if cleaned != match_key.lower():
                corrected, category = CANONICAL_SYMPTOMS_MAP[match_key]
                return {"original": text.strip(), "corrected": corrected, "category": category}

        if len(words) == 1:
            single_word_syms = [k for k in CANONICAL_SYMPTOMS_MAP.keys() if " " not in k]
            m = difflib.get_close_matches(words[0], single_word_syms, n=1, cutoff=0.7)
            if m and words[0] != m[0].lower():
                corrected, category = CANONICAL_SYMPTOMS_MAP[m[0]]
                return {"original": text.strip(), "corrected": corrected, "category": category}
                
    return None

def validate_medical_input(text: str, stage: str = "chief_complaint", language: str = "en") -> Dict[str, Any]:
    """
    Validates patient input across all 9 supported Indian languages.
    Rejects gibberish, profanities, and non-medical off-topic text when a clinical symptom is requested.
    """
    cleaned = (text or "").strip().lower()

    # 1. Empty or extremely short (unless it's an accepted abbreviation like 'bp' or 'tb')
    if len(cleaned) < 3 and cleaned not in {"bp", "tb"}:
        msg = ct.get_validation_error("too_short", language)
        return {
            "valid": False,
            "error_type": "too_short",
            "message": msg,
            "message_hi": ct.get_validation_error("too_short", "hi"),
            "suggestions": get_initial_symptom_chips(language)
        }

    # 2. Profanity check
    if any(p in cleaned for p in PROFANITIES):
        msg = ct.get_validation_error("inappropriate", language)
        return {
            "valid": False,
            "error_type": "inappropriate",
            "message": msg,
            "message_hi": ct.get_validation_error("inappropriate", "hi"),
            "suggestions": get_initial_symptom_chips(language)
        }

    # 3. Gibberish & Keystroke Spam Detection
    # Repeated characters 4+ times (e.g. 'aaaa', 'zzzz', '1111')
    if re.search(r"(.)\1{3,}", cleaned):
        msg = ct.get_validation_error("gibberish", language)
        return {
            "valid": False,
            "error_type": "gibberish",
            "message": msg,
            "message_hi": ct.get_validation_error("gibberish", "hi"),
            "suggestions": get_initial_symptom_chips(language)
        }

    # Pure digits / punctuation
    if re.match(r"^[^a-zA-Z\u0900-\u0D7F]+$", cleaned):
        msg = ct.get_validation_error("gibberish", language)
        return {
            "valid": False,
            "error_type": "gibberish",
            "message": msg,
            "message_hi": ct.get_validation_error("gibberish", "hi"),
            "suggestions": get_initial_symptom_chips(language)
        }

    # Long consonant cluster without vowels in Latin script (e.g., 'asdfghjkl', 'qwrtpsdf')
    if re.search(r"^[a-zA-Z\s]+$", cleaned) and re.search(r"[bcdfghjklmnpqrstvwxyz]{6,}", cleaned):
        msg = ct.get_validation_error("gibberish", language)
        return {
            "valid": False,
            "error_type": "gibberish",
            "message": msg,
            "message_hi": ct.get_validation_error("gibberish", "hi"),
            "suggestions": get_initial_symptom_chips(language)
        }

    # 4. Off-topic & Non-medical input detection (specifically for the initial chief complaint stage)
    if stage == "chief_complaint":
        # Check for medical symptom typo first
        typo = find_medical_typo(cleaned, language)
        if typo:
            return {
                "valid": True,
                "is_typo": True,
                "typo_info": typo
            }

        # If the input is exactly a non-medical greeting or chatter
        if cleaned in NON_MEDICAL_PHRASES or any(cleaned == p for p in NON_MEDICAL_PHRASES):
            msg = ct.get_validation_error("non_medical", language)
            return {
                "valid": False,
                "error_type": "off_topic",
                "message": msg,
                "message_hi": ct.get_validation_error("non_medical", "hi"),
                "suggestions": get_initial_symptom_chips(language)
            }

        # Check if at least one medical symptom keyword or physiological term is present
        has_medical_term = any(k in cleaned for k in COMMON_MEDICAL_KEYWORDS)
        
        # Also check common general anatomical words or words indicating illness
        illness_words = ["pain", "dard", "ache", "swelling", "infection", "sick", "problem", "takleef", "bimari", "hurt", "bleeding", "dizziness", "burning", "jaln", "chot", "injury", "fever", "cough", "cold", "stool", "urine", "vomit", "breath"]
        has_illness_word = any(w in cleaned for w in illness_words)

        # Check if text is matched by our multilingual clinical classifier
        cat = ct.detect_category_multilingual(cleaned)
        is_classified_category = (cat != "general")

        if not (has_medical_term or has_illness_word or is_classified_category):
            # If length is under 15 characters and contains zero medical clues
            if len(cleaned.split()) <= 3:
                msg = ct.get_validation_error("non_medical", language)
                return {
                    "valid": False,
                    "error_type": "non_medical",
                    "message": msg,
                    "message_hi": ct.get_validation_error("non_medical", "hi"),
                    "suggestions": get_initial_symptom_chips(language)
                }

    return {"valid": True}


def get_initial_symptom_chips(language: str = "en") -> List[Dict[str, str]]:
    """Returns top initial common symptom chips in all 9 supported languages."""
    chips_by_lang = {
        "hi": [
            {"label": "सर्दी, खांसी व जुकाम", "icon": "🤧", "text": "मुझे 2 दिन से सर्दी और खांसी है"},
            {"label": "तेज़ बुखार व कंपकंपी", "icon": "🌡️", "text": "तेज़ बुखार और कंपकंपी है"},
            {"label": "सीने में तेज़ दर्द व भारीपन", "icon": "🫀", "text": "सीने में तेज़ दर्द और भारीपन है"},
            {"label": "पेट में दर्द व उल्टी", "icon": "🫄", "text": "पेट में तेज़ दर्द और गैस की समस्या है"},
            {"label": "गंभीर सिरदर्द / माइग्रेन", "icon": "🧠", "text": "सिर में तेज़ दर्द और चक्कर आ रहे हैं"},
            {"label": "घुटनों व जोड़ों में दर्द", "icon": "🦴", "text": "घुटनों और जोड़ों में दर्द व सूजन है"},
            {"label": "कमजोरी व सामान्य चेकअप", "icon": "🩺", "text": "कमजोरी और शुगर/बीपी का सामान्य चेकअप"},
        ],
        "bn": [
            {"label": "সর্দি, কাশি ও জ্বরভাব", "icon": "🤧", "text": "আমার ২ দিন ধরে সর্দি, কাশি ও নাক বন্ধের সমস্যা"},
            {"label": "তীব্র জ্বর ও কাঁপুনি", "icon": "🌡️", "text": "আমার তীব্র জ্বর ও গা কাঁপুনি দিয়ে শরীর ব্যথা"},
            {"label": "বুকে তীব্র ব্যথা ও চাপ", "icon": "🫀", "text": "বুকে তীব্র চাপ ও ব্যথা অনুভূত হচ্ছে"},
            {"label": "পেটে ব্যথা ও বমি", "icon": "🫄", "text": "পেটে তীব্র ব্যথা ও বমি বমি ভাব"},
            {"label": "তীব্র মাথা ব্যথা ও চক্কর", "icon": "🧠", "text": "প্রচণ্ড মাথা ব্যথা ও মাথা ঘোরার সমস্যা"},
            {"label": "হাঁটু ও গাঁটে গাঁটে ব্যথা", "icon": "🦴", "text": "হাঁটু ও জয়েন্টে ফোলা ভাব এবং তীব্র ব্যথা"},
            {"label": "সাধারণ দুর্বলতা ও চেকআপ", "icon": "🩺", "text": "সাধারণ দুর্বলতা ও স্বাস্থ্য পরীক্ষা"},
        ],
        "mr": [
            {"label": "सर्दी, खोकला व पडसे", "icon": "🤧", "text": "मला २ दिवसांपासून सर्दी, खोकला आणि घशात खवखव आहे"},
            {"label": "तीव्र ताप व भरून येणे", "icon": "🌡️", "text": "मला तीव्र ताप आणि अंगदुखीचा त्रास होतोय"},
            {"label": "छातीत तीव्र कळ व दाब", "icon": "🫀", "text": "छातीत तीव्र दुखणे आणि जडपणा जाणवत आहे"},
            {"label": "पोटदुखी व मळमळ", "icon": "🫄", "text": "पोटात तीव्र कळा येऊन उलट्या होत आहेत"},
            {"label": "डोकेदुखी व चक्कर", "icon": "🧠", "text": "तीव्र डोकेदुखी आणि चक्कर येत आहे"},
            {"label": "गुडघे व सांधेदुखी", "icon": "🦴", "text": "गुडघ्यात आणि सांध्यांमध्ये सूज व तीव्र वेदना आहेत"},
            {"label": "अशक्तपणा व तपासणी", "icon": "🩺", "text": "अशक्तपणा आणि नियमित आरोग्य तपासणी"},
        ],
        "ta": [
            {"label": "சளி, இருமல் & காய்ச்சல்", "icon": "🤧", "text": "எனக்கு 2 நாட்களாக சளி, இருமல் மற்றும் தொண்டை வலி உள்ளது"},
            {"label": "அதிக காய்ச்சல் & குளிர்", "icon": "🌡️", "text": "எனக்கு அதிக காய்ச்சல் மற்றும் நடுக்கத்துடன் உடல் வலி உள்ளது"},
            {"label": "நெஞ்சு வலி & இறுக்கம்", "icon": "🫀", "text": "நெஞ்சில் கடுமையான வலி மற்றும் அழுத்தம் உள்ளது"},
            {"label": "வயிற்று வலி & வாந்தி", "icon": "🫄", "text": "கடுமையான வயிற்று வலி மற்றும் வாந்தி உணர்வு உள்ளது"},
            {"label": "தலைவலி & தலைச்சுற்றல்", "icon": "🧠", "text": "கடுமையான தலைவலி மற்றும் தலைச்சுற்றல் உள்ளது"},
            {"label": "மூட்டு & முழங்கால் வலி", "icon": "🦴", "text": "மூட்டுகளில் வீக்கம் மற்றும் வலி உள்ளது"},
            {"label": "உடல் சோர்வு & பரிசோதனை", "icon": "🩺", "text": "உடல் சோர்வு மற்றும் பொது மருத்துவ பரிசோதனை"},
        ],
        "te": [
            {"label": "జలుబు, దగ్గు & తుమ్ములు", "icon": "🤧", "text": "నాకు 2 రోజులుగా జలుబు, దగ్గు మరియు గొంతు నొప్పి ఉంది"},
            {"label": "తీవ్రమైన జ్వరం & వణుకు", "icon": "🌡️", "text": "నాకు విపరీతమైన జ్వరం మరియు ఒళ్ళు నొప్పులు ఉన్నాయి"},
            {"label": "ఛాతీ నొప్పి & భారము", "icon": "🫀", "text": "ఛాతీలో తీవ్రమైన నొప్పి మరియు ఒత్తిడిగా ఉంది"},
            {"label": "కడుపు నొప్పి & వాంతులు", "icon": "🫄", "text": "తీవ్రమైన కడుపు నొప్పి మరియు వాంతులు అవుతున్నాయి"},
            {"label": "తీవ్ర తలనొప్పి & కళ్ళు తిరగడం", "icon": "🧠", "text": "తీవ్రమైన తలనొప్పి మరియు కళ్ళు తిరుగుతున్నాయి"},
            {"label": "కీళ్ళ & మోకాళ్ళ నొప్పులు", "icon": "🦴", "text": "మోకాళ్ళు మరియు కీళ్ళలో వాపు, నొప్పులు ఉన్నాయి"},
            {"label": "నీరసం & సాధారణ తనిఖీ", "icon": "🩺", "text": "శరీర బలహీనత మరియు సాధారణ ఆరోగ్య పరీక్ష"},
        ],
        "kn": [
            {"label": "ನೆಗಡಿ, ಕೆಮ್ಮು & ಗಂಟಲು ನೋವು", "icon": "🤧", "text": "ನನಗೆ 2 ದಿನಗಳಿಂದ ನೆಗಡಿ, ಕೆಮ್ಮು ಮತ್ತು ಗಂಟಲು ನೋವು ಇದೆ"},
            {"label": "ತೀವ್ರ ಜ್ವರ & ಚಳಿ", "icon": "🌡️", "text": "ನನಗೆ ತೀವ್ರ ಜ್ವರ ಮತ್ತು ಮೈಕೈ ನೋವು ಇದೆ"},
            {"label": "ಎದೆ ನೋವು & ಭಾರ", "icon": "🫀", "text": "ಎದೆಯಲ್ಲಿ ತೀವ್ರವಾದ ನೋವು ಮತ್ತು ಒತ್ತಡ ಅನುಭವವಾಗುತ್ತಿದೆ"},
            {"label": "ಹೊಟ್ಟೆ ನೋವು & ವಾಂತಿ", "icon": "🫄", "text": "ತೀವ್ರ ಹೊಟ್ಟೆ ನೋವು ಮತ್ತು ವಾಂತಿ ಬರುತ್ತಿದೆ"},
            {"label": "ತಲೆನೋವು & ತಲೆತಿರುಗುವಿಕೆ", "icon": "🧠", "text": "ತೀವ್ರ ತಲೆನೋವು ಮತ್ತು ತಲೆತಿರುಗುವಿಕೆ ಇದೆ"},
            {"label": "ಮಂಡಿ & ಕೀಲು ನೋವು", "icon": "🦴", "text": "ಮಂಡಿ ಹಾಗೂ ಕೀಲುಗಳಲ್ಲಿ ಊತ ಮತ್ತು ನೋವು ಇದೆ"},
            {"label": "ಸಾಮಾನ್ಯ ಆಯಾಸ & ತಪಾಸಣೆ", "icon": "🩺", "text": "ಸಾಮಾನ್ಯ ಆಯಾಸ ಮತ್ತು ತಪಾಸಣೆ"},
        ],
        "ml": [
            {"label": "ജലദോഷം, ചുമ & തൊണ്ടവേദന", "icon": "🤧", "text": "എനിക്ക് 2 ദിവസമായി കടുത്ത ജലദോഷവും ചുമയും ഉണ്ട്"},
            {"label": "കടുത്ത പനി & വിറയൽ", "icon": "🌡️", "text": "എനിക്ക് കടുത്ത പനിയും ശരീരവേദനയും ഉണ്ട്"},
            {"label": "നെഞ്ചുവേദന & ഭാരം", "icon": "🫀", "text": "നെഞ്ചിൽ ശക്തമായ വേദനയും ഭാരവും അനുഭവപ്പെടുന്നു"},
            {"label": "വയറുവേദന & ഛർദ്ദി", "icon": "🫄", "text": "കടുത്ത വയറുവേദനയും ഛർദ്ദിയും ഉണ്ടാകുന്നു"},
            {"label": "തലവേദന & തലകറക്കം", "icon": "🧠", "text": "കടുത്ത തലവേദനയും തലകറക്കവും അനുഭവപ്പെടുന്നു"},
            {"label": "സന്ധി & കാൽമുട്ട് വേദന", "icon": "🦴", "text": "കാൽമുട്ടിലും സന്ധികളിലും വീക്കവും വേദനയും ഉണ്ട്"},
            {"label": "ക്ഷീണം & ജനറൽ ചെക്കപ്പ്", "icon": "🩺", "text": "ശരീര ക്ഷീണവും സാധാരണ പരിശോധനയും"},
        ],
        "gu": [
            {"label": "શરદી, ઉધરસ અને કફ", "icon": "🤧", "text": "મને ૨ દિવસથી શરદી, ઉધરસ અને ગળામાં દુખાવો છે"},
            {"label": "તીવ્ર તાવ અને ધ્રુજારી", "icon": "🌡️", "text": "મને સખત તાવ અને શરીરમાં કંપારી સાથે દુખાવો છે"},
            {"label": "છાતીમાં દુખાવો અને ભાર", "icon": "🫀", "text": "છાતીમાં તીવ્ર દુખાવો અને દબાણ અનુભવાય છે"},
            {"label": "પેટનો દુખાવો અને ઉલટી", "icon": "🫄", "text": "પેટમાં તીવ્ર દુખાવો અને ઉલટી થાય છે"},
            {"label": "માથાનો દુખાવો અને ચક્કર", "icon": "🧠", "text": "સખત માથાનો દુખાવો અને ચક્કર આવે છે"},
            {"label": "સાંધા અને ઘૂંટણનો દુખાવો", "icon": "🦴", "text": "ઘૂંટણ અને સાંધામાં સોજો અને દુખાવો છે"},
            {"label": "નબળાઈ અને સામાન્ય તપાસ", "icon": "🩺", "text": "શારીરિક નબળાઈ અને સામાન્ય ચેકઅપ"},
        ],
        "en": [
            {"label": "Cold, Cough & Runny Nose", "icon": "🤧", "text": "I have cold, cough and runny nose"},
            {"label": "Fever & Body Chills", "icon": "🌡️", "text": "High fever with chills and body ache"},
            {"label": "Chest Pain & Pressure", "icon": "🫀", "text": "Severe chest pain and heavy pressure"},
            {"label": "Stomach Ache & Acidity", "icon": "🫄", "text": "Severe stomach pain with nausea"},
            {"label": "Severe Headache / Migraine", "icon": "🧠", "text": "Severe throbbing headache and dizziness"},
            {"label": "Knee & Joint Pain", "icon": "🦴", "text": "Knee pain, stiffness and swelling"},
            {"label": "Weakness / Routine Checkup", "icon": "🩺", "text": "General body weakness and routine diabetes checkup"},
        ]
    }
    return chips_by_lang.get(language, chips_by_lang["en"])


# -------------------------------------------------------------
# 2. Dynamic Clinical Probing Protocol (Condition-Specific)
# -------------------------------------------------------------

def detect_category(text: str) -> str:
    """Categorizes the patient's primary concern into a clinical organ system across all 9 languages."""
    return ct.detect_category_multilingual(text)


def process_consultation_turn(
    message: str,
    conversation_history: List[Dict[str, str]],
    current_state: Dict[str, Any],
    language: str = "en"
) -> Dict[str, Any]:
    """
    Processes a conversation turn in the doctor-patient intake.
    Returns:
      - valid: bool
      - reply: str (doctor's conversational question/statement)
      - suggestions: list of quick tap chips
      - current_state: updated state dict
      - is_complete: bool
      - red_flag: bool
      - triage_level: str
    """
    stage = current_state.get("stage", "chief_complaint")

    # Step A: Validate user input
    val = validate_medical_input(message, stage=stage, language=language)
    if not val["valid"]:
        reply = val.get("message") or val.get("message_hi", "")
        return {
            "valid": False,
            "reply": f"⚠️ {reply}",
            "suggestions": val.get("suggestions", get_initial_symptom_chips(language)),
            "current_state": current_state,
            "is_complete": False,
            "red_flag": current_state.get("red_flag", False),
            "triage_level": current_state.get("triage_level", "routine"),
            "completeness": current_state.get("completeness_percent", 15)
        }

    # Step B: Route by Stage
    if stage == "chief_complaint":
        typo_info = val.get("typo_info")
        if typo_info:
            original_word = typo_info["original"]
            corrected_word = typo_info["corrected"]
            category = typo_info.get("category") or detect_category(corrected_word)
            current_state["category"] = category
            current_state["chief_complaint"] = corrected_word
            current_state["stage"] = "turn_1"
            current_state["completeness_percent"] = 35

            red_flag, reasons, triage = evaluate_emergency_red_flags(corrected_word)
            current_state["red_flag"] = red_flag
            current_state["red_flag_reasons"] = reasons
            current_state["triage_level"] = triage

            turn1_res = generate_turn_1(category, corrected_word, current_state, language)
            clarification = ct.get_typo_clarification(original_word, corrected_word, language)
            turn1_res["reply"] = f"{clarification}\n\n{turn1_res['reply']}"
            return turn1_res

        category = detect_category(message)
        current_state["category"] = category
        current_state["chief_complaint"] = message.strip()
        current_state["stage"] = "turn_1"
        current_state["completeness_percent"] = 35

        # Check for immediate Red Flags in primary complaint
        red_flag, reasons, triage = evaluate_emergency_red_flags(message)
        current_state["red_flag"] = red_flag
        current_state["red_flag_reasons"] = reasons
        current_state["triage_level"] = triage

        # Formulate Turn 1 Question based on category
        return generate_turn_1(category, message, current_state, language)

    elif stage == "turn_1":
        # Ingest Onset / Duration / Character
        current_state["socrates"]["onset_character"] = message.strip()
        current_state["stage"] = "turn_2"
        current_state["completeness_percent"] = 60

        category = current_state.get("category", "general")
        return generate_turn_2(category, message, current_state, language)

    elif stage == "turn_2":
        # Ingest Associated Symptoms & Severity
        current_state["socrates"]["associations_severity"] = message.strip()
        current_state["stage"] = "turn_3"
        current_state["completeness_percent"] = 80

        # Check again for red flags based on updated descriptions
        full_text = f"{current_state.get('chief_complaint', '')} {message}"
        red_flag, reasons, triage = evaluate_emergency_red_flags(full_text)
        if red_flag:
            current_state["red_flag"] = True
            current_state["red_flag_reasons"] = list(set(current_state.get("red_flag_reasons", []) + reasons))
            current_state["triage_level"] = triage

        category = current_state.get("category", "general")
        return generate_turn_3(category, message, current_state, language)

    elif stage == "turn_3":
        # Ingest Past Medical History, Medications & Allergies
        current_state["past_history"] = message.strip()
        current_state["medications"] = extract_medications_heuristic(message)
        current_state["allergies"] = extract_allergies_heuristic(message)
        current_state["stage"] = "turn_4"
        current_state["completeness_percent"] = 95

        category = current_state.get("category", "general")
        return generate_turn_4(category, message, current_state, language)

    else:
        # Turn 4 completed -> Wrap up consultation
        current_state["lifestyle"] = message.strip()
        current_state["stage"] = "completed"
        current_state["completeness_percent"] = 100

        # Correlate AYUSH parameters based on symptom category
        assign_ayush_profile(current_state)

        return generate_completion(current_state, language)


# -------------------------------------------------------------
# 3. Turn-by-Turn Dynamic Branching
# -------------------------------------------------------------

def generate_turn_1(category: str, user_msg: str, state: Dict[str, Any], lang: str) -> Dict[str, Any]:
    state["socrates"] = state.get("socrates", {})
    reply, chips = ct.get_turn_1(category, lang)
    return {
        "valid": True,
        "reply": reply,
        "suggestions": chips,
        "current_state": state,
        "is_complete": False,
        "red_flag": state.get("red_flag", False),
        "triage_level": state.get("triage_level", "routine"),
        "completeness": state.get("completeness_percent", 35)
    }


def generate_turn_2(category: str, user_msg: str, state: Dict[str, Any], lang: str) -> Dict[str, Any]:
    reply, chips = ct.get_turn_2(category, lang)
    return {
        "valid": True,
        "reply": reply,
        "suggestions": chips,
        "current_state": state,
        "is_complete": False,
        "red_flag": state.get("red_flag", False),
        "triage_level": state.get("triage_level", "routine"),
        "completeness": state.get("completeness_percent", 60)
    }


def generate_turn_3(category: str, user_msg: str, state: Dict[str, Any], lang: str) -> Dict[str, Any]:
    reply, chips = ct.get_turn_3(lang)
    return {
        "valid": True,
        "reply": reply,
        "suggestions": chips,
        "current_state": state,
        "is_complete": False,
        "red_flag": state.get("red_flag", False),
        "triage_level": state.get("triage_level", "routine"),
        "completeness": state.get("completeness_percent", 80)
    }


def generate_turn_4(category: str, user_msg: str, state: Dict[str, Any], lang: str) -> Dict[str, Any]:
    reply, chips = ct.get_turn_4(lang)
    return {
        "valid": True,
        "reply": reply,
        "suggestions": chips,
        "current_state": state,
        "is_complete": False,
        "red_flag": state.get("red_flag", False),
        "triage_level": state.get("triage_level", "routine"),
        "completeness": state.get("completeness_percent", 95)
    }


def generate_completion(state: Dict[str, Any], lang: str) -> Dict[str, Any]:
    triage = state.get("triage_level", "routine")
    reply, chips = ct.get_completion(triage, lang)
    return {
        "valid": True,
        "reply": reply,
        "suggestions": chips,
        "current_state": state,
        "is_complete": True,
        "red_flag": state.get("red_flag", False),
        "triage_level": triage,
        "completeness": 100
    }


# -------------------------------------------------------------
# 4. Helper Utilities (Red Flags, Heuristics, AYUSH Profile)
# -------------------------------------------------------------

def evaluate_emergency_red_flags(text: str) -> (bool, List[str], str):
    lower = text.lower()
    urgent_keywords = [
        "chest pain", "seene me dard", "chhati dard", "shortness of breath",
        "breathlessness", "saans", "stroke", "unconscious", "fainted",
        "profuse sweating", "left arm pain", "vomiting blood", "severe bleeding"
    ] + ct.EMERGENCY_RED_FLAGS
    matched = [k for k in urgent_keywords if k in lower]
    if matched:
        return True, [f"Critical red flag detected: {m}" for m in matched], "emergency"
    return False, [], "routine"


def extract_medications_heuristic(text: str) -> str:
    common_drugs = ["paracetamol", "crocin", "metformin", "amlodipine", "aspirin", "atorvastatin", "telmisartan", "pantoprazole", "omeprazole", "azithromycin", "cetirizine", "inhaler", "salbutamol", "insulin"]
    lower = text.lower()
    found = [d.capitalize() for d in common_drugs if d in lower]
    if found:
        return ", ".join(found)
    if "no med" in lower or "none" in lower or "nahi" in lower:
        return "None reported"
    return text[:80] if len(text) > 4 else "None reported"


def extract_allergies_heuristic(text: str) -> str:
    common_allergies = ["penicillin", "sulfa", "aspirin", "ibuprofen", "dust", "pollen"]
    lower = text.lower()
    found = [a.capitalize() for a in common_allergies if a in lower]
    if found:
        return ", ".join(found)
    if "no allerg" in lower or "none" in lower or "nahi" in lower:
        return "None reported"
    return "None reported"


def assign_ayush_profile(state: Dict[str, Any]):
    category = state.get("category", "general")
    if category == "cold":
        state["prakriti"] = "Kapha-Vata"
        state["agni"] = "Manda Agni"
        state["ahara_vihara"] = "Pratishyaya / Kaphaja Kasa assessment, Pranavaha Srotas"
    elif category == "fever":
        state["prakriti"] = "Pitta"
        state["agni"] = "Vishama Agni"
        state["ahara_vihara"] = "Jwara evaluation, Ama dosha in Swedavaha Srotas"
    elif category == "cardiac":
        state["prakriti"] = "Vata-Pitta"
        state["agni"] = "Vishama Agni"
        state["ahara_vihara"] = "Hridaya Pranavaha Srotas assessment, Rasa Dhatu vitiation"
    elif category == "gastro":
        state["prakriti"] = "Pitta-Kapha"
        state["agni"] = "Manda Agni"
        state["ahara_vihara"] = "Amlapitta & Annavaha Srotas evaluation, Vidagdha Ajeerna"
    elif category == "neuro":
        state["prakriti"] = "Vata"
        state["agni"] = "Vishama Agni"
        state["ahara_vihara"] = "Shiroroga, Majjavaha Srotas evaluation, Vata Vyadhi"
    elif category == "joint":
        state["prakriti"] = "Vata"
        state["agni"] = "Manda Agni"
        state["ahara_vihara"] = "Sandhivata / Amavata evaluation, Asthivaha Srotas"
    else:
        state["prakriti"] = "Sama (Balanced)"
        state["agni"] = "Sama Agni"
        state["ahara_vihara"] = "Rasayana therapy, preventive OPD evaluation"
