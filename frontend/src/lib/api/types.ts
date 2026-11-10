/** Shapes defined by the API contract (docs/VITALNEST_COMPLETE_PLAN.md, section 6). */
export type Role = 'user' | 'assistant'

export interface HistoryItem {
  role: Role
  content: string
}

export interface ChatRequest {
  message: string
  history: HistoryItem[]
}

export interface SourceItem {
  title: string
  url: string
  snippet: string
  source_name: string
  attribution: string
}

export type SafetyStatus = 'ok' | 'emergency' | 'refused' | 'no_context'

export type ChatEvent =
  | { type: 'token'; text: string }
  | { type: 'sources'; sources: SourceItem[] }
  | { type: 'suggestions'; questions: string[] }
  | { type: 'safety'; status: SafetyStatus; disclaimer: string }
  /** The server fixed a misspelling and searched with the corrected question. */
  | { type: 'corrected'; original: string; corrected: string; changes: { from: string; to: string }[] }
  | { type: 'done' }
  | { type: 'error'; code: string; message: string }

/** A failure reported by the server before streaming started (HTTP 4xx/5xx), or a network problem. */
export class ApiError extends Error {
  readonly code: string
  readonly status: number

  constructor(code: string, message: string, status = 0) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.status = status
  }
}
