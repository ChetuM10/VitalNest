/** Approved wording (see backend/app/safety/messages.py). The server sends these too; copies here are used for demo content and fallbacks. */
export const DISCLAIMER =
  'This is general health information, not medical advice. It does not replace a healthcare professional. In an emergency, call your local emergency number.'

export const EMERGENCY_MESSAGE =
  "This sounds like it could be a medical emergency. Please call your local emergency number right now (for example 112 in India and the EU, 911 in the US and Canada, 999 in the UK) or go to the nearest emergency department. If someone is with you, ask them to help. I can't assess emergencies, and getting help immediately matters more than anything I can tell you."

export const NO_CONTEXT_MESSAGE =
  "I don't have enough information in my sources to answer that. I can help with general health questions about conditions, symptoms, treatments and healthy habits. For anything about your own health, please talk to a healthcare professional."

export const STARTERS = [
  { label: 'Asthma symptoms', question: 'What are the symptoms of asthma?' },
  { label: 'Managing type 2 diabetes', question: 'How is type 2 diabetes managed?' },
  { label: 'Sleeping better', question: 'How can I sleep better?' },
]

export const MEDLINEPLUS_URL = 'https://medlineplus.gov/'
