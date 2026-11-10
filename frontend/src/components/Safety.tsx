import { container } from './ui'

// Keep in step with docs/safety.md.
const WONT_DO = [
  { title: 'Emergencies', text: 'If a message sounds like an emergency or mentions self-harm, VitalNest shows emergency and crisis numbers and nothing else.' },
  { title: 'Diagnosis', text: 'It cannot tell you what you have or what is causing your symptoms.' },
  { title: 'Medicines', text: 'It does not give doses, prescribe, or tell you to start, stop or change a medicine.' },
  { title: 'Other topics', text: 'It only answers general health and wellness questions.' },
]

const CHECKS = [
  'Your message is checked first for emergencies, self-harm, and requests for a diagnosis, a dose or a prescription.',
  'Answers are written only from pages found in MedlinePlus, WHO and CDC. If nothing close enough is found, VitalNest says so instead of guessing.',
  'Every sentence is checked before it is shown. If one fails, the answer stops and asks you to talk to a healthcare professional.',
  'Every answer shows its sources and a reminder that it is not medical advice.',
]

const LIMITS = [
  'The checks use simple rules. They can miss unusual wording, slang or languages other than English, and may sometimes stop a harmless question.',
  'An AI model writes the answers and can misread or oversimplify a page. Open the linked sources to check.',
  'Pages were copied on a fixed date and are not updated automatically. Health advice changes.',
  'Many topics are not covered. For anything about your own health, talk to a healthcare professional.',
]

const PRIVACY = [
  'Please do not enter personal health details.',
  'Your question is sent to Pinecone (to find pages) and Anthropic (to write the answer). The server does not store conversations.',
  'Signing in uses Amazon Cognito, which holds your email.',
]

function List({ items }: { items: string[] }) {
  return (
    <ul className="mt-3 list-disc space-y-2 pl-5 text-ink marker:text-muted">
      {items.map((item) => (
        <li key={item}>{item}</li>
      ))}
    </ul>
  )
}

export function Safety() {
  return (
    <section id="safety" aria-labelledby="safety-heading" className="scroll-mt-20 py-20 sm:py-28">
      <div className={container}>
        <h2 id="safety-heading" className="text-[32px] font-bold leading-tight text-ink sm:text-[44px]">Safety and limitations</h2>
        <p className="mt-4 max-w-[66ch] text-[18px] text-ink">
          VitalNest shares general health information. It is not a doctor, it does not diagnose, and it cannot promise that an answer is
          right or safe for you. In an emergency, call your local emergency number (112 in India and the EU, 911 in the US and Canada, 999 in the UK).
        </p>

        <h3 className="mt-10 text-[22px] font-bold text-ink">What it will not do</h3>
        <ul className="mt-4 grid gap-4 sm:grid-cols-2">
          {WONT_DO.map((item) => (
            <li key={item.title} className="rounded-[24px] border border-line bg-surface p-6">
              <p className="text-[19px] font-bold text-ink">{item.title}</p>
              <p className="mt-2 text-muted">{item.text}</p>
            </li>
          ))}
        </ul>

        <div className="mt-10 grid gap-10 md:grid-cols-2">
          <div>
            <h3 className="text-[22px] font-bold text-ink">How answers are checked</h3>
            <List items={CHECKS} />
          </div>
          <div>
            <h3 className="text-[22px] font-bold text-ink">Limitations</h3>
            <List items={LIMITS} />
          </div>
        </div>

        <h3 className="mt-10 text-[22px] font-bold text-ink">Your privacy</h3>
        <List items={PRIVACY} />
      </div>
    </section>
  )
}
