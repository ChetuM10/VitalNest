import { useState } from 'react'
import { BookIcon, CloudOffIcon, ShieldIcon } from './icons'
import { container, pillGhostSmall } from './ui'

const steps = [
  { n: '01', title: 'Ask', text: 'Type a health question in your own words.' },
  { n: '02', title: 'We search trusted sources', text: 'We look through MedlinePlus, the World Health Organization (WHO) and the CDC.' },
  { n: '03', title: 'You see the answer and where it came from', text: 'Every answer comes with the pages it was based on.' },
]

export function HowItWorks() {
  return (
    <section id="how" aria-labelledby="how-heading" className="py-20 sm:py-28">
      <div className={container}>
        <h2 id="how-heading" className="text-[32px] font-bold leading-tight text-ink sm:text-[44px]">How it works</h2>
        <ol className="mt-10 grid gap-6 sm:grid-cols-3">
          {steps.map((step) => (
            <li key={step.n} className="rounded-[24px] border border-line bg-surface p-6">
              <span className="label-mono text-muted">{step.n}</span>
              <h3 className="mt-3 text-[22px] font-bold leading-snug text-ink">{step.title}</h3>
              <p className="mt-2 text-muted">{step.text}</p>
            </li>
          ))}
        </ol>
      </div>
    </section>
  )
}

const trust = [
  { icon: <BookIcon />, text: 'Sources shown on every answer' },
  { icon: <ShieldIcon />, text: 'Safety checks on every answer' },
  { icon: <CloudOffIcon />, text: 'Nothing stored on our servers' },
]

export function TrustStrip() {
  return (
    <section id="sources" aria-label="What you can rely on" className="border-y border-line bg-surface py-10">
      <div className={`${container} grid gap-6 sm:grid-cols-3`}>
        {trust.map((item) => (
          <p key={item.text} className="flex items-center gap-3 text-[18px] font-bold text-ink">
            <span className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-soft text-ink">{item.icon}</span>
            {item.text}
          </p>
        ))}
      </div>
    </section>
  )
}

export function ThemeToggle() {
  const read = () => document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light'
  const [theme, setTheme] = useState<'light' | 'dark'>(read)
  const choose = (value: 'light' | 'dark') => {
    document.documentElement.setAttribute('data-theme', value)
    try {
      localStorage.setItem('vitalnest-theme', value)
    } catch {
      /* storage can be blocked; the choice then lasts until the page is closed */
    }
    setTheme(value)
  }
  return (
    <div role="group" aria-label="Colour theme" className="flex gap-2">
      {(['light', 'dark'] as const).map((value) => (
        <button key={value} type="button" aria-pressed={theme === value} onClick={() => choose(value)} className={`${pillGhostSmall} ${theme === value ? 'border-ink' : ''}`}>
          {value === 'light' ? 'Light' : 'Dark'}
        </button>
      ))}
    </div>
  )
}

export function Footer() {
  return (
    <footer className="py-12">
      <div className={`${container} flex flex-col gap-6 sm:flex-row sm:items-start sm:justify-between`}>
        <div className="max-w-[66ch] space-y-3 text-[15px] text-muted">
          <p>
            VitalNest shares general health information from MedlinePlus (National Library of Medicine), the World Health Organization (WHO) and the CDC. WHO text is
            adapted under CC BY-NC-SA 3.0 IGO and is not endorsed by WHO. It is not medical advice and does not replace a healthcare professional. In an
            emergency, call your local emergency number.
          </p>
          <p>
            <a href="#safety" className="inline-flex min-h-11 items-center font-bold text-ink underline decoration-2 underline-offset-4">
              Safety and limitations
            </a>
          </p>
        </div>
        <ThemeToggle />
      </div>
    </footer>
  )
}
