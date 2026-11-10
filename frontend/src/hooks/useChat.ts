import { useCallback, useRef, useState } from 'react'
import { friendlyError, streamChat } from '../lib/api/sse'
import { ApiError, type ChatEvent, type ChatRequest } from '../lib/api/types'
import { applyEvent, historyFrom, newAssistant, type AssistantMessage, type ChatMessage } from '../lib/chatState'
import { MAX_MESSAGE_CHARS, trimHistory } from '../lib/limits'

export type StreamFn = (request: ChatRequest, options: { signal: AbortSignal }) => AsyncGenerator<ChatEvent>

/** Owns the conversation: sending a question, streaming the answer into state, stopping, and retrying. */
export function useChat(stream: StreamFn = streamChat) {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [busy, setBusy] = useState(false)
  const controller = useRef<AbortController | null>(null)
  const counter = useRef(0)
  const busyRef = useRef(false)

  const patch = useCallback((id: string, change: (message: AssistantMessage) => AssistantMessage) => {
    setMessages((current) => current.map((m) => (m.id === id && m.role === 'assistant' ? change(m) : m)))
  }, [])

  /** `base` is the conversation shown so far including the question; `prior` is what came before it. */
  const begin = useCallback(
    async (question: string, prior: ChatMessage[], base: ChatMessage[]) => {
      const id = `a${++counter.current}`
      const request: ChatRequest = { message: question, history: trimHistory(historyFrom(prior), question) }
      setMessages([...base, newAssistant(id, question)])
      const abort = new AbortController()
      controller.current = abort
      busyRef.current = true
      setBusy(true)
      let finished = false
      try {
        for await (const event of stream(request, { signal: abort.signal })) {
          if (event.type === 'done' || event.type === 'error') finished = true
          patch(id, (m) => applyEvent(m, event))
        }
        if (!finished) patch(id, (m) => applyEvent(m, { type: 'error', code: 'incomplete', message: friendlyError('incomplete') }))
      } catch (error) {
        if ((error as Error).name === 'AbortError') {
          patch(id, (m) => ({ ...m, status: 'stopped' }))
        } else {
          const code = error instanceof ApiError ? error.code : 'network_error'
          patch(id, (m) => ({ ...m, status: 'error', error: { code, message: friendlyError(code) } }))
        }
      } finally {
        controller.current = null
        busyRef.current = false
        setBusy(false)
      }
    },
    [stream, patch],
  )

  const send = useCallback(
    (text: string): boolean => {
      const question = text.trim()
      if (busyRef.current || question.length === 0 || question.length > MAX_MESSAGE_CHARS) return false
      const user: ChatMessage = { id: `u${++counter.current}`, role: 'user', text: question }
      void begin(question, messages, [...messages, user])
      return true
    },
    [begin, messages],
  )

  const retry = useCallback(
    (assistantId: string) => {
      if (busyRef.current) return
      const index = messages.findIndex((m) => m.id === assistantId)
      const reply = messages[index]
      if (index < 1 || reply?.role !== 'assistant') return
      void begin(reply.question, messages.slice(0, index - 1), messages.slice(0, index))
    },
    [begin, messages],
  )

  const stop = useCallback(() => controller.current?.abort(), [])
  const reset = useCallback(() => setMessages([]), [])

  return { messages, busy, send, retry, stop, reset, setMessages }
}
