import type { SVGProps } from 'react'

const base: SVGProps<SVGSVGElement> = {
  width: 20,
  height: 20,
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 2,
  strokeLinecap: 'round',
  strokeLinejoin: 'round',
  'aria-hidden': true,
  focusable: false,
}

export const SendIcon = (p: SVGProps<SVGSVGElement>) => (
  <svg {...base} {...p}><path d="M12 19V5" /><path d="m5 12 7-7 7 7" /></svg>
)
export const StopIcon = (p: SVGProps<SVGSVGElement>) => (
  <svg {...base} {...p} fill="currentColor" stroke="none"><rect x="6" y="6" width="12" height="12" rx="2.5" /></svg>
)
/** The corner arrow used in front of each follow-up question. */
export const ReplyArrowIcon = (p: SVGProps<SVGSVGElement>) => (
  <svg {...base} {...p}><path d="M5 4v6a3 3 0 0 0 3 3h11" /><path d="m15 9 4 4-4 4" /></svg>
)
export const MenuIcon = (p: SVGProps<SVGSVGElement>) => (
  <svg {...base} {...p}><path d="M4 7h16" /><path d="M4 12h16" /><path d="M4 17h16" /></svg>
)
export const ExternalIcon = (p: SVGProps<SVGSVGElement>) => (
  <svg {...base} width={16} height={16} {...p}><path d="M7 17 17 7" /><path d="M8 7h9v9" /></svg>
)
export const LockIcon = (p: SVGProps<SVGSVGElement>) => (
  <svg {...base} width={16} height={16} {...p}><rect x="4" y="11" width="16" height="9" rx="2.5" /><path d="M8 11V8a4 4 0 0 1 8 0v3" /></svg>
)
export const ShieldIcon = (p: SVGProps<SVGSVGElement>) => (
  <svg {...base} width={24} height={24} {...p}><path d="M12 3 5 6v5c0 4.5 2.9 8 7 10 4.1-2 7-5.5 7-10V6l-7-3Z" /><path d="m9 12 2 2 4-4" /></svg>
)
export const BookIcon = (p: SVGProps<SVGSVGElement>) => (
  <svg {...base} width={24} height={24} {...p}><path d="M5 4h10a4 4 0 0 1 4 4v12H9a4 4 0 0 1-4-4V4Z" /><path d="M5 16a4 4 0 0 1 4-4h10" /></svg>
)
export const CloudOffIcon = (p: SVGProps<SVGSVGElement>) => (
  <svg {...base} width={24} height={24} {...p}><path d="M7 18h10a4 4 0 0 0 .8-7.9A6 6 0 0 0 6.3 9.4 4.3 4.3 0 0 0 7 18Z" /><path d="m4 4 16 16" /></svg>
)
export const WarningIcon = (p: SVGProps<SVGSVGElement>) => (
  <svg {...base} width={20} height={20} {...p}><path d="M12 4 3 20h18L12 4Z" /><path d="M12 10v4" /><path d="M12 17.5v.01" /></svg>
)

/** The VitalNest mark: two soft curves in a rounded square. Colours follow the theme. */
export function LogoMark({ size = 28 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden focusable="false">
      <rect width="32" height="32" rx="9" fill="var(--ink)" />
      <path
        d="M8 11c3 0 4 1.5 5 4 1-2.5 2-4 5-4M8 21c4 1 6-1 8-6 2 5 4 7 8 6"
        fill="none"
        stroke="var(--powder)"
        strokeWidth="2.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}
