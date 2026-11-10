import { cleanup } from '@testing-library/react'
import { afterEach, beforeEach, vi } from 'vitest'

// Tests never depend on a developer's .env.local: sign-in is off unless a test turns it on.
beforeEach(() => {
  vi.stubEnv('VITE_COGNITO_DOMAIN', '')
  vi.stubEnv('VITE_COGNITO_CLIENT_ID', '')
})
afterEach(() => cleanup())

if (!window.matchMedia) {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }))
}
window.HTMLElement.prototype.scrollIntoView = vi.fn()
window.scrollTo = vi.fn() as unknown as typeof window.scrollTo
