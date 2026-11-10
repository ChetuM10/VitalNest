import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

/** Reads the colour tokens straight from styles.css and checks WCAG AA contrast in both themes. */
const css = readFileSync(resolve(process.cwd(), 'src/styles.css'), 'utf8')

function tokens(selectorStart: string): Record<string, string> {
  const start = css.indexOf(selectorStart)
  const block = css.slice(css.indexOf('{', start) + 1, css.indexOf('}', start))
  return Object.fromEntries([...block.matchAll(/--([a-z-]+):\s*(#[0-9a-f]{6})/gi)].map((m) => [m[1], m[2]]))
}

function luminance(hex: string): number {
  const channel = (i: number) => {
    const value = parseInt(hex.slice(1 + i * 2, 3 + i * 2), 16) / 255
    return value <= 0.03928 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4
  }
  return 0.2126 * channel(0) + 0.7152 * channel(1) + 0.0722 * channel(2)
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return (hi + 0.05) / (lo + 0.05)
}

const themes = { light: tokens(':root,'), dark: tokens(":root[data-theme='dark']") }

const textPairs: [string, string][] = [
  ['ink', 'page'], ['ink', 'surface'], ['ink', 'powder'], ['ink', 'soft'],
  ['muted', 'page'], ['muted', 'surface'], ['muted', 'soft'],
  ['on-coral', 'coral'], ['on-emergency', 'emergency'], ['caution-fg', 'caution-bg'],
]

describe.each(Object.entries(themes))('%s theme', (_name, t) => {
  it('defines every token', () => {
    for (const key of ['powder', 'surface', 'page', 'ink', 'muted', 'line', 'coral', 'emergency', 'caution-bg', 'caution-fg', 'focus']) {
      expect(t[key], key).toMatch(/^#[0-9a-f]{6}$/i)
    }
  })

  it.each(textPairs)('%s on %s meets WCAG AA for text (4.5:1)', (fg, bg) => {
    expect(contrast(t[fg], t[bg])).toBeGreaterThanOrEqual(4.5)
  })

  it('the focus outline is clearly visible on the page and on cards (3:1)', () => {
    expect(contrast(t.focus, t.page)).toBeGreaterThanOrEqual(3)
    expect(contrast(t.focus, t.surface)).toBeGreaterThanOrEqual(3)
    expect(contrast(t.focus, t.powder)).toBeGreaterThanOrEqual(3)
  })
})

describe('brand colours from the design brief', () => {
  it('uses the exact light values', () => {
    expect(themes.light).toMatchObject({
      powder: '#a8c9c8', surface: '#ffffff', ink: '#14282a', muted: '#4f6567', line: '#d3e0de',
      page: '#f4f8f7', coral: '#c2410c', emergency: '#b3261e', 'caution-fg': '#7a4a00', 'caution-bg': '#fff3d6',
    })
  })

  it('keeps coral as the same call-to-action colour in dark', () => {
    expect(themes.dark.coral).toBe(themes.light.coral)
    expect(themes.dark.emergency).toBe(themes.light.emergency)
  })
})
