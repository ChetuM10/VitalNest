import { describe, expect, it } from 'vitest'
import type { HistoryItem } from './api/types'
import { BLOCK_NOTICE, answerText, applyEvent, historyFrom, newAssistant, splitNotice, type ChatMessage } from './chatState'
import { MAX_HISTORY_MESSAGES, MAX_MESSAGE_CHARS, MAX_TOTAL_CHARS, counterTone, trimHistory } from './limits'

describe('counterTone', () => {
  it('is normal below 450, amber from 450, and over above 500', () => {
    expect([0, 449].map(counterTone)).toEqual(['normal', 'normal'])
    expect([450, 500].map(counterTone)).toEqual(['warn', 'warn'])
    expect([501, 900].map(counterTone)).toEqual(['over', 'over'])
    expect(MAX_MESSAGE_CHARS).toBe(500)
  })
})

const pair = (n: number, size = 10): HistoryItem[] => [
  { role: 'user', content: `q${n}`.padEnd(size, 'x') },
  { role: 'assistant', content: `a${n}`.padEnd(size, 'y') },
]

describe('trimHistory', () => {
  it('keeps short history unchanged', () => {
    const history = [...pair(1), ...pair(2)]
    expect(trimHistory(history, 'next question')).toEqual(history)
  })

  it('keeps at most 20 messages, dropping the oldest pairs first', () => {
    const history = Array.from({ length: 15 }, (_, i) => pair(i)).flat() // 30 messages
    const trimmed = trimHistory(history, 'next')
    expect(trimmed).toHaveLength(MAX_HISTORY_MESSAGES)
    expect(trimmed[0].content.startsWith('q5')).toBe(true)
    expect(trimmed.at(-1)?.content.startsWith('a14')).toBe(true)
  })

  it('keeps the total (history plus the new message) within 8,000 characters', () => {
    const history = Array.from({ length: 8 }, (_, i) => pair(i, 1000)).flat() // 16,000 characters
    const trimmed = trimHistory(history, 'm'.repeat(500))
    const total = trimmed.reduce((sum, m) => sum + m.content.length, 0) + 500
    expect(total).toBeLessThanOrEqual(MAX_TOTAL_CHARS)
    expect(trimmed.length).toBeGreaterThan(0)
  })

  it('always drops whole pairs so the history still starts with a user turn', () => {
    const trimmed = trimHistory(Array.from({ length: 12 }, (_, i) => pair(i, 900)).flat(), 'hello')
    expect(trimmed[0].role).toBe('user')
    expect(trimmed.length % 2).toBe(0)
  })

  it('returns nothing when even one pair does not fit', () => {
    expect(trimHistory(pair(1, 4500), 'm'.repeat(500))).toEqual([])
  })
})

describe('applyEvent', () => {
  it('moves from searching to streaming on the first token and collects segments', () => {
    let message = newAssistant('a1', 'What is asthma?')
    expect(message.status).toBe('searching')
    message = applyEvent(message, { type: 'token', text: 'Asthma is common. ' })
    message = applyEvent(message, { type: 'token', text: 'It affects airways.' })
    expect(message.status).toBe('streaming')
    expect(answerText(message)).toBe('Asthma is common. It affects airways.')
  })

  it('completes with sources, suggestions, the safety disclaimer and done', () => {
    let message = newAssistant('a1', 'q')
    message = applyEvent(message, { type: 'token', text: 'Answer.' })
    message = applyEvent(message, { type: 'sources', sources: [{ title: 'Asthma', url: 'https://medlineplus.gov/asthma.html', snippet: 's', source_name: 'MedlinePlus', attribution: 'a' }] })
    message = applyEvent(message, { type: 'suggestions', questions: ['Next?'] })
    message = applyEvent(message, { type: 'safety', status: 'ok', disclaimer: 'Not medical advice.' })
    message = applyEvent(message, { type: 'done' })
    expect(message).toMatchObject({ status: 'done', kind: 'answer', disclaimer: 'Not medical advice.', suggestions: ['Next?'] })
    expect(message.sources).toHaveLength(1)
  })

  it('records a spelling correction', () => {
    const changes = [{ from: 'Alzeihmers', to: 'Alzheimers' }]
    const message = applyEvent(newAssistant('a1', 'q'), { type: 'corrected', original: 'Alzeihmers', corrected: 'Alzheimers', changes })
    expect(message.correction).toEqual({ original: 'Alzeihmers', corrected: 'Alzheimers', changes })
  })

  it.each(['emergency', 'refused', 'no_context'] as const)('records the %s safety status as the message kind', (status) => {
    const message = applyEvent(newAssistant('a1', 'q'), { type: 'safety', status, disclaimer: 'D' })
    expect(message.kind).toBe(status)
  })

  it('keeps the partial answer when an error event arrives, and a later done does not hide the error', () => {
    let message = applyEvent(newAssistant('a1', 'q'), { type: 'token', text: 'Partial. ' })
    message = applyEvent(message, { type: 'error', code: 'upstream_error', message: 'x' })
    message = applyEvent(message, { type: 'done' })
    expect(message.status).toBe('error')
    expect(message.error?.code).toBe('upstream_error')
    expect(answerText(message)).toBe('Partial. ')
  })
})

describe('splitNotice', () => {
  it('separates the approved sentences from the fixed notice', () => {
    expect(splitNotice(`Asthma is common.\n\n${BLOCK_NOTICE}`)).toEqual({ body: 'Asthma is common.', notice: BLOCK_NOTICE })
  })

  it('treats a whole refusal reply (no approved sentences) as the notice', () => {
    expect(splitNotice('I can’t advise on doses.')).toEqual({ body: '', notice: 'I can’t advise on doses.' })
  })
})

describe('historyFrom', () => {
  const done = (id: string, question: string, text: string, extra: object = {}) => ({
    ...applyEvent(applyEvent(newAssistant(id, question), { type: 'token', text }), { type: 'done' }),
    ...extra,
  })

  it('sends only completed, real answers', () => {
    const messages: ChatMessage[] = [
      { id: 'u1', role: 'user', text: 'What is asthma?' },
      done('a1', 'What is asthma?', 'A lung condition.'),
      { id: 'u2', role: 'user', text: 'I can’t breathe' },
      done('a2', 'I can’t breathe', 'Call emergency services.', { kind: 'emergency' }),
      { id: 'u3', role: 'user', text: 'Demo question' },
      done('a3', 'Demo question', 'Demo answer.', { demo: true }),
      { id: 'u4', role: 'user', text: 'Broken' },
      { ...newAssistant('a4', 'Broken'), status: 'error' },
    ]
    expect(historyFrom(messages)).toEqual([
      { role: 'user', content: 'What is asthma?' },
      { role: 'assistant', content: 'A lung condition.' },
    ])
  })
})
