import { getAccessToken, getSession } from '../auth/cognito'
import { ApiError, type ChatEvent, type ChatRequest, type SafetyStatus } from './types'

/** Turn one Server-Sent Event block ("event: x" then "data: {...}") into a typed event, or null if unknown. */
export function parseSseBlock(block: string): ChatEvent | null {
  let name = ''
  const data: string[] = []
  for (const line of block.split('\n')) {
    if (line.startsWith('event:')) name = line.slice(6).trim()
    else if (line.startsWith('data:')) data.push(line.slice(5).replace(/^ /, ''))
  }
  if (!name) return null
  let payload: Record<string, unknown>
  try {
    payload = JSON.parse(data.join('\n') || '{}')
  } catch {
    return null
  }
  switch (name) {
    case 'token':
      return typeof payload.text === 'string' ? { type: 'token', text: payload.text } : null
    case 'sources':
      return Array.isArray(payload.sources) ? { type: 'sources', sources: payload.sources as never } : null
    case 'suggestions':
      return Array.isArray(payload.suggested_questions)
        ? { type: 'suggestions', questions: payload.suggested_questions.filter((q): q is string => typeof q === 'string') }
        : null
    case 'safety':
      return { type: 'safety', status: payload.status as SafetyStatus, disclaimer: String(payload.disclaimer ?? '') }
    case 'corrected':
      return typeof payload.original === 'string' && typeof payload.corrected === 'string'
        ? {
            type: 'corrected',
            original: payload.original,
            corrected: payload.corrected,
            changes: Array.isArray(payload.changes)
              ? (payload.changes as { from?: unknown; to?: unknown }[]).filter((c) => typeof c.from === 'string' && typeof c.to === 'string').map((c) => ({ from: c.from as string, to: c.to as string }))
              : [],
          }
        : null
    case 'done':
      return { type: 'done' }
    case 'error':
      return { type: 'error', code: String(payload.code ?? 'error'), message: String(payload.message ?? 'Something went wrong.') }
    default:
      return null
  }
}

/** Read events from a response body. Chunk boundaries can fall anywhere, so text is buffered until a blank line. */
export async function* readEvents(body: ReadableStream<Uint8Array>): AsyncGenerator<ChatEvent> {
  const reader = body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  try {
    for (;;) {
      const { done, value } = await reader.read()
      buffer += decoder.decode(value, { stream: !done }).replace(/\r\n/g, '\n')
      let boundary = buffer.indexOf('\n\n')
      while (boundary !== -1) {
        const event = parseSseBlock(buffer.slice(0, boundary))
        buffer = buffer.slice(boundary + 2)
        if (event) yield event
        boundary = buffer.indexOf('\n\n')
      }
      if (done) break
    }
    const last = parseSseBlock(buffer.trim())
    if (last) yield last
  } finally {
    reader.releaseLock()
  }
}

/** Bearer header with the signed-in person's Cognito access token. Empty when signed out (the server then says 401). */
export async function getAuthHeaders(): Promise<Record<string, string>> {
  const token = await getAccessToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}


export interface StreamOptions {
  signal?: AbortSignal
  baseUrl?: string
  headers?: Record<string, string>
}

/** POST /v1/chat and yield its events. Errors before streaming (401, 413, 422, 502, ...) become an ApiError. */
export async function* streamChat(request: ChatRequest, options: StreamOptions = {}): AsyncGenerator<ChatEvent> {
  const baseUrl = options.baseUrl ?? import.meta.env.VITE_API_BASE_URL ?? ''
  let response: Response
  try {
    // Signed out: no waiting at all, the request goes out at once (the server answers 401).
    const auth = getSession() ? await getAuthHeaders() : {}
    response = await fetch(`${baseUrl}/v1/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream', ...auth, ...options.headers },
      body: JSON.stringify(request),
      signal: options.signal,
    })
  } catch (error) {
    if ((error as Error).name === 'AbortError') throw error
    throw new ApiError('network_error', 'Could not reach the service.')
  }

  if (!response.ok || !response.body) {
    let code = 'error'
    let message = 'Something went wrong.'
    try {
      const body = await response.json()
      code = body?.error?.code ?? code
      message = body?.error?.message ?? message
    } catch {
      /* the body was not JSON */
    }
    throw new ApiError(code, message, response.status)
  }
  yield* readEvents(response.body)
}

/** Plain-language text for each error code, shown to the person instead of technical details. */
export function friendlyError(code: string): string {
  switch (code) {
    case 'unauthorized':
      return 'Please sign in to ask a question.'
    case 'payload_too_large':
      return 'That conversation is too long. Start a new question and try again.'
    case 'validation_error':
      return 'That question could not be sent. Please shorten it and try again.'
    case 'rate_limited':
      return 'You have asked a lot of questions in a short time, or reached the daily limit. Please wait a while and try again.'
    case 'timeout':
      return 'The answer took too long. Please try again.'
    case 'service_unavailable':
      return 'The service is not available right now. Please try again later.'
    case 'network_error':
      return 'Could not reach the service. Check your connection, then try again in a moment.'
    case 'incomplete':
      return 'The answer stopped before it was finished.'
    default:
      return 'Something went wrong while answering. Please try again.'
  }
}
