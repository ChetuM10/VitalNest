"""Fixed responses for blocked requests.

DRAFT wording: the final text is agreed in docs/safety.md (open item in the plan). These are
fixed strings on purpose, so a blocked request never depends on the LLM and never echoes user input.
"""

EMERGENCY_MESSAGE = (
    "This sounds like it could be a medical emergency. Please call your local emergency number "
    "right now (for example 112 in India and the EU, 911 in the US and Canada, 999 in the UK) "
    "or go to the nearest emergency department. If someone is with you, ask them to help. "
    "I can't assess emergencies, and getting help immediately matters more than anything I can tell you."
)

SELF_HARM_MESSAGE = (
    "I'm really sorry you're going through this. You are not alone, and help is available right now. "
    "If you might act on these thoughts or are in immediate danger, please call your local emergency "
    "number now (112 in India, 911 in the US, 999 in the UK). You can also reach a crisis line: "
    "Tele-MANAS 14416 (India), 988 Suicide & Crisis Lifeline (US), Samaritans 116 123 (UK and Ireland). "
    "If you can, reach out to someone you trust and stay with them."
)

DIAGNOSIS_REFUSAL = (
    "I can't diagnose conditions or tell you what is causing your symptoms. A healthcare professional "
    "who can examine you can do that. I'm happy to share general information about a condition or "
    "its symptoms from trusted sources."
)

DOSING_REFUSAL = (
    "I can't advise on doses or how much medicine to take, because the right amount depends on your "
    "age, health and other medicines. Please ask a pharmacist or healthcare professional, or follow "
    "the instructions that came with the medicine."
)

PRESCRIPTION_REFUSAL = (
    "I can't prescribe or recommend specific medicines, or advise you to start, stop or change one. "
    "Please talk to a doctor, pharmacist or other healthcare professional. I can share general "
    "information about a treatment if that helps."
)

BLOCK_NOTICE = (
    "I can't continue this answer safely. Please talk to a healthcare professional."
)

DISCLAIMER = (
    "This is general health information, not medical advice. It does not replace a healthcare "
    "professional. In an emergency, call your local emergency number."
)

NO_CONTEXT_MESSAGE = (
    "I don't have enough information in my sources to answer that. I can help with general health "
    "questions about conditions, symptoms, treatments and healthy habits. For anything about your own "
    "health, please talk to a healthcare professional."
)

GREETING_MESSAGE = (
    "Hi! I'm VitalNest, an AI assistant that shares general health information from MedlinePlus, WHO and the CDC. "
    "Ask me about a condition, a symptom or a treatment, and I'll show you where the answer comes from. "
    "Please don't enter personal health details."
)

THANKS_MESSAGE = (
    "You're welcome! Ask me anything else about a condition, symptom or treatment. For anything about "
    "your own health, please talk to a healthcare professional."
)

GOODBYE_MESSAGE = (
    "Take care! If you ever have a medical emergency, call your local emergency number straight away."
)

OUT_OF_SCOPE_REFUSAL = (
    "I can only help with general health and wellness questions. Try asking about a condition, "
    "symptom, treatment or healthy habit."
)
