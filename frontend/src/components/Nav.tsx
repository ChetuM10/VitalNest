import { useEffect, useState } from 'react'
import { LogoMark, MenuIcon } from './icons'
import type { AuthState } from '../hooks/useAuth'
import { pillCoralNav } from './ui'

const links = [
  { href: '#how', label: 'How it works' },
  { href: '#sources', label: 'Sources' },
]

export function Nav({ onAsk, auth }: { onAsk: () => void; auth: AuthState }) {
  const [menu, setMenu] = useState(false)
  const [notice, setNotice] = useState(false)

  useEffect(() => {
    if (!notice) return
    const timer = window.setTimeout(() => setNotice(false), 4000)
    return () => window.clearTimeout(timer)
  }, [notice])

  const signIn = (event: { preventDefault: () => void }) => {
    event.preventDefault()
    if (auth.enabled) auth.signIn()
    else setNotice(true)
  }
  const signOut = (event: { preventDefault: () => void }) => {
    event.preventDefault()
    auth.signOut()
  }
  const accountLink = (className: string) =>
    auth.signedIn ? (
      <a href="#sign-out" onClick={signOut} className={className} title={auth.email ?? undefined}>Sign out</a>
    ) : (
      <a href="#sign-in" onClick={signIn} className={className}>Sign in</a>
    )

  const linkClass = 'inline-flex min-h-11 items-center px-3 text-[17px] text-ink underline-offset-4 hover:underline'

  return (
    <header className="sticky top-0 z-30 bg-powder">
      <nav aria-label="Main" className="mx-auto flex w-full max-w-[1100px] items-center justify-between gap-3 px-5 py-3 sm:px-8">
        <a href="#top" className="flex min-h-11 items-center gap-2.5 text-[19px] font-bold text-ink">
          <LogoMark />
          VitalNest
        </a>

        <div className="flex items-center gap-1">
          <div className="hidden items-center sm:flex">
            {links.map((l) => (
              <a key={l.href} href={l.href} className={linkClass}>{l.label}</a>
            ))}
            {accountLink(linkClass)}
          </div>
          <button type="button" onClick={onAsk} className={pillCoralNav}>Ask a question</button>
          <button
            type="button"
            className="grid h-11 w-11 shrink-0 place-items-center rounded-full border border-ink/30 text-ink sm:hidden"
            aria-label="Menu"
            aria-expanded={menu}
            aria-controls="mobile-menu"
            onClick={() => setMenu((v) => !v)}
          >
            <MenuIcon />
          </button>
        </div>
      </nav>

      {menu && (
        <div id="mobile-menu" className="border-t border-ink/15 px-5 pb-3 sm:hidden">
          {links.map((l) => (
            <a key={l.href} href={l.href} onClick={() => setMenu(false)} className={`${linkClass} w-full`}>{l.label}</a>
          ))}
          {accountLink(`${linkClass} w-full`)}
        </div>
      )}

      {auth.failed && (
        <p role="alert" className="mx-auto max-w-[1100px] px-5 pb-3 text-[15px] text-ink sm:px-8">
          Sign-in did not work. Please try again.
        </p>
      )}
      {notice && (
        <p role="status" className="mx-auto max-w-[1100px] px-5 pb-3 text-[15px] text-ink sm:px-8">
          Sign-in isn’t available yet.
        </p>
      )}
    </header>
  )
}
