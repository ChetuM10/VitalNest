import { container, pillCoral } from './ui'

/** The powder-blue band. Its bottom padding leaves room for the chat card to overlap its lower edge. */
export function Hero({ onAsk }: { onAsk: () => void }) {
  return (
    <section id="top" className="bg-powder pb-48 pt-10 sm:pb-56 sm:pt-20">
      <div className={container}>
        <h1 className="max-w-[16ch] text-balance text-[36px] font-bold leading-[1.04] tracking-tight text-ink sm:text-[56px] lg:text-[72px]">
          Health answers, with sources.
        </h1>
        <p className="mt-5 max-w-[46ch] text-[19px] leading-relaxed text-ink">
          Plain-language answers from MedlinePlus, WHO and the CDC, with every source shown.
        </p>
        <div className="mt-8 flex flex-wrap items-center gap-x-6 gap-y-3">
          <button type="button" onClick={onAsk} className={pillCoral}>Ask a question</button>
          <a href="#how" className="inline-flex min-h-11 items-center text-[17px] font-bold text-ink underline decoration-2 underline-offset-4">
            How it works
          </a>
        </div>
        <p className="label-mono mt-8 text-ink">Informational only. Not medical advice.</p>
      </div>
    </section>
  )
}
