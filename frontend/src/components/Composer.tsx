import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import { MAX_MESSAGE_CHARS, counterTone } from '../lib/limits'
import { SendIcon, StopIcon } from './icons'

interface Props {
  busy: boolean
  onSend: (text: string) => boolean
  onStop: () => void
}

const MAX_HEIGHT = 168

const toneClass = { normal: 'text-muted', warn: 'text-caution-fg bg-caution-bg px-2 rounded-full', over: 'text-on-emergency bg-emergency px-2 rounded-full' }

/** Auto-growing textarea with a live character counter, and a round send button that becomes Stop while answering. */
export function Composer({ busy, onSend, onStop }: Props) {
  const [text, setText] = useState('')
  const ref = useRef<HTMLTextAreaElement>(null)
  const length = text.trim().length
  const tone = counterTone(length)
  const empty = length === 0
  const canSend = !empty && tone !== 'over' && !busy

  useEffect(() => {
    const el = ref.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, MAX_HEIGHT)}px`
  }, [text])

  const submit = (event?: FormEvent) => {
    event?.preventDefault()
    if (!canSend) return
    if (onSend(text)) setText('')
  }

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault()
      submit()
    }
  }

  return (
    <form onSubmit={submit} className="border-t border-line px-4 pb-4 pt-3 sm:px-6" aria-label="Ask a question">
      <div className="flex items-end gap-3 rounded-[22px] border border-line bg-page px-4 py-2.5 focus-within:border-ink">
        <label htmlFor="composer-input" className="sr-only">Your question</label>
        <textarea
          id="composer-input"
          ref={ref}
          rows={1}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Ask about a condition, symptom or treatment"
          aria-describedby="composer-counter composer-note"
          className="max-h-[168px] min-h-11 flex-1 resize-none bg-transparent py-2 text-[17px] text-ink outline-none placeholder:text-muted"
        />
        {busy ? (
          <button type="button" onClick={onStop} aria-label="Stop answering" className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-ink text-page transition hover:opacity-90">
            <StopIcon />
          </button>
        ) : (
          <button
            type="submit"
            disabled={!canSend}
            aria-label="Send question"
            className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-coral text-on-coral transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-40"
          >
            <SendIcon />
          </button>
        )}
      </div>
      <div className="mt-2 flex items-center justify-between gap-3 px-2">
        <p id="composer-note" className="text-[14px] text-muted">
          Informational only. Please don’t enter personal health details.
        </p>
        <span
          id="composer-counter"
          className={`label-mono shrink-0 py-0.5 ${toneClass[tone]}`}
          aria-live={tone === 'normal' ? 'off' : 'polite'}
        >
          {length}/{MAX_MESSAGE_CHARS}
          {tone === 'over' && <span className="sr-only"> too long: shorten your question to send it</span>}
        </span>
      </div>
    </form>
  )
}
