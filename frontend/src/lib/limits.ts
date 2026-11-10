import type { HistoryItem } from './api/types'

/** The approved input limits (decision G5). The backend is the authority; these give instant feedback. */
export const MAX_MESSAGE_CHARS = 500
export const MAX_HISTORY_MESSAGES = 20
export const MAX_TOTAL_CHARS = 8000
export const WARN_FROM = 450

export type CounterTone = 'normal' | 'warn' | 'over'

export function counterTone(length: number): CounterTone {
  if (length > MAX_MESSAGE_CHARS) return 'over'
  return length >= WARN_FROM ? 'warn' : 'normal'
}

/**
 * Pick the conversation history to send: whole question/answer pairs, newest kept, so that there are at most
 * 20 messages and the current message plus history stay within 8,000 characters. The oldest pairs are dropped
 * first (decision D2: the client trims; the server rejects and never silently cuts).
 */
export function trimHistory(history: HistoryItem[], currentMessage: string): HistoryItem[] {
  const pairs: HistoryItem[][] = []
  for (let i = 0; i + 1 < history.length; i += 2) pairs.push([history[i], history[i + 1]])
  const size = (items: HistoryItem[][]) =>
    items.reduce((sum, pair) => sum + pair[0].content.trim().length + pair[1].content.trim().length, 0)

  const budget = MAX_TOTAL_CHARS - currentMessage.trim().length
  while (pairs.length > 0 && (pairs.length * 2 > MAX_HISTORY_MESSAGES || size(pairs) > budget)) pairs.shift()
  return pairs.flat()
}
