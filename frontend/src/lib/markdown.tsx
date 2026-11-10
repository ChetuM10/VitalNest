import type { ReactNode } from 'react'

/**
 * A deliberately tiny, safe renderer for the answers' markdown: paragraphs, "- " bullet lists and **bold**.
 * It builds React elements only (never raw HTML), so text from the model or the sources cannot inject markup.
 */
export type Block = { type: 'p'; text: string } | { type: 'ul'; items: string[] }

export function parseBlocks(text: string): Block[] {
  const blocks: Block[] = []
  let paragraph: string[] = []
  let list: string[] = []
  const flushParagraph = () => {
    if (paragraph.length) blocks.push({ type: 'p', text: paragraph.join(' ') })
    paragraph = []
  }
  const flushList = () => {
    if (list.length) blocks.push({ type: 'ul', items: list })
    list = []
  }
  for (const raw of text.split('\n')) {
    const line = raw.trim()
    const bullet = /^[-*•]\s+(.*)$/.exec(line)
    if (bullet) {
      flushParagraph()
      list.push(bullet[1])
    } else if (!line) {
      flushParagraph()
      flushList()
    } else {
      flushList()
      paragraph.push(line)
    }
  }
  flushParagraph()
  flushList()
  return blocks
}

/** Only https links are ever opened; anything else (javascript:, data:, http:) becomes a harmless "#". */
export function safeUrl(url: string): string {
  try {
    return new URL(url).protocol === 'https:' ? url : '#'
  } catch {
    return '#'
  }
}

function renderBold(text: string, keyPrefix: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*)/).filter(Boolean).map((part, index) =>
    part.startsWith('**') && part.endsWith('**') && part.length > 4 ? (
      <strong key={`${keyPrefix}-b${index}`}>{part.slice(2, -2)}</strong>
    ) : (
      part
    ),
  )
}

/** Each sentence is its own keyed span, so only newly arrived sentences mount and fade in. */
function renderSentences(text: string, keyPrefix: string): ReactNode[] {
  return text.split(/(?<=[.!?])\s+/).filter(Boolean).map((sentence, index) => (
    <span key={`${keyPrefix}-s${index}`} className="fade-in">
      {index > 0 ? ' ' : ''}
      {renderBold(sentence, `${keyPrefix}-s${index}`)}
    </span>
  ))
}

export function Answer({ text }: { text: string }) {
  const blocks = parseBlocks(text)
  return (
    <div className="answer-text space-y-4 max-w-[66ch]">
      {blocks.map((block, blockIndex) =>
        block.type === 'p' ? (
          <p key={`p${blockIndex}`}>{renderSentences(block.text, `p${blockIndex}`)}</p>
        ) : (
          <ul key={`u${blockIndex}`} className="list-disc space-y-1.5 pl-6 marker:text-muted">
            {block.items.map((item, itemIndex) => (
              <li key={`u${blockIndex}-i${itemIndex}`}>{renderSentences(item, `u${blockIndex}-i${itemIndex}`)}</li>
            ))}
          </ul>
        ),
      )}
    </div>
  )
}
