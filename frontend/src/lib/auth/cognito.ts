/** Sign-in with the Cognito Hosted UI: authorization-code flow with PKCE (no client secret in the browser).
 *
 * Tokens live in sessionStorage (this tab only, gone when the tab closes). The API gets the access token.
 * Nothing here is a secret: the domain and client id are public values.
 */

const SESSION_KEY = 'vitalnest.session'
const LOGIN_KEY = 'vitalnest.login'
const REFRESH_MARGIN_MS = 60_000

export interface Session {
  accessToken: string
  idToken?: string
  refreshToken?: string
  /** When the access token stops working, in ms since 1970. */
  expiresAt: number
}

export interface AuthConfig {
  domain: string
  clientId: string
}

export function authConfig(): AuthConfig | null {
  const domain = import.meta.env.VITE_COGNITO_DOMAIN
  const clientId = import.meta.env.VITE_COGNITO_CLIENT_ID
  if (!domain || !clientId) return null
  return { domain: domain.replace(/\/+$/, ''), clientId }
}

export const redirectUri = () => `${window.location.origin}/`

function read(key: string): string | null {
  try {
    return sessionStorage.getItem(key)
  } catch {
    return null
  }
}
function write(key: string, value: string | null) {
  try {
    if (value === null) sessionStorage.removeItem(key)
    else sessionStorage.setItem(key, value)
  } catch {
    /* storage blocked: the person just has to sign in again */
  }
}

const listeners = new Set<() => void>()
export function onAuthChange(listener: () => void): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}
const notify = () => listeners.forEach((l) => l())

export function getSession(): Session | null {
  const raw = read(SESSION_KEY)
  if (!raw) return null
  try {
    const s = JSON.parse(raw) as Session
    return typeof s.accessToken === 'string' && typeof s.expiresAt === 'number' ? s : null
  } catch {
    return null
  }
}

function saveSession(session: Session | null) {
  write(SESSION_KEY, session ? JSON.stringify(session) : null)
  notify()
}

/** The signed-in person's email, read from the ID token for display only (never trusted by the server). */
export function sessionEmail(session: Session | null): string | null {
  if (!session?.idToken) return null
  try {
    const payload = session.idToken.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')
    const claims = JSON.parse(atob(payload.padEnd(Math.ceil(payload.length / 4) * 4, '=')))
    return typeof claims.email === 'string' ? claims.email : null
  } catch {
    return null
  }
}

function base64Url(bytes: Uint8Array): string {
  let text = ''
  bytes.forEach((b) => (text += String.fromCharCode(b)))
  return btoa(text).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

export function randomString(byteCount = 32): string {
  return base64Url(crypto.getRandomValues(new Uint8Array(byteCount)))
}

export async function challengeFor(verifier: string): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier))
  return base64Url(new Uint8Array(digest))
}

export async function loginUrl(config: AuthConfig, verifier: string, state: string): Promise<string> {
  const query = new URLSearchParams({
    response_type: 'code',
    client_id: config.clientId,
    redirect_uri: redirectUri(),
    scope: 'openid email',
    state,
    code_challenge_method: 'S256',
    code_challenge: await challengeFor(verifier),
  })
  return `${config.domain}/oauth2/authorize?${query}`
}

/** Send the person to the Cognito sign-in page. */
export async function signIn(): Promise<void> {
  const config = authConfig()
  if (!config) return
  const verifier = randomString(48)
  const state = randomString(16)
  write(LOGIN_KEY, JSON.stringify({ verifier, state }))
  window.location.assign(await loginUrl(config, verifier, state))
}

function toSession(body: Record<string, unknown>, previous?: Session): Session {
  if (typeof body.access_token !== 'string' || typeof body.expires_in !== 'number') throw new Error('bad token response')
  return {
    accessToken: body.access_token,
    idToken: typeof body.id_token === 'string' ? body.id_token : previous?.idToken,
    refreshToken: typeof body.refresh_token === 'string' ? body.refresh_token : previous?.refreshToken,
    expiresAt: Date.now() + body.expires_in * 1000,
  }
}

async function tokenRequest(config: AuthConfig, form: Record<string, string>): Promise<Record<string, unknown>> {
  const response = await fetch(`${config.domain}/oauth2/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({ client_id: config.clientId, ...form }),
  })
  if (!response.ok) throw new Error(`token request failed (${response.status})`)
  return response.json()
}

export type LoginOutcome = 'none' | 'signed-in' | 'failed'

let callbackRun: Promise<LoginOutcome> | null = null

/** If the page was opened by the redirect back from Cognito (?code=...), finish signing in. Runs once per load. */
export function completeLoginFromUrl(): Promise<LoginOutcome> {
  callbackRun ??= finishLogin()
  return callbackRun
}
export function resetCallbackForTests() {
  callbackRun = null
}

async function finishLogin(): Promise<LoginOutcome> {
  const params = new URLSearchParams(window.location.search)
  const code = params.get('code')
  const state = params.get('state')
  if (!code && !params.get('error')) return 'none'
  window.history.replaceState({}, '', window.location.pathname) // the code is single-use: take it out of the address bar
  const saved = read(LOGIN_KEY)
  write(LOGIN_KEY, null)
  const config = authConfig()
  if (!code || !config || !saved) return 'failed'
  try {
    const { verifier, state: expected } = JSON.parse(saved) as { verifier: string; state: string }
    if (!state || state !== expected) return 'failed'
    const body = await tokenRequest(config, {
      grant_type: 'authorization_code',
      code,
      redirect_uri: redirectUri(),
      code_verifier: verifier,
    })
    saveSession(toSession(body))
    return 'signed-in'
  } catch {
    return 'failed'
  }
}

/** A valid access token, refreshed first if it is about to expire; null when signed out. */
export async function getAccessToken(): Promise<string | null> {
  const session = getSession()
  if (!session) return null
  if (session.expiresAt - Date.now() > REFRESH_MARGIN_MS) return session.accessToken
  const config = authConfig()
  if (!config || !session.refreshToken) {
    saveSession(null)
    return null
  }
  try {
    const body = await tokenRequest(config, { grant_type: 'refresh_token', refresh_token: session.refreshToken })
    const refreshed = toSession(body, session)
    saveSession(refreshed)
    return refreshed.accessToken
  } catch {
    saveSession(null)
    return null
  }
}

/** Forget the session here and end it at Cognito too. */
export function signOut(): void {
  saveSession(null)
  const config = authConfig()
  if (config) {
    const query = new URLSearchParams({ client_id: config.clientId, logout_uri: redirectUri() })
    window.location.assign(`${config.domain}/logout?${query}`)
  }
}
