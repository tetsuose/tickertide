import { describe, it, expect } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import board from '../lib/__fixtures__/board.sample.json'
import chartFixture from '../lib/__fixtures__/board.chart.sample.json'
import Breakouts from './Breakouts'
import EvidenceCard from '../components/EvidenceCard'
import type { BoardData, BoardChartDetail, Stock } from '../types'

// AC-M1 / AC-M7 (PRD §14, §10.8; 2026-06-16 spine pivot) as a committed regression gate:
// render Breakouts + EvidenceCard from the real exported fixture (board.sample.json —
// export/board.py product, carrying the base→breakout block) via react-dom/server and assert
// the milestone's user-visible contract. The card is base→breakout-first; composite/ignition
// are no longer shown. No browser needed. schema v3: the bulk fixture has no chart (payload
// split) — the mini-chart loads lazily per card; tests inject board.chart.sample.json.
const data = board as unknown as BoardData
const chart = (chartFixture as unknown as BoardChartDetail).chart
const order = (html: string) => [...html.matchAll(/ec-tk">\s*([A-Za-z0-9]+)/g)].map((m) => m[1])
const card = (i: number) => renderToStaticMarkup(<EvidenceCard stock={data.stocks[i]} />)

// base→breakout sort key (PRD §10.8): candidate first, then brk_strength_pct desc (recall-first).
const brkKey = (s: Stock): [number, number] => [
  s.breakout?.candidate ? 1 : 0,
  s.breakout?.brk_strength_pct ?? 0,
]
const expectedBrkOrder = (stocks: Stock[]) =>
  [...stocks]
    .sort((a, b) => {
      const ka = brkKey(a)
      const kb = brkKey(b)
      for (let i = 0; i < 2; i++) if (kb[i] !== ka[i]) return kb[i] - ka[i]
      return 0
    })
    .map((s) => s.ticker)

describe('AC-M1: Breakouts evidence-card board', () => {
  it('renders >=18 cards', () => {
    const html = renderToStaticMarkup(<Breakouts initial={data} />)
    expect(order(html).length).toBeGreaterThanOrEqual(18)
  })

  it('card carries the 6 raw evidence fields', () => {
    const html = card(0)
    for (const label of ['1M', '3M', '6M', 'from high', 'week', 'vol']) expect(html).toContain(label)
  })

  it('renders the mini-chart SVG with MA lines + 52w dashed line (injected chart, v2 lazy)', () => {
    const html = renderToStaticMarkup(<EvidenceCard stock={data.stocks[0]} chart={chart} />)
    expect(html).toContain('<svg')
    expect(html).toContain('var(--ma50)')
    expect(html).toContain('stroke-dasharray')
  })

  it('without a chart (schema v2 lazy split) the card shows a skeleton, not the chart SVG', () => {
    const html = card(0)
    expect(html).toContain('ec-chart-skel')
    expect(html).not.toContain('<svg')
  })
})

// AC-M7 (PRD §10.8): Breakouts is the base→breakout board — sorted by candidate →
// brk_strength_pct, NOT by composite/ignition. base→breakout is the core engine with no
// tunable parameter (PRD §16), so nothing perturbs this order. recall-first: no persistence gate.
describe('AC-M7: Breakouts is the base→breakout board (not composite)', () => {
  it('fixture carries the breakout block with >=1 candidate (sanity for the sort assertions)', () => {
    expect(data.stocks.every((s) => s.breakout !== undefined)).toBe(true)
    const cands = data.stocks.filter((s) => s.breakout!.candidate)
    expect(cands.length).toBeGreaterThanOrEqual(1)
  })

  it('sorts by base→breakout strength: candidate first → brk_strength_pct desc', () => {
    const html = renderToStaticMarkup(<Breakouts initial={data} />)
    expect(order(html)).toEqual(expectedBrkOrder(data.stocks))
  })

  it('candidates float to the very top of the board', () => {
    const html = renderToStaticMarkup(<Breakouts initial={data} />)
    const o = order(html)
    const candTickers = new Set(data.stocks.filter((s) => s.breakout!.candidate).map((s) => s.ticker))
    const lastCandIdx = Math.max(...o.map((t, i) => (candTickers.has(t) ? i : -1)))
    for (let i = 0; i <= lastCandIdx; i++) expect(candTickers.has(o[i])).toBe(true)
    expect(lastCandIdx).toBeGreaterThanOrEqual(0)
  })

  it('higher strength outranks lower strength among candidates', () => {
    const o = order(renderToStaticMarkup(<Breakouts initial={data} />))
    const cands = data.stocks
      .filter((s) => s.breakout!.candidate)
      .sort((a, b) => (b.breakout!.brk_strength_pct ?? 0) - (a.breakout!.brk_strength_pct ?? 0))
    if (cands.length >= 2 && cands[0].breakout!.brk_strength_pct !== cands[1].breakout!.brk_strength_pct) {
      expect(o.indexOf(cands[0].ticker)).toBeLessThan(o.indexOf(cands[1].ticker))
    }
  })

  it('the base→breakout order is the sole order — no knob exists to re-sort it (PRD §16)', () => {
    const html = renderToStaticMarkup(<Breakouts initial={data} />)
    expect(order(html)).toEqual(expectedBrkOrder(data.stocks))
  })

  it('base→breakout order differs from a pure composite ranking (proves it is NOT composite-sorted)', () => {
    const compOrder = [...data.stocks]
      .sort((a, b) => (b.composite ?? 0) - (a.composite ?? 0))
      .map((s) => s.ticker)
    expect(expectedBrkOrder(data.stocks)).not.toEqual(compOrder)
  })

  it('composite/ignition are NOT shown on the card (no badge, no component panel)', () => {
    const i = data.stocks.findIndex((s) => s.composite != null)
    expect(i).toBeGreaterThanOrEqual(0)
    const html = card(i)
    expect(html).not.toContain('ec-badge')          // composite badge removed
    expect(html).not.toContain('ec-comp')           // composite 5-component panel removed
    expect(html).not.toContain('Σ wᵢ')              // composite formula note removed
    expect(html).not.toContain('🔥')                // ignition marker removed
  })
})

// AC-M7: base/τ/breakout 证据 on the card head.
describe('AC-M7: base→breakout evidence on the card', () => {
  it('renders the base/τ/breakout 证据 strip (τ / drift / fit / vol) for a breakout stock', () => {
    const i = data.stocks.findIndex((s) => s.breakout && s.breakout.evidence.tau_date != null)
    expect(i).toBeGreaterThanOrEqual(0)
    const html = card(i)
    expect(html).toContain('ec-ignev')
    for (const label of ['drift', 'fit', 'vol']) expect(html).toContain(label)
  })

  it('a candidate card shows the 🚀 breakout marker with its days-since-τ', () => {
    const ci = data.stocks.findIndex((s) => s.breakout?.candidate)
    expect(ci).toBeGreaterThanOrEqual(0)
    const html = card(ci)
    expect(html).toContain('ec-ign')
    expect(html).toContain('🚀')
    const dst = data.stocks[ci].breakout!.evidence.days_since_tau
    if (dst != null) expect(html).toContain(`${dst}d`)
  })

  it('a non-candidate card shows the dim brk_pct chip (not the 🚀 marker)', () => {
    const i = data.stocks.findIndex((s) => s.breakout && !s.breakout.candidate && s.breakout.brk_strength_pct != null)
    expect(i).toBeGreaterThanOrEqual(0)
    const html = card(i)
    expect(html).toContain('ec-ignpct')
    expect(html).toContain('brk ')
  })
})

// AC-M2.4 (C10): Breakouts respects the global scope — filter BEFORE sort (§9.3).
describe('AC-M2.4: Breakouts respects global scope', () => {
  it('scope=sector keeps only that sector', () => {
    const sector = data.stocks.find((s) => s.sector)!.sector as string
    const expected = data.stocks.filter((s) => s.sector === sector).length
    const html = renderToStaticMarkup(
      <Breakouts initial={data} scope={{ kind: 'sector', key: sector }} />,
    )
    expect(order(html).length).toBe(expected)
    expect(expected).toBeLessThan(data.stocks.length) // genuinely filtered
  })

  it('scope=pinned keeps only the pinned tickers', () => {
    const pins = [data.stocks[2].ticker, data.stocks[5].ticker]
    const html = renderToStaticMarkup(
      <Breakouts initial={data} scope={{ kind: 'pinned', key: null }} pinned={pins} />,
    )
    expect(order(html).sort()).toEqual([...pins].sort())
  })

  it('scope=all (or unset) shows everything', () => {
    const html = renderToStaticMarkup(<Breakouts initial={data} scope={{ kind: 'all', key: null }} />)
    expect(order(html).length).toBe(data.stocks.length)
  })
})
