import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { getAuthHeaders } from './api/sse'
import {
  authConfig,
  challengeFor,
  completeLoginFromUrl,
  getAccessToken,
  getSession,
  loginUrl,
  randomString,
  resetCallbackForTests,
  sessionEmail,
} from './auth/cognito'

const DOMAIN = 'https://example.auth.ap-south-1.amazoncognito.com'

function tokenResponse(extra: Record<string, unknown> = {}) {
  return new Response(JSON.stringify({ access_token: 'access-1', id_token: 'a.b.c', refresh_token: 'refresh-1', expires_in: 3600, ...extra }), { status: 200 })
}

function arriveWith(search: string) {
  window.history.replaceState({}, '', `/${search}`)
}

beforeEach(() => {
  vi.stubEnv('VITE_COGNITO_DOMAIN', `${DOMAIN}/`)
  vi.stubEnv('VITE_COGNITO_CLIENT_ID', 'client-1')
  sessionStorage.clear()
  resetCallbackForTests()
  arriveWith('')
})

afterEach(() => {
  vi.unstubAllEnvs()
  vi.unstubAllGlobals()
})

describe('configuration', () => {
  it('is off when the settings are missing', () => {
    vi.stubEnv('VITE_COGNITO_DOMAIN', '')
    expect(authConfig()).toBeNull()
  })
  it('drops a trailing slash from the domain', () => {
    expect(authConfig()).toEqual({ domain: DOMAIN, clientId: 'client-1' })
  })
})

describe('PKCE', () => {
  it('matches the RFC 7636 example challenge', async () => {
    expect(await challengeFor('dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk')).toBe('E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM')
  })
  it('makes unrelated url-safe random strings', () => {
    const a = randomString(32)
    expect(a).toMatch(/^[A-Za-z0-9_-]{43}$/)
    expect(randomString(32)).not.toBe(a)
  })
  it('builds the authorize address with the code flow and S256', async () => {
    const url = new URL(await loginUrl({ domain: DOMAIN, clientId: 'client-1' }, 'verifier', 'state-1'))
    expect(url.origin + url.pathname).toBe(`${DOMAIN}/oauth2/authorize`)
    expect(Object.fromEntries(url.searchParams)).toMatchObject({
      response_type: 'code',
      client_id: 'client-1',
      state: 'state-1',
      code_challenge_method: 'S256',
      scope: 'openid email',
      redirect_uri: `${window.location.origin}/`,
    })
    expect(url.searchParams.get('code_challenge')).toBe(await challengeFor('verifier'))
  })
})

describe('coming back from Cognito', () => {
  it('does nothing on a normal page load', async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    expect(await completeLoginFromUrl()).toBe('none')
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('swaps the code for tokens, stores the session and cleans the address bar', async () => {
    sessionStorage.setItem('vitalnest.login', JSON.stringify({ verifier: 'v-1', state: 's-1' }))
    const fetchMock = vi.fn().mockResolvedValue(tokenResponse())
    vi.stubGlobal('fetch', fetchMock)
    arriveWith('?code=abc&state=s-1')
    expect(await completeLoginFromUrl()).toBe('signed-in')

    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe(`${DOMAIN}/oauth2/token`)
    const form = new URLSearchParams(init.body as URLSearchParams)
    expect(Object.fromEntries(form)).toMatchObject({ grant_type: 'authorization_code', code: 'abc', code_verifier: 'v-1', client_id: 'client-1' })
    expect(getSession()?.accessToken).toBe('access-1')
    expect(window.location.search).toBe('')
    expect(sessionStorage.getItem('vitalnest.login')).toBeNull()
  })

  it('rejects a wrong state without calling the token endpoint', async () => {
    sessionStorage.setItem('vitalnest.login', JSON.stringify({ verifier: 'v-1', state: 's-1' }))
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    arriveWith('?code=abc&state=forged')
    expect(await completeLoginFromUrl()).toBe('failed')
    expect(fetchMock).not.toHaveBeenCalled()
    expect(getSession()).toBeNull()
  })

  it('fails when nothing was started in this tab', async () => {
    vi.stubGlobal('fetch', vi.fn())
    arriveWith('?code=abc&state=s-1')
    expect(await completeLoginFromUrl()).toBe('failed')
  })

  it('fails cleanly when Cognito reports an error or the token call is refused', async () => {
    arriveWith('?error=access_denied')
    expect(await completeLoginFromUrl()).toBe('failed')

    resetCallbackForTests()
    sessionStorage.setItem('vitalnest.login', JSON.stringify({ verifier: 'v', state: 's' }))
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{}', { status: 400 })))
    arriveWith('?code=abc&state=s')
    expect(await completeLoginFromUrl()).toBe('failed')
    expect(getSession()).toBeNull()
  })
})

describe('tokens', () => {
  const store = (expiresAt: number, refreshToken: string | undefined = 'refresh-1') =>
    sessionStorage.setItem('vitalnest.session', JSON.stringify({ accessToken: 'old', refreshToken, expiresAt }))

  it('is null when signed out and adds no Authorization header', async () => {
    expect(await getAccessToken()).toBeNull()
    expect(await getAuthHeaders()).toEqual({})
  })

  it('uses the stored token while it is fresh, without any request', async () => {
    store(Date.now() + 10 * 60_000)
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    expect(await getAuthHeaders()).toEqual({ Authorization: 'Bearer old' })
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('refreshes a token that is about to expire and keeps the refresh token', async () => {
    store(Date.now() + 10_000)
    const fetchMock = vi.fn().mockResolvedValue(tokenResponse({ access_token: 'new', refresh_token: undefined }))
    vi.stubGlobal('fetch', fetchMock)
    expect(await getAccessToken()).toBe('new')
    expect(new URLSearchParams(fetchMock.mock.calls[0][1].body as URLSearchParams).get('grant_type')).toBe('refresh_token')
    expect(getSession()?.refreshToken).toBe('refresh-1')
  })

  it('signs the person out when the refresh fails or is impossible', async () => {
    store(Date.now() - 1000)
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{}', { status: 400 })))
    expect(await getAccessToken()).toBeNull()
    expect(getSession()).toBeNull()

    store(Date.now() - 1000, undefined)
    expect(await getAccessToken()).toBeNull()
    expect(getSession()).toBeNull()
  })

  it('ignores a damaged stored session', () => {
    sessionStorage.setItem('vitalnest.session', 'not json')
    expect(getSession()).toBeNull()
  })
})

describe('sessionEmail', () => {
  it('reads the email from the id token for display', () => {
    const payload = btoa(JSON.stringify({ email: 'a@example.com' })).replace(/=+$/, '')
    expect(sessionEmail({ accessToken: 'x', idToken: `h.${payload}.s`, expiresAt: 0 })).toBe('a@example.com')
  })
  it('returns null for anything unreadable', () => {
    expect(sessionEmail(null)).toBeNull()
    expect(sessionEmail({ accessToken: 'x', idToken: 'junk', expiresAt: 0 })).toBeNull()
  })
})
