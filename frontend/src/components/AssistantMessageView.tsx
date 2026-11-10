import { useEffect, useState } from 'react'
import { DISCLAIMER, MEDLINEPLUS_URL } from '../content'
import { answerText, splitNotice, type AssistantMessage } from '../lib/chatState'
import { Answer } from '../lib/markdown'
import { FollowUps } from './FollowUps'
import { LogoMark, WarningIcon } from './icons'
import { SourceCards } from './SourceCards'
import { pillGhostSmall } from './ui'

interface Props {
  message: AssistantMessage
  isLatest: boolean
  busy: boolean
  onAsk: (question: string) => void
  onRetry: (id: string) => void
}

const capitalise = (text: string) => text.charAt(0).toUpperCase() + text.slice(1)

/** "Showing results for Diabetes. You typed 'diabtes'." Names only the words that were changed. */
function CorrectionNotice({ correction }: { correction: NonNullable<AssistantMessage['correction']> }) {
  const words = correction.changes.length > 0
  const shown = words ? correction.changes.map((c) => c.to).join(', ') : correction.corrected
  const typed = words ? correction.changes.map((c) => `'${c.from}'`).join(', ') : `'${correction.original}'`
  return (
    <p className="max-w-[66ch] text-[15px] text-muted">
      Showing results for <strong className="text-ink">{capitalise(shown)}</strong>. You typed {typed}.
    </p>
  )
}

/** After this long with no answer, the free server is probably waking from sleep (it can take about a minute). */
export const SLOW_START_MS = 6000

function Searching() {
  const [slow, setSlow] = useState(false)
  useEffect(() => {
    const timer = window.setTimeout(() => setSlow(true), SLOW_START_MS)
    return () => window.clearTimeout(timer)
  }, [])
  return (
    <div className="space-y-1" role="status">
      <div className="flex items-center gap-3 text-muted">
        <span className="flex gap-1" aria-hidden>
          <span className="dot" />
          <span className="dot" />
          <span className="dot" />
        </span>
        <span>Searching trusted sources…</span>
      </div>
      {slow && (
        <p className="pl-1 text-[15px] text-muted">
          The service is waking up after a quiet period. The first answer can take up to a minute.
        </p>
      )}
    </div>
  )
}

function EmergencyPanel({ text }: { text: string }) {
  return (
    <div role="alert" className="rounded-2xl bg-emergency p-5 text-on-emergency sm:p-6">
      <p className="label-mono">Emergency</p>
      <p className="mt-2 max-w-[66ch] text-[18px] leading-relaxed">{text}</p>
    </div>
  )
}

function CautionNotice({ text }: { text: string }) {
  return (
    <div role="note" className="flex gap-3 rounded-2xl border border-caution-fg/40 bg-caution-bg p-4 text-caution-fg">
      <WarningIcon className="mt-1 shrink-0" />
      <p className="max-w-[66ch]">{text}</p>
    </div>
  )
}

function NoContextCard({ text }: { text: string }) {
  return (
    <div className="rounded-2xl border-2 border-dashed border-line p-5">
      <p className="max-w-[66ch] text-ink">{text}</p>
      <a href={MEDLINEPLUS_URL} target="_blank" rel="noopener noreferrer" className="mt-3 inline-flex min-h-11 items-center font-bold text-ink underline decoration-2 underline-offset-4">
        Browse MedlinePlus (medlineplus.gov)
        <span className="sr-only"> (opens in a new tab)</span>
      </a>
    </div>
  )
}

function ErrorNotice({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div role="alert" className="flex flex-wrap items-center justify-between gap-3 rounded-2xl bg-emergency p-4 text-on-emergency">
      <p className="max-w-[52ch]">
        <strong>Something went wrong.</strong> {message}
      </p>
      {/* A neutral button on the red notice: safety colours are never used for buttons. */}
      <button type="button" onClick={onRetry} className={`${pillGhostSmall} border-transparent`}>
        Try again
      </button>
    </div>
  )
}

/** One assistant reply in any of its states. It always says it is an AI assistant (no human avatar). */
export function AssistantMessageView({ message, isLatest, busy, onAsk, onRetry }: Props) {
  const text = answerText(message)
  const active = message.status === 'searching' || message.status === 'streaming'
  const finished = message.status === 'done' || message.status === 'stopped'
  const isAnswer = message.kind === 'answer'
  const refused = message.kind === 'refused' ? splitNotice(text) : null

  return (
    <article aria-label="Answer from VitalNest" className="space-y-5">
      <header className="flex flex-wrap items-center gap-2">
        <LogoMark size={24} />
        <span className="font-bold text-ink">VitalNest</span>
        <span className="label-mono rounded-full border border-line px-2.5 py-0.5 text-muted">AI assistant</span>
        {message.demo && <span className="label-mono text-muted">Demo content, not real medical advice</span>}
      </header>

      {message.correction && <CorrectionNotice correction={message.correction} />}

      {message.status === 'searching' && <Searching />}

      {message.kind === 'emergency' && text && <EmergencyPanel text={text.trim()} />}
      {refused && (
        <>
          {refused.body && <Answer text={refused.body} />}
          {refused.notice && <CautionNotice text={refused.notice} />}
        </>
      )}
      {message.kind === 'no_context' && text && <NoContextCard text={text.trim()} />}
      {isAnswer && text && <Answer text={text} />}

      {message.status === 'stopped' && <p className="label-mono text-muted">Stopped</p>}
      {message.status === 'error' && <ErrorNotice message={message.error?.message ?? ''} onRetry={() => onRetry(message.id)} />}

      {isAnswer && message.status !== 'error' && message.status !== 'stopped' && (
        <SourceCards sources={message.sources} loading={active} />
      )}

      {finished && message.status === 'done' && (
        <p className="max-w-[66ch] text-[14px] leading-relaxed text-muted">{message.disclaimer || DISCLAIMER}</p>
      )}

      {isLatest && message.status === 'done' && isAnswer && (
        <FollowUps questions={message.suggestions} disabled={busy} onAsk={onAsk} />
      )}
    </article>
  )
}
