import { describe, expect, it } from 'vitest'
import { cleanSnippet, sourceLabel } from './SourceCards'

describe('cleanSnippet', () => {
  it('removes a leading list dash and turns flattened list dashes into separators', () => {
    expect(cleanSnippet('- Being exposed to smoke - Genetics and family history. You are')).toBe(
      'Being exposed to smoke · Genetics and family history. You are',
    )
  })

  it('leaves ordinary hyphens inside words alone', () => {
    expect(cleanSnippet('A long-term, high-risk condition.')).toBe('A long-term, high-risk condition.')
  })
})

describe('sourceLabel', () => {
  it('builds "MedlinePlus · National Library of Medicine" from the attribution the server sends', () => {
    expect(sourceLabel({ title: 't', url: 'u', snippet: 's', source_name: 'MedlinePlus', attribution: 'Courtesy of MedlinePlus from the National Library of Medicine' }))
      .toBe('MedlinePlus · National Library of Medicine')
  })

  it('falls back to the source name', () => {
    expect(sourceLabel({ title: 't', url: 'u', snippet: 's', source_name: 'MedlinePlus', attribution: '' })).toBe('MedlinePlus')
  })
})
