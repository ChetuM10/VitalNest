import { ChatCard } from './components/ChatCard'
import { Hero } from './components/Hero'
import { Nav } from './components/Nav'
import { Safety } from './components/Safety'
import { Footer, HowItWorks, TrustStrip } from './components/Sections'
import { useAuth } from './hooks/useAuth'
import { useChat } from './hooks/useChat'

/** Scroll to the chat card and put the cursor in the question box. */
function focusComposer() {
  const reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  document.getElementById('ask')?.scrollIntoView({ behavior: reduced ? 'auto' : 'smooth', block: 'center' })
  window.setTimeout(() => document.getElementById('composer-input')?.focus({ preventScroll: true }), reduced ? 0 : 350)
}

export default function App() {
  const chat = useChat()
  const auth = useAuth()
  return (
    <div className="min-h-screen bg-page text-ink">
      <a href="#ask" className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-full focus:bg-surface focus:px-4 focus:py-2">
        Skip to the chat
      </a>
      <Nav onAsk={focusComposer} auth={auth} />
      <main>
        <Hero onAsk={focusComposer} />
        <ChatCard chat={chat} auth={auth} />
        <HowItWorks />
        <TrustStrip />
        <Safety />
      </main>
      <Footer />
    </div>
  )
}
