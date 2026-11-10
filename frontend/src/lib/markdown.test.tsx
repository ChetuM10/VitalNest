import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { Answer, parseBlocks, safeUrl } from './markdown'

describe('parseBlocks', () => {
  it('splits paragraphs and bullet lists', () => {
    expect(parseBlocks('Intro line.\n\n- Cough\n- Wheeze\n\nClosing.')).toEqual([
      { type: 'p', text: 'Intro line.' },
      { type: 'ul', items: ['Cough', 'Wheeze'] },
      { type: 'p', text: 'Closing.' },
    ])
  })

  it('treats a list that directly follows a sentence as its own block', () => {
    expect(parseBlocks('Signs include:\n- Fever\n- Cough')).toEqual([
      { type: 'p', text: 'Signs include:' },
      { type: 'ul', items: ['Fever', 'Cough'] },
    ])
  })

  it('joins soft-wrapped lines into one paragraph and ignores empty text', () => {
    expect(parseBlocks('One line\nsecond line')).toEqual([{ type: 'p', text: 'One line second line' }])
    expect(parseBlocks('  \n\n')).toEqual([])
  })
})

describe('Answer', () => {
  it('renders bold text and list items', () => {
    render(<Answer text={'**Avoid triggers.** Rest.\n\n- Item one\n- Item two'} />)
    expect(screen.getByText('Avoid triggers.').tagName).toBe('STRONG')
    expect(screen.getAllByRole('listitem')).toHaveLength(2)
  })

  it('never turns markup in the text into elements', () => {
    const { container } = render(<Answer text={'<img src=x onerror=alert(1)> <script>alert(1)</script> done.'} />)
    expect(container.querySelector('img')).toBeNull()
    expect(container.querySelector('script')).toBeNull()
    expect(container.textContent).toContain('<script>alert(1)</script>')
  })

  it('caps the line length of answers at 66 characters', () => {
    const { container } = render(<Answer text="Hello there." />)
    expect((container.firstChild as HTMLElement).className).toContain('max-w-[66ch]')
  })
})

describe('safeUrl', () => {
  it('allows https links only', () => {
    expect(safeUrl('https://medlineplus.gov/asthma.html')).toBe('https://medlineplus.gov/asthma.html')
    for (const bad of ['javascript:alert(1)', 'data:text/html,hi', 'http://medlineplus.gov', 'not a url', '']) {
      expect(safeUrl(bad)).toBe('#')
    }
  })
})
