import { useEffect, useRef, useState } from 'react'
import { STARTERS } from '../content'
import { DEMO_OPTIONS, demoConversation, type DemoState } from '../demo/fixtures'
import type { AuthState } from '../hooks/useAuth'
import type { useChat } from '../hooks/useChat'
import { AssistantMessageView } from './AssistantMessageView'
import { Composer } from './Composer'
import { LockIcon } from './icons'
import { pillCoralNav, pillGhost } from './ui'

type Chat = ReturnType<typeof useChat>

function EmptyState({ onAsk, disabled }: { onAsk: (question: string) => void; disabled: boolean }) {
  return (
    <div className="py-6 text-center sm:py-10">
      <h2 className="text-[28px] font-bold leading-tight text-ink sm:text-[34px]">What would you like to know?</h2>
      <p className="mx-auto mt-2 max-w-[46ch] text-muted">Ask about a condition, a symptom or a treatment. Every answer shows where it came from.</p>
      <ul className="mt-6 flex flex-wrap justify-center gap-3" aria-label="Example questions">
        {STARTERS.map(({ label, question }) => (
          <li key={label}>
            <button type="button" disabled={disabled} onClick={() => onAsk(question)} className={pillGhost}>
              {label}
            </button>
          </li>
        ))}
      </ul>
      <p className="mt-6 inline-flex items-center gap-2 text-[15px] text-muted">
        <LockIcon />
        Please don’t enter personal health details.
      </p>
    </div>
  )
}

/** The chat surface: log of messages, demo-state switch, and the composer. */
export function ChatCard({ chat, auth }: { chat: Chat; auth: AuthState }) {
  const { messages, busy, send, stop, retry, setMessages, reset } = chat
  const [demo, setDemo] = useState<DemoState | 'live'>('live')
  const end = useRef<HTMLDivElement>(null)

  useEffect(() => {
    end.current?.scrollIntoView?.({ block: 'nearest' })
  }, [messages])

  const chooseDemo = (value: DemoState | 'live') => {
    setDemo(value)
    if (value === 'live') reset()
    else setMessages(demoConversation(value))
  }

  // When sign-in is set up but the person has not signed in, nothing is sent: they are asked to sign in instead.
  const [needSignIn, setNeedSignIn] = useState(false)
  const blocked = auth.enabled && !auth.signedIn
  useEffect(() => {
    if (!blocked) setNeedSignIn(false)
  }, [blocked])

  const guardedSend = (text: string): boolean => {
    if (blocked) {
      setNeedSignIn(true)
      return false // the typed question stays in the box
    }
    return send(text)
  }

  const ask = (question: string) => {
    if (demo !== 'live') setDemo('live')
    guardedSend(question)
  }

  const lastAssistant = [...messages].reverse().find((m) => m.role === 'assistant')
  // The sample-state switch is for design review. Set VITE_HIDE_DEMO=true to remove it from a release build.
  const showDemo = import.meta.env.VITE_HIDE_DEMO !== 'true'

  return (
    <section id="ask" aria-label="Chat" className="relative z-10 -mt-36 px-4 sm:-mt-44">
      <div className="mx-auto max-w-[760px] overflow-hidden rounded-[28px] border border-line bg-surface shadow-card">
        <div className="flex items-center justify-between gap-3 border-b border-line px-5 py-3 sm:px-6">
          <span className="label-mono hidden text-muted sm:inline">Ask VitalNest</span>
          {showDemo && (
            <label className="flex min-w-0 flex-1 items-center gap-2 sm:flex-none">
              <span className="label-mono shrink-0 text-muted">Demo states</span>
              <select
                value={demo}
                onChange={(e) => chooseDemo(e.target.value as DemoState | 'live')}
                className="min-h-11 min-w-0 flex-1 rounded-full border border-line bg-page px-3 text-[15px] text-ink sm:flex-none"
              >
                {DEMO_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            </label>
          )}
        </div>

        <div role="log" aria-live="polite" aria-relevant="additions text" aria-label="Conversation" className="max-h-[70vh] min-h-[280px] space-y-8 overflow-y-auto px-5 py-6 sm:px-8">
          {messages.length === 0 ? (
            <EmptyState onAsk={ask} disabled={busy} />
          ) : (
            messages.map((message) =>
              message.role === 'user' ? (
                <div key={message.id} className="flex justify-end">
                  <p className="max-w-[85%] whitespace-pre-wrap break-words rounded-[20px] bg-soft px-4 py-2.5 text-ink">{message.text}</p>
                </div>
              ) : (
                <AssistantMessageView key={message.id} message={message} isLatest={message === lastAssistant} busy={busy} onAsk={ask} onRetry={retry} />
              ),
            )
          )}
          <div ref={end} />
        </div>

        {needSignIn && (
          <div role="alert" className="mx-4 mb-3 flex flex-wrap items-center justify-between gap-3 rounded-[20px] bg-soft px-5 py-3 text-ink sm:mx-6">
            <p><strong>Please sign in to ask questions.</strong> Your question stays in the box.</p>
            <button type="button" onClick={auth.signIn} className={pillCoralNav}>Sign in</button>
          </div>
        )}
        <Composer busy={busy} onSend={guardedSend} onStop={stop} />
      </div>
    </section>
  )
}
