import { useState } from 'react'
import type { SourceItem } from '../lib/api/types'
import { safeUrl } from '../lib/markdown'
import { pillGhostSmall } from './ui'
import { ExternalIcon } from './icons'

const VISIBLE = 2

/** Snippets are cut from the middle of a page, so they can start with a list dash or contain flattened "- item - item" lists. */
export function cleanSnippet(text: string): string {
  return text.replace(/^\s*[-•*]\s+/, '').replace(/\s[-•]\s+(?=[A-Z0-9])/g, ' · ').trim()
}

/** "MedlinePlus · National Library of Medicine", taken from the attribution the server sends. */
export function sourceLabel(source: SourceItem): string {
  const organisation = /from (?:the )?(.+)$/i.exec(source.attribution)?.[1]
  return organisation ? `${source.source_name} · ${organisation}` : source.source_name
}

export function SourceCards({ sources, loading }: { sources: SourceItem[]; loading: boolean }) {
  const [expanded, setExpanded] = useState(false)
  const shown = expanded ? sources : sources.slice(0, VISIBLE)
  const hidden = sources.length - VISIBLE

  if (!loading && sources.length === 0) return null

  return (
    <section aria-label="Sources" aria-busy={loading}>
      <h3 className="label-mono mb-3 text-muted">Sources</h3>
      {loading ? (
        <div className="grid gap-3 sm:grid-cols-2" aria-hidden>
          {[0, 1].map((n) => (
            <div key={n} className="rounded-2xl border border-line p-4">
              <div className="skeleton h-5 w-2/3" />
              <div className="skeleton mt-2 h-3 w-1/2" />
              <div className="skeleton mt-4 h-3 w-full" />
              <div className="skeleton mt-2 h-3 w-full" />
              <div className="skeleton mt-2 h-3 w-4/5" />
            </div>
          ))}
        </div>
      ) : (
        <>
          <ul className="grid gap-3 sm:grid-cols-2">
            {shown.map((source) => (
              <li key={source.url} className="flex flex-col rounded-2xl border border-line bg-surface p-4">
                <h4 className="text-[17px] font-bold leading-snug text-ink">{source.title}</h4>
                <p className="label-mono mt-1 text-muted">{sourceLabel(source)}</p>
                <p className="mt-3 line-clamp-3 text-[15px] leading-relaxed text-muted">{cleanSnippet(source.snippet)}</p>
                <a
                  href={safeUrl(source.url)}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="mt-3 inline-flex min-h-11 items-center gap-1.5 self-start text-[15px] font-bold text-ink underline decoration-2 underline-offset-4"
                >
                  Open source
                  <ExternalIcon />
                  <span className="sr-only"> ({source.title}, opens in a new tab)</span>
                </a>
              </li>
            ))}
          </ul>
          {hidden > 0 && (
            <button type="button" className={`${pillGhostSmall} mt-3`} aria-expanded={expanded} onClick={() => setExpanded((v) => !v)}>
              {expanded ? 'Show fewer sources' : `Show ${hidden} more source${hidden === 1 ? '' : 's'}`}
            </button>
          )}
        </>
      )}
    </section>
  )
}
