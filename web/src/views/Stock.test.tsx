import { describe, it, expect } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import board from '../lib/__fixtures__/board.sample.json'
import Stock from './Stock'
import type { BoardData } from '../types'

// M5-preview Stock contract (PRD §9.6), rendered from the real exported fixture.
const data = board as unknown as BoardData
const count = (html: string, cls: string) => html.split(cls).length - 1

describe('Stock detail (M5 preview)', () => {
  it('renders the requested per-name header', () => {
    const s = data.stocks[5]
    const html = renderToStaticMarkup(<Stock initial={data} ticker={s.ticker} />)
    expect(html).toContain(`stk-tk">${s.ticker}<`)
    expect(html).toContain('COMPOSITE')
  })

  it('defaults to the first board stock when no ticker is selected', () => {
    const html = renderToStaticMarkup(<Stock initial={data} ticker={null} />)
    expect(html).toContain(`stk-tk">${data.stocks[0].ticker}<`)
  })

  it('shows the 6 valuation multiple cards', () => {
    const html = renderToStaticMarkup(<Stock initial={data} ticker={data.stocks[0].ticker} />)
    expect(count(html, 'stk-vcard')).toBe(6)
    expect(html).toContain('Rule of 40')
    expect(html).toContain('EV/EBITDA')
  })

  it('shows the 5 composite components', () => {
    const html = renderToStaticMarkup(<Stock initial={data} ticker={data.stocks[0].ticker} />)
    expect(count(html, 'stk-crow')).toBe(5)
    expect(html).toContain('ACCEL')
  })

  it('renders theme chips with exposure % (the NVDA-style demo payload)', () => {
    // board.sample synthetic stocks carry no themes; inject the real M4.5 shape to prove
    // the chip renders exposure (AI 90% / SEMI 100%, like themes/approved/NVDA.json).
    const injected: BoardData = {
      ...data,
      stocks: [
        { ...data.stocks[0], themes: [{ theme: 'AI', exposure: 0.9 }, { theme: 'SEMI', exposure: 1.0 }] },
        ...data.stocks.slice(1),
      ],
    }
    const html = renderToStaticMarkup(<Stock initial={injected} ticker={injected.stocks[0].ticker} />)
    expect(html).toContain('stk-chip')
    expect(html).toContain('AI')
    expect(html).toContain('90%')
    expect(html).toContain('SEMI')
    expect(html).toContain('100%')
  })

  it('lists every board ticker in the per-name selector', () => {
    const html = renderToStaticMarkup(<Stock initial={data} ticker={data.stocks[0].ticker} />)
    for (const t of data.stocks.map((s) => s.ticker)) expect(html).toContain(`value="${t}"`)
  })
})
