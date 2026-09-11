"""
consultation.py
---------------
Interactive Doctor-Patient Consultation Engine for Starbucks.
Transforms step-by-step intake into an adaptive conversation:
1. Validates medical input (filters inappropriate, gibberish, and off-topic messages).
2. Generates dynamic, multi-turn doctor questions based on prior answers.
3. Produces specialized quick-response chips tailored to the specific health concern.
4. Extracts structured clinical telemetry (SOCRATES, history, medications, AYUSH).
5. Detects acute red flags and computes clinical history completeness.
"""

import re
from typing import Dict, List, Any, Optional

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
]

def validate_medical_input(text: str, stage: str = "chief_complaint", language: str = "en") -> Dict[str, Any]:
    """
    Validates patient input.
    Rejects gibberish, profanities, and non-medical off-topic text when a clinical symptom is requested.
    """
    cleaned = (text or "").strip().lower()

    # 1. Empty or extremely short (unless it's an accepted abbreviation like 'bp' or 'tb')
    if len(cleaned) < 3 and cleaned not in {"bp", "tb"}:
        return {
            "valid": False,
            "error_type": "too_short",
            "message": "Please enter a more detailed description of your health symptom.",
            "message_hi": "कृपया अपने स्वास्थ्य लक्षण का थोड़ा और विस्तार से विवरण दें।",
            "suggestions": get_initial_symptom_chips(language)
        }

    # 2. Profanity check
    if any(p in cleaned for p in PROFANITIES):
        return {
            "valid": False,
            "error_type": "inappropriate",
            "message": "Inappropriate language detected. Starbucks is a professional clinical consultation system. Please describe your health problem respectfully.",
            "message_hi": "अनुचित भाषा का प्रयोग न करें। कृपया अपनी स्वास्थ्य समस्या का शालीनता से विवरण दें।",
            "suggestions": get_initial_symptom_chips(language)
        }

    # 3. Gibberish & Keystroke Spam Detection
    # Repeated characters 4+ times (e.g. 'aaaa', 'zzzz', '1111')
    if re.search(r"(.)\1{3,}", cleaned):
        return {
            "valid": False,
            "error_type": "gibberish",
            "message": "Unrecognized or repeated input. Please type or speak a real medical symptom (e.g. cold, fever, headache, chest pain).",
            "message_hi": "अमान्य इनपुट। कृपया अपनी वास्तविक बीमारी या लक्षण (उदा. सर्दी, बुखार, सिरदर्द, सीने में दर्द) बताएं।",
            "suggestions": get_initial_symptom_chips(language)
        }

    # Pure digits / punctuation
    if re.match(r"^[^a-zA-Z\u0900-\u0D7F]+$", cleaned):
        return {
            "valid": False,
            "error_type": "gibberish",
            "message": "Numbers or symbols alone do not describe a medical condition. Please describe what discomfort you are experiencing.",
            "message_hi": "केवल अंक या चिन्ह पर्याप्त नहीं हैं। कृपया बताएं कि आपको क्या तकलीफ है।",
            "suggestions": get_initial_symptom_chips(language)
        }

    # Long consonant cluster without vowels (e.g., 'asdfghjkl', 'qwrtpsdf')
    if re.search(r"[bcdfghjklmnpqrstvwxyz]{6,}", cleaned):
        return {
            "valid": False,
            "error_type": "gibberish",
            "message": "The text entered does not resemble a valid medical concern. Please describe your symptom clearly or tap one of the suggestions below.",
            "message_hi": "यह शब्द किसी क्लिनिकल बीमारी से मेल नहीं खाता। कृपया नीचे दिए गए विकल्पों में से चुनें।",
            "suggestions": get_initial_symptom_chips(language)
        }

    # 4. Off-topic & Non-medical input detection (specifically for the initial chief complaint stage)
    if stage == "chief_complaint":
        # If the input is exactly a non-medical greeting or chatter
        if cleaned in NON_MEDICAL_PHRASES or any(cleaned == p for p in NON_MEDICAL_PHRASES):
            return {
                "valid": False,
                "error_type": "off_topic",
                "message": "I didn't catch a medical symptom in your message. To help you consult the doctor, please describe the specific health problem or physical discomfort you are facing today.",
                "message_hi": "मुझे आपके संदेश में कोई बीमारी या लक्षण नहीं मिला। कृपया बताएं कि आज आप किस समस्या या दर्द के लिए अस्पताल आए हैं।",
                "suggestions": get_initial_symptom_chips(language)
            }

        # Check if at least one medical symptom keyword or physiological term is present
        has_medical_term = any(k in cleaned for k in COMMON_MEDICAL_KEYWORDS)
        
        # Also check common general anatomical words or words indicating illness
        illness_words = ["pain", "dard", "ache", "swelling", "infection", "sick", "problem", "takleef", "bimari", "hurt", "bleeding", "dizziness", "burning", "jaln", "chot", "injury", "fever", "cough", "cold", "stool", "urine", "vomit", "breath"]
        has_illness_word = any(w in cleaned for w in illness_words)

        if not (has_medical_term or has_illness_word):
            # If length is under 15 characters and contains zero medical clues
            if len(cleaned.split()) <= 3:
                return {
                    "valid": False,
                    "error_type": "non_medical",
                    "message": f"'{text}' does not appear to be a medical symptom. Please state what health issue or physical discomfort you are experiencing.",
                    "message_hi": f"'{text}' कोई क्लिनिकल लक्षण प्रतीत नहीं होता। कृपया अपनी स्वास्थ्य समस्या का स्पष्ट विवरण दें।",
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
    """Categorizes the patient's primary concern into a clinical organ system."""
    lower = text.lower()
    if re.search(r"chest|heart|cardiac|palpitation|angina|chhati|seene|saans|breath|coronary|myocardial", lower):
        return "cardiac"
    if re.search(r"cold|cough|phlegm|mucus|sneeze|runny nose|sore throat|gala|khansi|sardi|jukham|kaph|wheez", lower):
        return "cold"
    if re.search(r"fever|temp|chills|shiver|bukhar|thand|jwara|dengue|malaria|typhoid", lower):
        return "fever"
    if re.search(r"stomach|abdomen|belly|gastric|acidity|vomit|diarrhea|pet dard|kabz|dast|loose stool|ulti|ulcer", lower):
        return "gastro"
    if re.search(r"headache|migraine|dizzy|vertigo|neuro|sar dard|chakkar|behoshi|faint", lower):
        return "neuro"
    if re.search(r"knee|joint|bone|backache|back pain|arthritis|guthna|kamar dard|jod|swelling|ankle|gout|sciatica", lower):
        return "joint"
    return "general"


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
        reply = val["message_hi"] if language == "hi" else val["message"]
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

    if category == "cold":
        if lang == "hi":
            reply = f"मैं समझ गया कि आपको सर्दी-जुकाम की समस्या है। कृपया बताएं कि यह कितने दिनों से है, और क्या आपको सूखी खांसी है या बलगम/कफ भी निकल रहा है?"
            chips = [
                {"label": "1 - 2 दिन से (अचानक)", "icon": "⚡", "text": "2 दिन से है, बलगम और छींकें आ रही हैं"},
                {"label": "सूखी खांसी व गले में खराश", "icon": "🗣️", "text": "3 दिन से सूखी खांसी और गले में खराश है"},
                {"label": "कफ/बलगम वाली खांसी", "icon": "🫁", "text": "कफ और पीला बलगम आ रहा है"},
                {"label": "1 हफ्ते से अधिक समय से", "icon": "📅", "text": "लगभग 1 हफ्ते से लगातार बना हुआ है"}
            ]
        else:
            reply = f"I understand you are dealing with a cold and respiratory discomfort. How many days has this been going on, and is your cough dry or with phlegm/mucus?"
            chips = [
                {"label": "Started 1-2 days ago", "icon": "⚡", "text": "Started 2 days ago with runny nose and sneezing"},
                {"label": "Dry cough & scratchy throat", "icon": "🗣️", "text": "Dry persistent cough with sore throat for 3 days"},
                {"label": "Productive cough with phlegm", "icon": "🫁", "text": "Chest congestion with thick phlegm/mucus"},
                {"label": "Ongoing for over a week", "icon": "📅", "text": "Ongoing for more than a week without relief"}
            ]

    elif category == "cardiac":
        if lang == "hi":
            reply = f"सीने का दर्द एक गंभीर लक्षण है। क्या यह दर्द भारी दबाव या निचोड़ जैसा महसूस हो रहा है, और क्या यह छाती के बीच में है या बाईं तरफ?"
            chips = [
                {"label": "छाती के बीच में भारी दबाव", "icon": "🗜️", "text": "छाती के बीच में भारी दबाव और जकड़न है"},
                {"label": "बाईं तरफ तेज़ चुभने वाला दर्द", "icon": "👈", "text": "बाईं तरफ तेज़ चुभन महसूस हो रही है"},
                {"label": "सांस लेने में भारी तकलीफ", "icon": "😮‍💨", "text": "सांस फूल रही है और सीने में जकड़न है"},
                {"label": "चलने पर दर्द बढ़ जाता है", "icon": "🚶‍♂️", "text": "चलने या मेहनत करने पर दर्द बढ़ जाता है"}
            ]
        else:
            reply = f"Chest discomfort is an important symptom that requires precise triage. Does it feel like a crushing heaviness or tightness, and is it located retrosternally (center of chest) or on the left?"
            chips = [
                {"label": "Center chest crushing pressure", "icon": "🗜️", "text": "Heavy crushing pressure in center of chest"},
                {"label": "Sharp left-sided chest pain", "icon": "👈", "text": "Sharp stabbing pain on the left side of chest"},
                {"label": "Tight band with breathlessness", "icon": "😮‍💨", "text": "Tight band-like constriction and shortness of breath"},
                {"label": "Worse with walking / exertion", "icon": "🚶‍♂️", "text": "Pain increases with physical exertion and walking"}
            ]

    elif category == "fever":
        if lang == "hi":
            reply = f"बुखार के संबंध में: यह कितने दिनों से है, क्या आपको कंपकंपी/ठंड लग रही है, और क्या आपने थर्मामीटर से तापमान नापा है?"
            chips = [
                {"label": "2 दिन से तेज़ बुखार (102°F)", "icon": "🔥", "text": "2 दिन से तेज़ बुखार 102 डिग्री है"},
                {"label": "कंपकंपी व ठंड लगकर बुखार", "icon": "🥶", "text": "तेज़ कंपकंपी और ठंड लगकर बुखार आता है"},
                {"label": "हल्का बुखार और शरीर में दर्द", "icon": "🌡️", "text": "हल्का बुखार 99-100 और शरीर में बहुत दर्द है"},
                {"label": "शाम के समय बढ़ता है", "icon": "🌙", "text": "सुबह सामान्य रहता है, शाम को बुखार बढ़ जाता है"}
            ]
        else:
            reply = f"Regarding your fever: How many days have you had high temperature, is it accompanied by shivering/chills, and have you measured it?"
            chips = [
                {"label": "High fever (102°F) for 2 days", "icon": "🔥", "text": "High grade fever 102°F for past 2 days"},
                {"label": "Severe chills & shivering", "icon": "🥶", "text": "Fever with severe shivering and chills"},
                {"label": "Low grade with body ache", "icon": "🌡️", "text": "Low grade fever around 100°F with intense body aches"},
                {"label": "Spikes in the evening", "icon": "🌙", "text": "Normal in morning, spikes significantly in evening"}
            ]

    elif category == "gastro":
        if lang == "hi":
            reply = f"पेट की तकलीफ के बारे में: दर्द ठीक किस जगह पर है (ऊपरी पेट, नाभि के पास, या नीचे), और क्या आपको खट्टी डकार या उल्टी भी हो रही है?"
            chips = [
                {"label": "ऊपरी पेट में तेज़ जलन", "icon": "🔥", "text": "ऊपरी पेट में तेज़ जलन और खट्टी डकारें हैं"},
                {"label": "मरोड़ वाला दर्द और उल्टी", "icon": "🤢", "text": "पेट में मरोड़ उठ रहे हैं और उल्टी हो रही है"},
                {"label": "दाहिनी तरफ पसलियों के नीचे", "icon": "👉", "text": "दाहिनी तरफ पसलियों के नीचे चुभन है"},
                {"label": "दस्त व पेट फूलना", "icon": "🚽", "text": "पेट फूल रहा है और पतले दस्त हो रहे हैं"}
            ]
        else:
            reply = f"Regarding your abdominal discomfort: Where is the pain concentrated (upper epigastric, navel, or lower abdomen), and is there acidity or vomiting?"
            chips = [
                {"label": "Upper abdominal burning acid", "icon": "🔥", "text": "Severe burning pain in upper stomach with acid reflux"},
                {"label": "Colicky cramps & vomiting", "icon": "🤢", "text": "Severe cramping spasms with recurrent vomiting"},
                {"label": "Right upper side below ribs", "icon": "👉", "text": "Sharp ache in right upper abdomen below ribcage"},
                {"label": "Bloating & watery diarrhea", "icon": "🚽", "text": "Severe abdominal distension and loose watery stools"}
            ]

    elif category == "neuro":
        if lang == "hi":
            reply = f"सिरदर्द के बारे में: क्या दर्द सिर के एक हिस्से में धड़कन जैसा है, या पूरे सिर में भारीपन है? क्या चक्कर भी आ रहे हैं?"
            chips = [
                {"label": "एक तरफ धड़कता हुआ माइग्रेन", "icon": "🧠", "text": "सिर के आधे हिस्से में धड़कता हुआ तेज़ दर्द है"},
                {"label": "घूमता हुआ चक्कर (वर्टिगो)", "icon": "💫", "text": "कमरे में चक्कर आ रहे हैं और संतुलन बिगड़ रहा है"},
                {"label": "रोशनी और आवाज़ से तकलीफ", "icon": "💡", "text": "रोशनी और आवाज़ से सिर का दर्द असहनीय हो जाता है"},
                {"label": "माथे में भारी तनाव", "icon": "🗜️", "text": "माथे और कनपटी पर भारी दबाव बना हुआ है"}
            ]
        else:
            reply = f"Regarding your headache: Is it a pulsating ache on one side of your head, or generalized tension? Are you feeling dizzy or light-sensitive?"
            chips = [
                {"label": "Throbbing one-sided migraine", "icon": "🧠", "text": "Throbbing unilateral migraine pain in temple/eye"},
                {"label": "Spinning room vertigo", "icon": "💫", "text": "Severe room spinning vertigo and balance loss"},
                {"label": "Light & sound intolerance", "icon": "💡", "text": "Extreme intolerance to bright lights and loud sounds"},
                {"label": "Constricting band pressure", "icon": "🗜️", "text": "Tight band-like constriction around forehead"}
            ]

    elif category == "joint":
        if lang == "hi":
            reply = f"जोड़ों के दर्द के बारे में: मुख्य रूप से कौन सा जोड़ प्रभावित है (घुटने, कमर, या गर्दन), और क्या सुबह उठने पर जकड़न रहती है?"
            chips = [
                {"label": "दोनों घुटनों में चलने पर दर्द", "icon": "🦵", "text": "दोनों घुटनों में चलने और सीढ़ियों पर तेज़ दर्द होता है"},
                {"label": "सुबह 30 मिनट से अधिक जकड़न", "icon": "⏰", "text": "सुबह उठने पर 30 मिनट से ज्यादा जोड़ों में जकड़न रहती है"},
                {"label": "कमर से पैर तक जाता दर्द", "icon": "⚡", "text": "कमर का दर्द पैर के नीचे तक जा रहा है (साइटिका)"},
                {"label": "जोड़ों में सूजन और गर्माहट", "icon": "🔴", "text": "घुटने और टखने में स्पष्ट सूजन और गर्माहट है"}
            ]
        else:
            reply = f"Regarding your joint and musculoskeletal pain: Which specific joints are affected (knees, lumbar spine, hands), and is there morning stiffness?"
            chips = [
                {"label": "Bilateral knee pain with walking", "icon": "🦵", "text": "Severe pain in both knees when walking and climbing stairs"},
                {"label": "Morning stiffness > 30 mins", "icon": "⏰", "text": "Marked joint stiffness lasting over 30 minutes every morning"},
                {"label": "Lower back shooting down leg", "icon": "⚡", "text": "Sharp lower back pain radiating down the leg (sciatica)"},
                {"label": "Noticeable swelling and warmth", "icon": "🔴", "text": "Joints are visibly swollen, warm and tender to touch"}
            ]

    else:
        if lang == "hi":
            reply = f"कृपया बताएं कि यह समस्या कब से शुरू हुई, और क्या यह दिन-प्रतिदिन बढ़ रही है या बीच-बीच में आती है?"
            chips = [
                {"label": "कुछ दिनों से धीरे-धीरे बढ़ी", "icon": "⏳", "text": "पिछले 3-4 दिनों से धीरे-धीरे बढ़ रही है"},
                {"label": "पुराने रोग की नियमित जांच", "icon": "🩺", "text": "यह मेरी पुरानी बीमारी है, नियमित डॉक्टर जांच हेतु आया हूँ"},
                {"label": "अचानक आज सुबह से शुरू", "icon": "⚡", "text": "अचानक आज सुबह से ही तकलीफ शुरू हुई है"}
            ]
        else:
            reply = f"Please let me know how long this has been affecting you, and whether it is persistent or comes and goes periodically?"
            chips = [
                {"label": "Gradually over past few days", "icon": "⏳", "text": "Gradually worsening over the last 3-4 days"},
                {"label": "Routine follow-up for chronic issue", "icon": "🩺", "text": "Routine follow-up checkup for chronic condition"},
                {"label": "Started suddenly today", "icon": "⚡", "text": "Started suddenly earlier today"}
            ]

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
    if category == "cold":
        if lang == "hi":
            reply = f"नोट कर लिया गया। क्या इस सर्दी के साथ आपको बुखार, सांस फूलना या सीने में भारी जकड़न भी महसूस हो रही है?"
            chips = [
                {"label": "हल्का बुखार (100°F)", "icon": "🌡️", "text": "हल्का बुखार है और गले में खराश है"},
                {"label": "सांस लेने में थोड़ी दिक्कत", "icon": "😮‍💨", "text": "सांस लेने में हल्की घबराहट और जकड़न है"},
                {"label": "तेज़ बुखार व कंपकंपी", "icon": "🥶", "text": "तेज़ बुखार और कंपकंपी भी है"},
                {"label": "बुखार नहीं है, केवल जुकाम", "icon": "✅", "text": "बुखार नहीं है, केवल बहती नाक और छींकें हैं"}
            ]
        else:
            reply = f"Noted. Along with this cold, are you experiencing any fever, shortness of breath, throat pain, or chest tightness?"
            chips = [
                {"label": "Mild fever (around 100°F)", "icon": "🌡️", "text": "Mild fever with scratchy sore throat"},
                {"label": "Shortness of breath / wheeze", "icon": "😮‍💨", "text": "Noticeable chest tightness and slight wheezing"},
                {"label": "High fever & body shivering", "icon": "🥶", "text": "High temperature with body chills and shivering"},
                {"label": "No fever, only nasal cold", "icon": "✅", "text": "No fever at all, just persistent runny nose and sneezing"}
            ]

    elif category == "cardiac":
        if lang == "hi":
            reply = f"🚨 महत्वपूर्ण जांच: क्या यह दर्द आपके बाएं हाथ, कंधे, गर्दन या जबड़े की तरफ फैलता है? और क्या आपको पसीना या सांस फूलने की समस्या हो रही है?"
            chips = [
                {"label": "बाएं हाथ और जबड़े में दर्द", "icon": "💪", "text": "दर्द बाएं हाथ और जबड़े की तरफ फैल रहा है"},
                {"label": "ठंडा पसीना और सांस फूलना", "icon": "💦", "text": "बहुत ठंडा पसीना आ रहा है और सांस फूल रही है"},
                {"label": "दर्द केवल छाती में सीमित है", "icon": "🎯", "text": "दर्द फैलता नहीं है, केवल एक जगह पर है"},
                {"label": "घबराहट और चक्कर", "icon": "💫", "text": "दिल की धड़कन तेज़ है और चक्कर आ रहे हैं"}
            ]
        else:
            reply = f"🚨 Critical Assessment: Does this pain radiate to your left arm, shoulder, neck, or jaw? And are you breaking out in a cold sweat or having breathlessness?"
            chips = [
                {"label": "Radiating to left arm & jaw", "icon": "💪", "text": "Pain radiates clearly down my left arm and up to jaw"},
                {"label": "Profuse cold sweat & gasping", "icon": "💦", "text": "Breaking out in profuse cold sweats with difficulty breathing"},
                {"label": "No radiation, stays in chest", "icon": "🎯", "text": "No radiation, localized strictly in center of chest"},
                {"label": "Palpitations & lightheadedness", "icon": "💫", "text": "Rapid racing pulse and lightheadedness"}
            ]

    elif category == "fever":
        if lang == "hi":
            reply = f"धन्यवाद। क्या बुखार के साथ खांसी, उल्टी, त्वचा पर लाल चकत्ते, या हाल ही में किसी मलेरिया/डेंगू प्रभावित इलाके की यात्रा की है?"
            chips = [
                {"label": "खांसी और कफ भी है", "icon": "🗣️", "text": "बुखार के साथ बलगम वाली खांसी भी है"},
                {"label": "आंखों के पीछे दर्द व चकत्ते", "icon": "👁️", "text": "आंखों के पीछे तेज़ दर्द है और त्वचा पर लाल दाने हैं"},
                {"label": "पेशाब में जलन", "icon": "🚽", "text": "पेशाब में तेज़ जलन और बार-बार जाना पड़ रहा है"},
                {"label": "अन्य कोई लक्षण नहीं", "icon": "✅", "text": "केवल बुखार और कमजोरी है, कोई अन्य लक्षण नहीं"}
            ]
        else:
            reply = f"Thank you. Along with the fever, do you have cough, vomiting, skin rashes, burning urination, or recent travel to a malaria/dengue prone area?"
            chips = [
                {"label": "Productive cough & sputum", "icon": "🗣️", "text": "Fever accompanied by productive cough and yellow sputum"},
                {"label": "Retro-orbital pain & rashes", "icon": "👁️", "text": "Intense ache behind eyes and faint red rashes on arms"},
                {"label": "Burning sensation during urination", "icon": "🚽", "text": "Severe burning sensation and frequency when urinating"},
                {"label": "No other symptoms", "icon": "✅", "text": "Just fever, fatigue and loss of appetite"}
            ]

    elif category == "gastro":
        if lang == "hi":
            reply = f"क्या यह दर्द खाना खाने के बाद बढ़ता है या खाली पेट? क्या उल्टी में खून, या काले रंग का मल आने की शिकायत है?"
            chips = [
                {"label": "खाना खाने के तुरंत बाद बढ़ता है", "icon": "🍽️", "text": "खाना खाते ही पेट में तेज़ जलन और दर्द बढ़ता है"},
                {"label": "खाली पेट ज्यादा दर्द रहता है", "icon": "⏰", "text": "खाली पेट ज्यादा दर्द होता है, खाने पर थोड़ा आराम मिलता है"},
                {"label": "लगातार उल्टी हो रही है", "icon": "🤢", "text": "पानी पीने पर भी उल्टी हो रही है"},
                {"label": "खून या काला मल नहीं है", "icon": "✅", "text": "साधारण पेट दर्द है, कोई खून या काला मल नहीं है"}
            ]
        else:
            reply = f"Does this pain get worse after eating meals or when your stomach is empty? And have you noticed any blood in vomit or black-colored stools?"
            chips = [
                {"label": "Worse immediately after meals", "icon": "🍽️", "text": "Pain intensifies sharply within 30 minutes after eating"},
                {"label": "Worse on empty stomach", "icon": "⏰", "text": "Severe gnawing pain when hungry, relieved slightly by milk/food"},
                {"label": "Persistent vomiting / cannot keep water", "icon": "🤢", "text": "Unable to keep water down due to recurrent vomiting"},
                {"label": "No blood or black stools", "icon": "✅", "text": "No blood or dark stools, standard digestive distress"}
            ]

    elif category == "neuro":
        if lang == "hi":
            reply = f"क्या सिरदर्द शुरू होने से पहले आंखों के आगे चमक या धुंधलापन दिखता है? क्या उल्टी या गर्दन में अकड़न महसूस होती है?"
            chips = [
                {"label": "आंखों के आगे चमक (ऑरा)", "icon": "👁️", "text": "सिरदर्द से पहले आंखों के आगे टेढ़ी-मेढ़ी रोशनी चमकती है"},
                {"label": "उल्टी और मतली की इच्छा", "icon": "🤢", "text": "सिरदर्द के साथ बहुत तेज़ जी मिचलाना और उल्टी होती है"},
                {"label": "गर्दन में अकड़न और तेज़ दर्द", "icon": "🧣", "text": "गर्दन में बहुत अकड़न है और सिर झुकाने पर दर्द होता है"},
                {"label": "नींद की कमी और तनाव", "icon": "🌙", "text": "नींद पूरी न होने और तनाव से दर्द बढ़ता है"}
            ]
        else:
            reply = f"Before or during the headache, do you experience visual zig-zags (aura), numbness in fingers, nausea, or stiffness in your neck?"
            chips = [
                {"label": "Visual flickering aura", "icon": "👁️", "text": "Visual zig-zag aura and blurred vision preceding headache"},
                {"label": "Severe nausea & vomiting", "icon": "🤢", "text": "Headache causes intense nausea and recurrent vomiting"},
                {"label": "Neck stiffness with fever", "icon": "🧣", "text": "Stiff neck and pain when bending chin to chest"},
                {"label": "Stress & lack of sleep triggers", "icon": "🌙", "text": "Directly triggered by lack of sleep, screens, and work stress"}
            ]

    elif category == "joint":
        if lang == "hi":
            reply = f"क्या आपको जोड़ों में कट-कट की आवाज़ (क्रेपिटस) आती है? क्या दर्द के कारण नीचे बैठने या चलने में बहुत असमर्थता हो रही है?"
            chips = [
                {"label": "घुटनों में कट-कट की आवाज़", "icon": "🔊", "text": "घुटने मोड़ने पर कट-कट की आवाज़ आती है"},
                {"label": "नीचे बैठने व उठने में असमर्थ", "icon": "🪑", "text": "जमीन पर बैठने या उकड़ू बैठने में बहुत कठिनाई होती है"},
                {"label": "हाथ की छोटी उंगलियों में भी दर्द", "icon": "🖐️", "text": "हाथ की छोटी उंगलियों और कलाइयों में भी दर्द व सूजन है"},
                {"label": "दर्द की गोली लेने पर आराम", "icon": "💊", "text": "पेनकिलर लेने पर कुछ घंटे आराम मिलता है फिर दर्द होता है"}
            ]
        else:
            reply = f"Do you notice cracking/grinding sounds (crepitus) on moving the joint? Does the pain limit your ability to walk or sit on the floor?"
            chips = [
                {"label": "Audible grinding / crepitus", "icon": "🔊", "text": "Noticeable grinding and cracking sounds when bending knees"},
                {"label": "Inability to squat or sit low", "icon": "🪑", "text": "Severe difficulty sitting on floor or getting up from chair"},
                {"label": "Small finger and wrist joints", "icon": "🖐️", "text": "Pain also affects small knuckle joints on both hands"},
                {"label": "Temporary relief with painkillers", "icon": "💊", "text": "Temporary relief with NSAID painkillers, but returns quickly"}
            ]

    else:
        if lang == "hi":
            reply = f"क्या इस तकलीफ के साथ आपको भूख में कमी, चक्कर, वजन घटना या नींद की समस्या भी है?"
            chips = [
                {"label": "भूख और नींद में बहुत कमी", "icon": "🌙", "text": "भूख बिल्कुल नहीं लग रही और नींद में बेचैनी रहती है"},
                {"label": "थकान व चक्कर आते हैं", "icon": "💤", "text": "सारा दिन अत्यधिक थकान और चक्कर महसूस होते हैं"},
                {"label": "कोई अन्य परेशानी नहीं", "icon": "✅", "text": "अन्य कोई विशेष लक्षण नहीं है"}
            ]
        else:
            reply = f"Are you experiencing any associated symptoms such as unexpected weight loss, chronic fatigue, dizziness, or sleep disturbances?"
            chips = [
                {"label": "Loss of appetite & poor sleep", "icon": "🌙", "text": "Complete loss of appetite and disturbed sleep patterns"},
                {"label": "Constant fatigue & giddiness", "icon": "💤", "text": "Overwhelming tiredness throughout the day with occasional dizziness"},
                {"label": "No other associated symptoms", "icon": "✅", "text": "No other associated complaints, strictly localized"}
            ]

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
    if lang == "hi":
        reply = "कृपया अपनी पुरानी बीमारियों की जानकारी दें (जैसे बीपी, शुगर, अस्थमा, थायरॉइड), आप वर्तमान में कौन सी दवाइयां ले रहे हैं, और क्या किसी दवा से एलर्जी है?"
        chips = [
            {"label": "शुगर (डायबिटीज) व बीपी", "icon": "🩸", "text": "मुझे डायबिटीज और हाई ब्लड प्रेशर है। मेटफॉर्मिन और टेल्मीसार्टन लेता हूँ। कोई एलर्जी नहीं।"},
            {"label": "अस्थमा की बीमारी (इन्हेलर)", "icon": "🫁", "text": "अस्थमा है और सालबुटामोल इन्हेलर लेता हूँ। कोई एलर्जी नहीं।"},
            {"label": "पेनिसिलिन / सल्फा दवा से एलर्जी", "icon": "⚠️", "text": "मुझे पेनिसिलिन एंटीबायोटिक से एलर्जी है। कोई अन्य पुरानी बीमारी नहीं।"},
            {"label": "केवल पैरासिटामोल ले रहा हूँ", "icon": "💊", "text": "वर्तमान में केवल पैरासिटामोल ली है। कोई पुरानी बीमारी या एलर्जी नहीं है।"},
            {"label": "कोई पुरानी बीमारी या एलर्जी नहीं", "icon": "✅", "text": "मुझे कोई पुरानी बीमारी नहीं है और किसी दवा से एलर्जी नहीं है।"}
        ]
    else:
        reply = "Please share your medical history: Do you have conditions like Diabetes, High BP, or Asthma? What regular medications do you take, and do you have any drug allergies?"
        chips = [
            {"label": "Diabetes & High Blood Pressure", "icon": "🩸", "text": "History of Type 2 Diabetes and Hypertension. Taking Metformin and Telmisartan. No allergies."},
            {"label": "Bronchial Asthma (Uses Inhaler)", "icon": "🫁", "text": "History of bronchial asthma, taking Salbutamol inhaler. No known allergies."},
            {"label": "Allergy to Penicillin / Sulfa", "icon": "⚠️", "text": "Severe allergy to Penicillin antibiotics. No other chronic illness."},
            {"label": "Taking Paracetamol / OTC only", "icon": "💊", "text": "Only taking Paracetamol 650mg for current symptoms. No chronic diseases."},
            {"label": "No chronic conditions or allergies", "icon": "✅", "text": "No past medical conditions, no regular medications, and no drug allergies."}
        ]

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
    if lang == "hi":
        reply = "धन्यवाद। आयुष व समग्र स्वास्थ्य मूल्यांकन हेतु: क्या आप मांसाहारी या शाकाहारी हैं, भोजन का समय कैसा रहता है, और क्या आप सिगरेट/तंबाकू लेते हैं?"
        chips = [
            {"label": "शाकाहारी, अनियमित भोजन का समय", "icon": "🥗", "text": "शुद्ध शाकाहारी भोजन, अनियमित समय पर खाना, चाय ज्यादा पीता हूँ। धूम्रपान नहीं।"},
            {"label": "तीखा-तला भोजन व देर रात नींद", "icon": "🌶️", "text": "तीखा व तला भोजन, देर रात 12 बजे सोना, 6 घंटे की नींद।"},
            {"label": "संतुलित आहार, 7 घंटे नींद", "icon": "⏰", "text": "संतुलित घर का भोजन, 7-8 घंटे की अच्छी नींद, कोई व्यसन नहीं।"},
            {"label": "सिगरेट / बीड़ी का सेवन", "icon": "🚬", "text": "प्रतिदिन 4-5 सिगरेट पीता हूँ, दफ्तर में ज्यादा बैठने का काम है।"}
        ]
    else:
        reply = "Lastly, for our holistic AYUSH & lifestyle assessment: What are your dietary habits (vegetarian/spicy), daily meal routine, sleep hours, and do you use tobacco or alcohol?"
        chips = [
            {"label": "Vegetarian, irregular meal hours", "icon": "🥗", "text": "Vegetarian diet, irregular meal timings due to desk job, non-smoker, 6 hrs sleep."},
            {"label": "Spicy diet & late night sleep", "icon": "🌶️", "text": "Spicy & fried food intake, late night sleep after midnight, occasional alcohol."},
            {"label": "Balanced home food, 8 hrs sleep", "icon": "⏰", "text": "Healthy balanced home cooked food, 7-8 hours restful sleep, no tobacco/smoking."},
            {"label": "Tobacco / Smoking history", "icon": "🚬", "text": "Smoker (5 cigarettes per day), sedentary desk routine, high stress levels."}
        ]

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
    cat = state.get("category", "general")
    triage = state.get("triage_level", "routine")

    if lang == "hi":
        if triage == "emergency":
            reply = f"🚨 **क्लिनिकल इतिहास पूर्ण — आपातकालीन प्राथमिकता अलर्ट:** मैंने आपकी पूरी केस हिस्ट्री दर्ज कर ली है। आपके लक्षण तीव्र प्राथमिकता श्रेणी में आते हैं। कृपया नीचे दिए गए विकल्प से पुराने पर्चे/रिपोर्ट स्कैन करें और तुरंत ओपीडी में डॉक्टर को अपना केस भेजें।"
        else:
            reply = f"✅ **क्लिनिकल इतिहास सफलतापूर्वक दर्ज हो गया:** आपकी स्थिति का संपूर्ण विवरण तैयार कर लिया गया है। यदि आपके पास पुराने मेडिकल पर्चे या लैब रिपोर्ट हैं, तो नीचे दिए गए स्कैनर से अपलोड करें, या सीधे 'केस सारांश देखें' पर क्लिक करके डॉक्टर को भेजें।"
        chips = [
            {"label": "📄 पुराने पर्चे या रिपोर्ट स्कैन करें", "icon": "📤", "text": "स्कैन दस्तावेज"},
            {"label": "📋 केस सारांश देखें और डॉक्टर को भेजें", "icon": "🏥", "text": "सारांश देखें"}
        ]
    else:
        if triage == "emergency":
            reply = f"🚨 **Clinical Intake Completed — EMERGENCY Triage Priority:** All relevant clinical dimensions have been gathered. Your reported symptoms have been categorized as an **EMERGENCY priority** for the attending doctor. Please scan any previous ECG or lab reports below, or tap Submit to route to the OPD consultation queue immediately."
        else:
            reply = f"✅ **Clinical Intake Successfully Completed:** I have documented a comprehensive pre-consultation case history. If you have any previous doctor prescriptions or diagnostic reports, you can upload them below for OCR digitization, or tap to review your summary and send it to the physician."
        chips = [
            {"label": "📄 Scan / Upload Medical Records", "icon": "📤", "text": "Scan Documents"},
            {"label": "📋 Review Case Summary & Send to Doctor", "icon": "🏥", "text": "Review Summary"}
        ]

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
    ]
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
