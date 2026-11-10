import { afterEach, describe, expect, it, vi } from 'vitest'
import { friendlyError, parseSseBlock, readEvents, streamChat } from './api/sse'
import { ApiError, type ChatEvent } from './api/types'

const sse = (event: string, data: object) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`

function streamOf(chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder()
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk))
      controller.close()
    },
  })
}

async function collect(iterable: AsyncGenerator<ChatEvent>): Promise<ChatEvent[]> {
  const events: ChatEvent[] = []
  for await (const event of iterable) events.push(event)
  return events
}

describe('parseSseBlock', () => {
  it('parses every event type in the API contract', () => {
    expect(parseSseBlock('event: token\ndata: {"text":"Hi. "}')).toEqual({ type: 'token', text: 'Hi. ' })
    expect(parseSseBlock('event: sources\ndata: {"sources":[{"title":"Asthma"}]}')).toEqual({ type: 'sources', sources: [{ title: 'Asthma' }] })
    expect(parseSseBlock('event: suggestions\ndata: {"suggested_questions":["a?","b?"]}')).toEqual({ type: 'suggestions', questions: ['a?', 'b?'] })
    expect(parseSseBlock('event: safety\ndata: {"status":"ok","disclaimer":"D"}')).toEqual({ type: 'safety', status: 'ok', disclaimer: 'D' })
    expect(
      parseSseBlock('event: corrected\ndata: {"original":"Alzeihmers","corrected":"Alzheimers","changes":[{"from":"Alzeihmers","to":"Alzheimers"},{"from":5}]}'),
    ).toEqual({ type: 'corrected', original: 'Alzeihmers', corrected: 'Alzheimers', changes: [{ from: 'Alzeihmers', to: 'Alzheimers' }] })
    expect(parseSseBlock('event: corrected\ndata: {"original":"a","corrected":"b"}')).toEqual({ type: 'corrected', original: 'a', corrected: 'b', changes: [] })
    expect(parseSseBlock('event: done\ndata: {}')).toEqual({ type: 'done' })
    expect(parseSseBlock('event: error\ndata: {"code":"timeout","message":"slow"}')).toEqual({ type: 'error', code: 'timeout', message: 'slow' })
  })

  it('ignores unknown events, bad JSON and blocks without an event name', () => {
    expect(parseSseBlock('event: mystery\ndata: {}')).toBeNull()
    expect(parseSseBlock('event: token\ndata: {broken')).toBeNull()
    expect(parseSseBlock('data: {"text":"x"}')).toBeNull()
    expect(parseSseBlock('')).toBeNull()
  })

  it('drops non-string suggestions', () => {
    expect(parseSseBlock('event: suggestions\ndata: {"suggested_questions":["ok?",5,null]}')).toEqual({ type: 'suggestions', questions: ['ok?'] })
  })
})

describe('readEvents', () => {
  it('reads several events from one chunk', async () => {
    const body = streamOf([sse('token', { text: 'A. ' }) + sse('token', { text: 'B.' }) + sse('done', {})])
    expect((await collect(readEvents(body))).map((e) => e.type)).toEqual(['token', 'token', 'done'])
  })

  it('handles events split across chunks at any position', async () => {
    const whole = sse('token', { text: 'Asthma is common. ' }) + sse('done', {})
    for (let cut = 1; cut < whole.length; cut += 7) {
      const events = await collect(readEvents(streamOf([whole.slice(0, cut), whole.slice(cut)])))
      expect(events).toEqual([{ type: 'token', text: 'Asthma is common. ' }, { type: 'done' }])
    }
  })

  it('handles Windows line endings and a final event without a trailing blank line', async () => {
    const body = streamOf(['event: token\r\ndata: {"text":"x"}\r\n\r\nevent: done\r\ndata: {}'])
    expect((await collect(readEvents(body))).map((e) => e.type)).toEqual(['token', 'done'])
  })

  it('keeps multi-byte characters intact when a chunk splits them', async () => {
    const bytes = new TextEncoder().encode(sse('token', { text: 'café ☕' }))
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(bytes.slice(0, 30))
        controller.enqueue(bytes.slice(30))
        controller.close()
      },
    })
    expect(await collect(readEvents(body))).toEqual([{ type: 'token', text: 'café ☕' }])
  })
})

describe('streamChat', () => {
  afterEach(() => vi.unstubAllGlobals())
  const request = { message: 'What is asthma?', history: [] }

  it('posts the request as JSON and yields the events', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(streamOf([sse('token', { text: 'Hi' }), sse('done', {})]), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    const events = await collect(streamChat(request, { baseUrl: 'http://api.test' }))
    expect(events.map((e) => e.type)).toEqual(['token', 'done'])
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('http://api.test/v1/chat')
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body)).toEqual(request)
    expect(init.headers['Content-Type']).toBe('application/json')
  })

  it('turns an error response into an ApiError with the server code', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ error: { code: 'unauthorized', message: 'no' } }), { status: 401 })))
    await expect(collect(streamChat(request))).rejects.toMatchObject({ name: 'ApiError', code: 'unauthorized', status: 401 })
  })

  it('handles an error response that is not JSON', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('Bad gateway', { status: 502 })))
    await expect(collect(streamChat(request))).rejects.toMatchObject({ code: 'error', status: 502 })
  })

  it('reports a network failure as network_error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    await expect(collect(streamChat(request))).rejects.toMatchObject({ code: 'network_error' })
  })

  it('lets an abort through unchanged so the caller can tell it from a failure', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new DOMException('aborted', 'AbortError')))
    await expect(collect(streamChat(request))).rejects.toMatchObject({ name: 'AbortError' })
  })

  it('is an ApiError instance', () => {
    expect(new ApiError('x', 'y')).toBeInstanceOf(Error)
  })
})

describe('friendlyError', () => {
  it('gives plain-language text and never echoes technical details', () => {
    for (const code of ['unauthorized', 'payload_too_large', 'validation_error', 'rate_limited', 'timeout', 'service_unavailable', 'network_error', 'incomplete', 'whatever']) {
      const text = friendlyError(code)
      expect(text.length).toBeGreaterThan(20)
      expect(text).not.toMatch(/stack|exception|undefined|502|500/i)
    }
  })
})
