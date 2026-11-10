import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { SLOW_START_MS } from './components/AssistantMessageView'
import { EMERGENCY_MESSAGE } from './content'
import { BLOCK_NOTICE } from './lib/chatState'

const frame = (event: string, data: object) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`
const encoder = new TextEncoder()

const SOURCE = (title: string, url: string) => ({
  title, url, snippet: `${title} snippet text.`, source_name: 'MedlinePlus',
  attribution: 'Courtesy of MedlinePlus from the National Library of Medicine',
})

/** A fetch mock whose response body the test feeds by hand, and which honours an abort signal. */
function controlledFetch() {
  const calls: { body: { message: string; history: { role: string; content: string }[] } }[] = []
  const pending: { push: (event: string, data: object) => void; close: () => void }[] = []
  const fetchMock = vi.fn((_url: string, init: RequestInit) => {
    calls.push({ body: JSON.parse(init.body as string) })
    let controller!: ReadableStreamDefaultController<Uint8Array>
    const body = new ReadableStream<Uint8Array>({ start: (c) => (controller = c) })
    init.signal?.addEventListener('abort', () => controller.error(new DOMException('aborted', 'AbortError')))
    pending.push({
      push: (event, data) => controller.enqueue(encoder.encode(frame(event, data))),
      close: () => controller.close(),
    })
    return Promise.resolve(new Response(body, { status: 200 }))
  })
  return { fetchMock, calls, pending }
}

const ask = (text: string) => {
  fireEvent.change(screen.getByLabelText('Your question'), { target: { value: text } })
  fireEvent.click(screen.getByRole('button', { name: 'Send question' }))
}

const completeAnswer = (stream: { push: (e: string, d: object) => void; close: () => void }, suggestions = ['What triggers asthma?', 'How is asthma diagnosed?', 'Can asthma be prevented?']) => {
  stream.push('token', { text: 'Asthma is a lung condition. ' })
  stream.push('token', { text: 'It causes wheezing.' })
  stream.push('sources', { sources: [SOURCE('Asthma', 'https://medlineplus.gov/asthma.html'), SOURCE('Asthma in Children', 'https://medlineplus.gov/asthmainchildren.html')] })
  stream.push('suggestions', { suggested_questions: suggestions })
  stream.push('safety', { status: 'ok', disclaimer: 'Approved disclaimer text.' })
  stream.push('done', {})
  stream.close()
}

beforeEach(() => document.documentElement.setAttribute('data-theme', 'light'))
afterEach(() => vi.unstubAllGlobals())

describe('page structure', () => {
  it('shows the nav, the hero and the empty chat state from the brief', () => {
    render(<App />)
    expect(screen.getByRole('heading', { level: 1, name: 'Health answers, with sources.' })).toBeTruthy()
    expect(screen.getByText('Plain-language answers from MedlinePlus, WHO and the CDC, with every source shown.')).toBeTruthy()
    expect(screen.getByText('Informational only. Not medical advice.')).toBeTruthy()
    const nav = screen.getByRole('navigation', { name: 'Main' })
    for (const name of ['How it works', 'Sources', 'Sign in']) expect(within(nav).getAllByText(name).length).toBeGreaterThan(0)
    expect(within(nav).getByRole('button', { name: 'Ask a question' })).toBeTruthy()
    for (const chip of ['Asthma symptoms', 'Managing type 2 diabetes', 'Sleeping better']) expect(screen.getByRole('button', { name: chip })).toBeTruthy()
    expect(screen.getAllByText('Please don’t enter personal health details.').length).toBeGreaterThan(0)
  })

  it('has the how-it-works steps, the trust strip and the footer disclaimer', () => {
    render(<App />)
    for (const text of ['Ask', 'We search trusted sources', 'You see the answer and where it came from']) expect(screen.getByRole('heading', { name: text })).toBeTruthy()
    for (const text of ['Sources shown on every answer', 'Safety checks on every answer', 'Nothing stored on our servers']) expect(screen.getByText(text)).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Safety and limitations' })).toBeTruthy()
    expect(screen.getByText(/not medical advice and does not replace a healthcare professional/i)).toBeTruthy()
  })

  it('has an accessible conversation log', () => {
    render(<App />)
    const log = screen.getByRole('log', { name: 'Conversation' })
    expect(log.getAttribute('aria-live')).toBe('polite')
  })

  it('does not show a human avatar; assistant messages are labelled as an AI assistant', async () => {
    const { fetchMock, pending } = controlledFetch()
    vi.stubGlobal('fetch', fetchMock)
    render(<App />)
    ask('What is asthma?')
    await screen.findByText('Searching trusted sources…')
    expect(screen.getByText('AI assistant')).toBeTruthy()
    act(() => completeAnswer(pending[0]))
  })
})

describe('composer', () => {
  it('counts characters and warns in amber from 450', () => {
    render(<App />)
    const box = screen.getByLabelText('Your question')
    fireEvent.change(box, { target: { value: 'a'.repeat(449) } })
    expect(screen.getByText('449/500').className).not.toContain('bg-caution-bg')
    fireEvent.change(box, { target: { value: 'a'.repeat(450) } })
    expect(screen.getByText('450/500').className).toContain('bg-caution-bg')
  })

  it('turns red and disables sending above 500', () => {
    render(<App />)
    fireEvent.change(screen.getByLabelText('Your question'), { target: { value: 'a'.repeat(501) } })
    expect(screen.getByText(/501\/500/).className).toContain('bg-emergency')
    expect((screen.getByRole('button', { name: 'Send question' }) as HTMLButtonElement).disabled).toBe(true)
  })

  it('disables sending an empty or blank question', () => {
    render(<App />)
    expect((screen.getByRole('button', { name: 'Send question' }) as HTMLButtonElement).disabled).toBe(true)
    fireEvent.change(screen.getByLabelText('Your question'), { target: { value: '   ' } })
    expect((screen.getByRole('button', { name: 'Send question' }) as HTMLButtonElement).disabled).toBe(true)
  })

  it('sends with Enter and keeps Shift+Enter for new lines', () => {
    const { fetchMock } = controlledFetch()
    vi.stubGlobal('fetch', fetchMock)
    render(<App />)
    const box = screen.getByLabelText('Your question')
    fireEvent.change(box, { target: { value: 'What is asthma?' } })
    fireEvent.keyDown(box, { key: 'Enter', shiftKey: true })
    expect(fetchMock).not.toHaveBeenCalled()
    fireEvent.keyDown(box, { key: 'Enter' })
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })
})

describe('live conversation', () => {
  it('shows searching, then the answer, source cards, disclaimer and Perplexity-style follow-up rows', async () => {
    const { fetchMock, calls, pending } = controlledFetch()
    vi.stubGlobal('fetch', fetchMock)
    render(<App />)
    ask('What are the symptoms of asthma?')

    expect(calls[0].body).toEqual({ message: 'What are the symptoms of asthma?', history: [] })
    await screen.findByText('Searching trusted sources…')
    expect(screen.getByRole('button', { name: 'Stop answering' })).toBeTruthy() // send becomes Stop

    act(() => {
      pending[0].push('token', { text: 'Asthma is a lung condition. ' })
    })
    await screen.findByText(/Asthma is a lung condition\./)
    expect(screen.queryByText('Searching trusted sources…')).toBeNull()
    expect(document.querySelectorAll('.skeleton').length).toBeGreaterThan(0) // skeleton cards first

    act(() => completeAnswer(pending[0]))
    const sources = await screen.findByRole('region', { name: 'Sources' })
    expect(within(sources).getByRole('heading', { name: 'Asthma' })).toBeTruthy()
    expect(within(sources).getAllByText('MedlinePlus · National Library of Medicine')).toHaveLength(2)
    expect(within(sources).getAllByRole('link', { name: /Open source/ })).toHaveLength(2)
    expect(document.querySelectorAll('.skeleton')).toHaveLength(0)
    expect(screen.getByText('Approved disclaimer text.')).toBeTruthy()

    const related = screen.getByRole('region', { name: 'Related questions' })
    const rows = within(related).getAllByRole('listitem')
    expect(rows).toHaveLength(3)
    for (const row of rows) {
      expect(row.querySelector('svg')).not.toBeNull() // the reply arrow
      expect(row.querySelector('button')?.className).not.toContain('rounded-full') // rows, not chips
    }
    expect(screen.getByRole('button', { name: 'Send question' })).toBeTruthy() // Stop became Send again
  })

  it('asks a follow-up question when its row is chosen, sending the earlier exchange as history', async () => {
    const { fetchMock, calls, pending } = controlledFetch()
    vi.stubGlobal('fetch', fetchMock)
    render(<App />)
    ask('What is asthma?')
    await screen.findByText('Searching trusted sources…')
    act(() => completeAnswer(pending[0]))
    fireEvent.click(await screen.findByRole('button', { name: 'How is asthma diagnosed?' }))
    await waitFor(() => expect(calls).toHaveLength(2))
    expect(calls[1].body.message).toBe('How is asthma diagnosed?')
    expect(calls[1].body.history).toEqual([
      { role: 'user', content: 'What is asthma?' },
      { role: 'assistant', content: 'Asthma is a lung condition. It causes wheezing.' },
    ])
    act(() => completeAnswer(pending[1], ['Only the newest answer shows follow-ups?']))
    await screen.findByRole('button', { name: 'Only the newest answer shows follow-ups?' })
    expect(screen.getAllByRole('region', { name: 'Related questions' })).toHaveLength(1)
  })

  it('stops an answer and keeps what arrived', async () => {
    const { fetchMock, pending } = controlledFetch()
    vi.stubGlobal('fetch', fetchMock)
    render(<App />)
    ask('What is asthma?')
    await screen.findByText('Searching trusted sources…')
    act(() => pending[0].push('token', { text: 'Asthma is a lung condition. ' }))
    await screen.findByText(/Asthma is a lung condition/)
    fireEvent.click(screen.getByRole('button', { name: 'Stop answering' }))
    await screen.findByText('Stopped')
    expect(screen.getByText(/Asthma is a lung condition/)).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Send question' })).toBeTruthy()
  })

  it('shows an error notice for a failed request and retries with Try again', async () => {
    const failing = vi.fn().mockResolvedValue(new Response(JSON.stringify({ error: { code: 'upstream_error', message: 'x' } }), { status: 502 }))
    vi.stubGlobal('fetch', failing)
    render(<App />)
    ask('What is asthma?')
    expect((await screen.findAllByRole('alert'))[0].textContent).toContain('Something went wrong')
    const { fetchMock, pending } = controlledFetch()
    vi.stubGlobal('fetch', fetchMock)
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    await screen.findByText('Searching trusted sources…')
    act(() => completeAnswer(pending[0]))
    await screen.findByText(/It causes wheezing\./)
    expect(screen.queryByRole('button', { name: 'Try again' })).toBeNull()
  })

  it('shows plain-language text for each error, never technical details', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ error: { code: 'unauthorized', message: 'Missing authentication context.' } }), { status: 401 })))
    render(<App />)
    ask('What is asthma?')
    const alert = (await screen.findAllByRole('alert'))[0]
    expect(alert.textContent).toContain('Please sign in')
    expect(alert.textContent).not.toContain('Missing authentication context')
  })

  it('keeps the partial answer when the stream fails part-way', async () => {
    const { fetchMock, pending } = controlledFetch()
    vi.stubGlobal('fetch', fetchMock)
    render(<App />)
    ask('What is asthma?')
    await screen.findByText('Searching trusted sources…')
    act(() => {
      pending[0].push('token', { text: 'Asthma is a lung condition. ' })
      pending[0].push('error', { code: 'upstream_error', message: 'The AI service is unavailable.' })
      pending[0].close()
    })
    await screen.findByRole('button', { name: 'Try again' })
    expect(screen.getByText(/Asthma is a lung condition/)).toBeTruthy()
  })

  it('shows the emergency panel, with no sources, for an emergency answer', async () => {
    const { fetchMock, pending } = controlledFetch()
    vi.stubGlobal('fetch', fetchMock)
    render(<App />)
    ask('I can’t breathe')
    await screen.findByText('Searching trusted sources…')
    act(() => {
      pending[0].push('token', { text: EMERGENCY_MESSAGE })
      pending[0].push('safety', { status: 'emergency', disclaimer: 'D' })
      pending[0].push('done', {})
      pending[0].close()
    })
    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toContain('call your local emergency number')
    expect(screen.queryByRole('region', { name: 'Sources' })).toBeNull()
  })
})

describe('friendly replies and corrections', () => {
  it('says which spelling was used, and keeps what the person typed', async () => {
    const { fetchMock, pending } = controlledFetch()
    vi.stubGlobal('fetch', fetchMock)
    render(<App />)
    ask('Tell me about Alzeihmers')
    await screen.findByText('Searching trusted sources…')
    act(() => {
      pending[0].push('corrected', { original: 'Tell me about Alzeihmers', corrected: 'Tell me about Alzheimers', changes: [{ from: 'Alzeihmers', to: 'Alzheimers' }] })
      completeAnswer(pending[0])
    })
    const notice = await screen.findByText(/Showing results for/)
    expect(notice.textContent).toBe("Showing results for Alzheimers. You typed 'Alzeihmers'.")
  })

  it('words the notice like "Showing results for Diabetes. You typed \'diabtes\'." and leaves the chat message as typed', async () => {
    const { fetchMock, pending } = controlledFetch()
    vi.stubGlobal('fetch', fetchMock)
    render(<App />)
    ask('what is diabtes')
    await screen.findByText('Searching trusted sources…')
    act(() => {
      pending[0].push('corrected', { original: 'what is diabtes', corrected: 'what is diabetes', changes: [{ from: 'diabtes', to: 'diabetes' }] })
      completeAnswer(pending[0])
    })
    const notice = await screen.findByText(/Showing results for/)
    expect(notice.textContent).toBe("Showing results for Diabetes. You typed 'diabtes'.")
    // the person's own message in the chat log is never rewritten
    expect(screen.getByText('what is diabtes', { selector: 'p.whitespace-pre-wrap' })).toBeTruthy()
  })

  it('shows a greeting reply as a normal short answer: no sources, no error', async () => {
    const { fetchMock, pending } = controlledFetch()
    vi.stubGlobal('fetch', fetchMock)
    render(<App />)
    ask('Hi')
    await screen.findByText('Searching trusted sources…')
    act(() => {
      pending[0].push('token', { text: "Hi! I'm VitalNest, an AI assistant that shares general health information." })
      pending[0].push('safety', { status: 'ok', disclaimer: 'Approved disclaimer text.' })
      pending[0].push('done', {})
      pending[0].close()
    })
    // Each sentence is its own span (for the fade-in), so match the second sentence.
    await screen.findByText(/an AI assistant that shares general health information/)
    expect(screen.queryByRole('region', { name: 'Sources' })).toBeNull()
    expect(screen.queryByRole('alert')).toBeNull()
    expect(screen.queryByText(/Showing results for/)).toBeNull()
  })
})

describe('demo states', () => {
  const choose = (label: string) => fireEvent.change(screen.getByLabelText('Demo states'), { target: { value: label } })

  it('normal answer: labelled demo content, sources and three follow-up rows', () => {
    render(<App />)
    choose('normal')
    expect(screen.getByText('Demo content, not real medical advice')).toBeTruthy()
    expect(within(screen.getByRole('region', { name: 'Sources' })).getAllByRole('listitem')).toHaveLength(2)
    expect(within(screen.getByRole('region', { name: 'Related questions' })).getAllByRole('listitem')).toHaveLength(3)
  })

  it('spelling corrected: tells the person which spelling was used', () => {
    render(<App />)
    choose('corrected')
    expect(screen.getByText(/Showing results for/).textContent).toBe("Showing results for Alzheimer's. You typed 'Alzeihmers'.")
    expect(screen.getByRole('region', { name: 'Sources' })).toBeTruthy()
  })

  it('emergency: a full-width red alert that tells the person to call their local emergency number, and no sources', () => {
    render(<App />)
    choose('emergency')
    const alert = screen.getByRole('alert')
    expect(alert.className).toContain('bg-emergency')
    expect(alert.textContent).toContain('local emergency number')
    expect(screen.queryByRole('region', { name: 'Sources' })).toBeNull()
  })

  it('refused mid-answer: the approved sentences, then the amber notice', () => {
    render(<App />)
    choose('refused')
    expect(screen.getByText(/Type 2 diabetes is usually managed/)).toBeTruthy()
    const notice = screen.getByRole('note')
    expect(notice.textContent).toContain(BLOCK_NOTICE)
    expect(notice.className).toContain('bg-caution-bg')
    expect(screen.queryByRole('region', { name: 'Sources' })).toBeNull()
  })

  it('not enough information: a dashed neutral card linking to medlineplus.gov', () => {
    render(<App />)
    choose('no_context')
    const link = screen.getByRole('link', { name: /Browse MedlinePlus/ })
    expect(link.getAttribute('href')).toBe('https://medlineplus.gov/')
    expect(link.getAttribute('rel')).toContain('noopener')
    expect(link.parentElement?.className).toContain('border-dashed')
  })

  it('stream error: keeps the partial answer and offers Try again', () => {
    render(<App />)
    choose('error')
    expect(screen.getByText(/Most adults need about seven/)).toBeTruthy()
    expect(screen.getByRole('alert').textContent).toContain('Something went wrong')
    expect(screen.getByRole('button', { name: 'Try again' })).toBeTruthy()
  })

  it('going back to live clears the sample conversation', () => {
    render(<App />)
    choose('normal')
    choose('live')
    expect(screen.getByText('What would you like to know?')).toBeTruthy()
  })
})

describe('release build', () => {
  it('hides the demo-states switch when VITE_HIDE_DEMO is true', () => {
    vi.stubEnv('VITE_HIDE_DEMO', 'true')
    render(<App />)
    expect(screen.queryByLabelText('Demo states')).toBeNull()
    vi.unstubAllEnvs()
  })
})

describe('theme', () => {
  it('switches between light and dark and remembers the choice', () => {
    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Dark' }))
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark')
    expect(localStorage.getItem('vitalnest-theme')).toBe('dark')
    expect(screen.getByRole('button', { name: 'Dark' }).getAttribute('aria-pressed')).toBe('true')
    fireEvent.click(screen.getByRole('button', { name: 'Light' }))
    expect(document.documentElement.getAttribute('data-theme')).toBe('light')
  })
})

describe('accessibility basics', () => {
  it('uses at least 44px tall controls for the main buttons and links', () => {
    render(<App />)
    for (const name of ['Send question']) expect(screen.getByRole('button', { name }).className).toContain('h-11')
    for (const button of screen.getAllByRole('button', { name: 'Ask a question' })) expect(button.className).toContain('min-h-11')
  })

  it('opens source links safely in a new tab', () => {
    render(<App />)
    fireEvent.change(screen.getByLabelText('Demo states'), { target: { value: 'normal' } })
    for (const link of screen.getAllByRole('link', { name: /Open source/ })) {
      expect(link.getAttribute('target')).toBe('_blank')
      expect(link.getAttribute('rel')).toBe('noopener noreferrer')
      expect(link.getAttribute('href')).toMatch(/^https:\/\//)
    }
  })
})

describe('signed-out visitors', () => {
  beforeEach(() => {
    vi.stubEnv('VITE_COGNITO_DOMAIN', 'https://example.auth.ap-south-1.amazoncognito.com')
    vi.stubEnv('VITE_COGNITO_CLIENT_ID', 'client-1')
    sessionStorage.clear()
  })

  it('asks them to sign in instead of sending, and keeps the typed question', () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    render(<App />)
    const box = screen.getByLabelText('Your question') as HTMLTextAreaElement
    fireEvent.change(box, { target: { value: 'What is asthma?' } })
    fireEvent.keyDown(box, { key: 'Enter' })
    expect(fetchMock).not.toHaveBeenCalled()
    expect(screen.getByRole('alert').textContent).toContain('Please sign in to ask questions.')
    expect(box.value).toBe('What is asthma?')
  })

  it('also asks when an example question is clicked', () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    render(<App />)
    fireEvent.click(within(screen.getByLabelText('Example questions')).getAllByRole('button')[0])
    expect(fetchMock).not.toHaveBeenCalled()
    expect(screen.getByRole('alert').textContent).toContain('Please sign in to ask questions.')
  })
})

describe('safety and limitations section', () => {
  it('is on the page, linked from the footer, and covers the key promises', () => {
    render(<App />)
    const section = document.getElementById('safety') as HTMLElement
    expect(section).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Safety and limitations' }).getAttribute('href')).toBe('#safety')
    expect(within(section).getByRole('heading', { name: 'Safety and limitations' })).toBeTruthy()
    for (const text of ['Emergencies', 'Diagnosis', 'Medicines', 'How answers are checked', 'Limitations', 'Your privacy']) {
      expect(within(section).getByText(text)).toBeTruthy()
    }
    expect(section.textContent).toContain('not a doctor')
    expect(section.textContent).toContain('112 in India')
  })
})

describe('slow first answer', () => {
  it('says the service is waking up only after several seconds without an answer, and hides it once the answer starts', async () => {
    const { fetchMock, pending } = controlledFetch()
    vi.stubGlobal('fetch', fetchMock)
    render(<App />)
    ask('What is asthma?')
    await screen.findByText('Searching trusted sources…')
    expect(screen.queryByText(/waking up/)).toBeNull()

    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, SLOW_START_MS + 200))
    })
    expect(screen.getByText(/waking up after a quiet period/)).toBeTruthy()

    act(() => {
      pending[0].push('token', { text: 'Asthma is a lung condition. ' })
    })
    await screen.findByText(/Asthma is a lung condition\./)
    expect(screen.queryByText(/waking up/)).toBeNull()
  }, 15000)
})
