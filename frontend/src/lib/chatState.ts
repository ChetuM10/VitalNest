import type { ChatEvent, HistoryItem, SourceItem } from './api/types'

export type MessageKind = 'answer' | 'emergency' | 'refused' | 'no_context'
export type AssistantStatus = 'searching' | 'streaming' | 'done' | 'stopped' | 'error'

export interface UserMessage {
  id: string
  role: 'user'
  text: string
}

export interface AssistantMessage {
  id: string
  role: 'assistant'
  /** The question this answers, kept so "Try again" can ask it again. */
  question: string
  status: AssistantStatus
  kind: MessageKind
  /** Text as it arrived: one entry per streamed event (a sentence or list item). */
  segments: string[]
  sources: SourceItem[]
  suggestions: string[]
  disclaimer: string | null
  /** Set when the server corrected a misspelling in the question. */
  correction: { original: string; corrected: string; changes: { from: string; to: string }[] } | null
  error: { code: string; message: string } | null
  /** True for sample content shown by the "Demo states" switch. */
  demo: boolean
}

export type ChatMessage = UserMessage | AssistantMessage

/** The fixed notice the server appends when it stops an answer part-way (decision D1a). */
export const BLOCK_NOTICE = "I can't continue this answer safely. Please talk to a healthcare professional."

export function newAssistant(id: string, question: string, demo = false): AssistantMessage {
  return {
    id, role: 'assistant', question, status: 'searching', kind: 'answer',
    segments: [], sources: [], suggestions: [], disclaimer: null, correction: null, error: null, demo,
  }
}

/** Fold one server event into the message. Pure, so it is easy to test. */
export function applyEvent(message: AssistantMessage, event: ChatEvent): AssistantMessage {
  switch (event.type) {
    case 'token':
      return { ...message, status: 'streaming', segments: [...message.segments, event.text] }
    case 'sources':
      return { ...message, sources: event.sources }
    case 'suggestions':
      return { ...message, suggestions: event.questions }
    case 'safety':
      return { ...message, kind: event.status === 'ok' ? 'answer' : event.status, disclaimer: event.disclaimer }
    case 'corrected':
      return { ...message, correction: { original: event.original, corrected: event.corrected, changes: event.changes } }
    case 'done':
      return message.status === 'error' ? message : { ...message, status: 'done' }
    case 'error':
      return { ...message, status: 'error', error: { code: event.code, message: event.message } }
  }
}

export function answerText(message: AssistantMessage): string {
  return message.segments.join('')
}

/** For a refused answer: the approved sentences, and the fixed notice if the answer was stopped part-way. */
export function splitNotice(text: string): { body: string; notice: string | null } {
  const trimmed = text.trimEnd()
  if (trimmed.endsWith(BLOCK_NOTICE)) return { body: trimmed.slice(0, -BLOCK_NOTICE.length).trim(), notice: BLOCK_NOTICE }
  return { body: '', notice: trimmed }
}

/** Completed question/answer pairs to send as conversation context. Demo content and failed answers are left out. */
export function historyFrom(messages: ChatMessage[]): HistoryItem[] {
  const history: HistoryItem[] = []
  for (let i = 0; i + 1 < messages.length; i++) {
    const user = messages[i]
    const reply = messages[i + 1]
    if (user.role === 'user' && reply.role === 'assistant' && reply.status === 'done' && reply.kind === 'answer' && !reply.demo) {
      history.push({ role: 'user', content: user.text }, { role: 'assistant', content: answerText(reply).trim() })
    }
  }
  return history
}
