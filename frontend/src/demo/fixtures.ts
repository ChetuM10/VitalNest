import { BLOCK_NOTICE, applyEvent, newAssistant, type AssistantMessage, type ChatMessage } from '../lib/chatState'
import type { ChatEvent, SourceItem } from '../lib/api/types'
import { DISCLAIMER, EMERGENCY_MESSAGE, NO_CONTEXT_MESSAGE } from '../content'

/** Sample conversations for the "Demo states" switch. Every one is labelled "Demo content, not real medical advice". */
export type DemoState = 'normal' | 'corrected' | 'emergency' | 'refused' | 'no_context' | 'error'

export const DEMO_OPTIONS: { value: DemoState | 'live'; label: string }[] = [
  { value: 'live', label: 'Live (real answers)' },
  { value: 'normal', label: 'Normal answer' },
  { value: 'corrected', label: 'Spelling corrected' },
  { value: 'emergency', label: 'Emergency' },
  { value: 'refused', label: 'Refused mid-answer' },
  { value: 'no_context', label: 'Not enough information' },
  { value: 'error', label: 'Stream error' },
]

const SOURCES: SourceItem[] = [
  {
    title: 'Asthma',
    url: 'https://medlineplus.gov/asthma.html',
    snippet:
      'Asthma is a disease that affects your lungs. It causes repeated episodes of wheezing, breathlessness, chest tightness, and nighttime or early morning coughing. Symptoms can range from mild to severe and may come and go.',
    source_name: 'MedlinePlus',
    attribution: 'Courtesy of MedlinePlus from the National Library of Medicine',
  },
  {
    title: 'Asthma in Children',
    url: 'https://medlineplus.gov/asthmainchildren.html',
    snippet:
      'Asthma is a chronic lung disease that causes breathing problems. In children it can also bring tiredness, irritability, and rapid breathing. Your provider can help you make a plan for managing it.',
    source_name: 'MedlinePlus',
    attribution: 'Courtesy of MedlinePlus from the National Library of Medicine',
  },
]

const token = (text: string): ChatEvent => ({ type: 'token', text })

function build(id: string, question: string, events: ChatEvent[]): ChatMessage[] {
  const reply = events.reduce<AssistantMessage>((message, event) => applyEvent(message, event), { ...newAssistant(id, question, true) })
  return [{ id: `${id}-q`, role: 'user', text: question }, reply]
}

export function demoConversation(state: DemoState): ChatMessage[] {
  switch (state) {
    case 'normal':
      return build('demo-normal', 'What are the symptoms of asthma?', [
        token('Asthma is a long-term lung condition that affects the airways. '),
        token('Common symptoms include:\n'),
        token('- Wheezing, a whistling sound when you breathe out\n'),
        token('- Coughing, especially at night or early in the morning\n'),
        token('- Chest tightness and shortness of breath\n'),
        token('Symptoms can be mild or severe, and they may come and go. '),
        token('If you are worried about your breathing, please talk with a healthcare professional.'),
        { type: 'sources', sources: SOURCES },
        { type: 'suggestions', questions: ['What are common asthma triggers?', 'How is asthma diagnosed?', 'How is asthma treated in children?'] },
        { type: 'safety', status: 'ok', disclaimer: DISCLAIMER },
        { type: 'done' },
      ])
    case 'corrected':
      return build('demo-corrected', 'Tell me about Alzeihmers', [
        { type: 'corrected', original: 'Tell me about Alzeihmers', corrected: "Tell me about Alzheimer's", changes: [{ from: 'Alzeihmers', to: "Alzheimer's" }] },
        token("Alzheimer's disease is the most common cause of dementia in older adults. "),
        token('It affects memory, thinking and everyday skills, and it usually begins slowly and gets worse over time. '),
        token('If you are worried about memory changes, please talk with a healthcare professional.'),
        { type: 'sources', sources: [{ title: "Alzheimer's Disease", url: 'https://medlineplus.gov/alzheimersdisease.html', snippet: "Alzheimer's disease (AD) is the most common form of dementia among older people. It affects the parts of the brain that control thought, memory, and language.", source_name: 'MedlinePlus', attribution: 'Courtesy of MedlinePlus from the National Library of Medicine' }] },
        { type: 'suggestions', questions: ["What are the early signs of Alzheimer's?", 'How is dementia diagnosed?', 'How can caregivers cope?'] },
        { type: 'safety', status: 'ok', disclaimer: DISCLAIMER },
        { type: 'done' },
      ])
    case 'emergency':
      return build('demo-emergency', 'I have chest pain and I can’t breathe', [
        token(EMERGENCY_MESSAGE),
        { type: 'safety', status: 'emergency', disclaimer: DISCLAIMER },
        { type: 'done' },
      ])
    case 'refused':
      return build('demo-refused', 'How do I manage type 2 diabetes?', [
        token('Type 2 diabetes is usually managed with healthy eating, regular physical activity, and for many people, medicine. '),
        token('Keeping blood sugar in a healthy range lowers the risk of complications.'),
        token(`\n\n${BLOCK_NOTICE}`),
        { type: 'safety', status: 'refused', disclaimer: DISCLAIMER },
        { type: 'done' },
      ])
    case 'no_context':
      return build('demo-nocontext', 'How do I train for a marathon?', [
        token(NO_CONTEXT_MESSAGE),
        { type: 'safety', status: 'no_context', disclaimer: DISCLAIMER },
        { type: 'done' },
      ])
    case 'error':
      return build('demo-error', 'How can I sleep better?', [
        token('Most adults need about seven or more hours of sleep a night. '),
        token('Keeping a regular sleep schedule, limiting caffeine late in the day, and keeping your bedroom dark and quiet can all help. '),
        { type: 'error', code: 'upstream_error', message: 'The AI service is unavailable.' },
      ])
  }
}
