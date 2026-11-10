import { ReplyArrowIcon } from './icons'

/**
 * Related questions, styled like Perplexity's: a thin divider, then one row per question with a
 * corner-arrow icon and large plain text. Rows, not chips. Choosing one asks it.
 */
export function FollowUps({ questions, disabled, onAsk }: { questions: string[]; disabled: boolean; onAsk: (question: string) => void }) {
  if (questions.length === 0) return null
  return (
    <section aria-labelledby="related-heading" className="mt-2 border-t border-line">
      <h3 id="related-heading" className="sr-only">Related questions</h3>
      <ul>
        {questions.slice(0, 3).map((question) => (
          <li key={question} className="border-b border-line last:border-b-0">
            <button
              type="button"
              disabled={disabled}
              onClick={() => onAsk(question)}
              className="group flex min-h-14 w-full items-start gap-4 py-4 text-left text-[18px] leading-snug text-ink transition hover:bg-soft disabled:cursor-not-allowed disabled:opacity-50 sm:px-2"
            >
              <ReplyArrowIcon className="mt-0.5 shrink-0 text-muted transition group-hover:text-ink" />
              <span className="group-hover:underline group-hover:underline-offset-4">{question}</span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  )
}
