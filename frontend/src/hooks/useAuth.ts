import { useEffect, useState } from 'react'
import { authConfig, completeLoginFromUrl, getSession, onAuthChange, sessionEmail, signIn, signOut } from '../lib/auth/cognito'

export interface AuthState {
  /** False when the Cognito settings are missing (local development without sign-in). */
  enabled: boolean
  signedIn: boolean
  email: string | null
  /** True after a redirect back from Cognito that did not work. */
  failed: boolean
  signIn: () => void
  signOut: () => void
}

export function useAuth(): AuthState {
  const [, setTick] = useState(0)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    const off = onAuthChange(() => setTick((n) => n + 1))
    void completeLoginFromUrl().then((outcome) => setFailed(outcome === 'failed'))
    return off
  }, [])

  const session = getSession()
  return {
    enabled: authConfig() !== null,
    signedIn: session !== null,
    email: sessionEmail(session),
    failed,
    signIn: () => void signIn(),
    signOut,
  }
}
