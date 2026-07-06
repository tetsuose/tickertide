import { describe, it, expect } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import board from '../lib/__fixtures__/board.sample.json'
import chartFixture from '../lib/__fixtures__/board.chart.sample.json'
import Risers from './Risers'
import EvidenceCard from '../components/EvidenceCard'
import type { BoardData, BoardChartDetail, Stock } from '../types'

// AC-M1 / AC-M7 (PRD §14, §10.8; 2026-07-02 spine pivot II) as a committed regression gate:
// render Risers + EvidenceCard from the real exported fixture (board.sample.json —
// export/board.py product, schema v4, carrying the steady-riser block) via react-dom/server
// and assert the user-visible contract. The card is riser-first; breakout/composite/ignition
// are no longer shown. No browser needed. Payload split: the bulk fixture has no chart —
// the mini-chart loads lazily per card; tests inject board.chart.sample.json.
const data = board as unknown as BoardData
const chart = (chartFixture as unknown as BoardChartDetail).chart
const order = (html: string) => [...html.matchAll(/ec-tk">(?:<span[^>]*>)?\s*([A-Za-z0-9]+)/g)].map((m) => m[1])
const card = (i: number) => renderToStaticMarkup(<EvidenceCard stock={data.stocks[i]} />)

// steady-riser sort key (PRD §10.8.2): candidate first, then net10 desc (recall-first).
// Mirrors compute/check_ac_m7.py::_riser_key — the AC gate that verifies this exact order.
const riserKey = (s: Stock): [number, number] => [
  s.riser?.candidate ? 1 : 0,
  s.riser?.net10 ?? -Infinity,
]
const expectedRiserOrder = (stocks: Stock[]) =>
  [...stocks]
    .sort((a, b) => {
      const ka = riserKey(a)
      const kb = riserKey(b)
      for (let i = 0; i < 2; i++) if (kb[i] !== ka[i]) return kb[i] - ka[i]
      return 0
    })
    .map((s) => s.ticker)

describe('AC-M1: Risers evidence-card board', () => {
  it('renders >=18 cards', () => {
    const html = renderToStaticMarkup(<Risers initial={data} />)
    expect(order(html).length).toBeGreaterThanOrEqual(18)
  })

  it('hovering the ticker shows the company name (native title tooltip)', () => {
    const s = data.stocks[0]
    expect(s.name).toBeTruthy() // fixture sanity: the assertion below is meaningful
    expect(card(0)).toContain(`<span title="${s.name}">${s.ticker}</span>`)
  })

  it('card carries the riser evidence fields (net 5/10/20d, up-days, drawdown, vol)', () => {
    const html = card(0)
    for (const label of ['5d', '10d', '20d', '上涨天数', '回撤', 'vol']) expect(html).toContain(label)
  })

  it('renders the mini-chart SVG with MA lines + 52w dashed line (injected chart, v2 lazy)', () => {
    const html = renderToStaticMarkup(<EvidenceCard stock={data.stocks[0]} chart={chart} />)
    expect(html).toContain('<svg')
    expect(html).toContain('var(--ma50)')
    expect(html).toContain('stroke-dasharray')
  })

  it('the mini-chart highlights the last-10-trading-day riser window (static tint)', () => {
    const html = renderToStaticMarkup(<EvidenceCard stock={data.stocks[0]} chart={chart} />)
    expect(html).toContain('mc-hlwin')
  })

  it('without a chart (schema v2 lazy split) the card shows a skeleton, not the chart SVG', () => {
    const html = card(0)
    expect(html).toContain('ec-chart-skel')
    expect(html).not.toContain('<svg')
  })
})

// AC-M7 (PRD §10.8): Risers is the steady-riser board — sorted by candidate → net10 desc,
// NOT by breakout strength/composite/ignition (all retired, §16). candidate is compute's
// read-only flag — the view never re-derives it. recall-first: false positives expected.
describe('AC-M7: Risers is the steady-riser board (not breakout/composite)', () => {
  it('fixture carries the riser block with >=1 candidate (sanity for the sort assertions)', () => {
    expect(data.stocks.every((s) => s.riser !== undefined)).toBe(true)
    const cands = data.stocks.filter((s) => s.riser!.candidate)
    expect(cands.length).toBeGreaterThanOrEqual(1)
  })

  it('sorts by the riser key: candidate first → net10 desc (mirrors check_ac_m7._riser_key)', () => {
    const html = renderToStaticMarkup(<Risers initial={data} />)
    expect(order(html)).toEqual(expectedRiserOrder(data.stocks))
  })

  it('candidates float to the very top of the board', () => {
    const html = renderToStaticMarkup(<Risers initial={data} />)
    const o = order(html)
    const candTickers = new Set(data.stocks.filter((s) => s.riser!.candidate).map((s) => s.ticker))
    const lastCandIdx = Math.max(...o.map((t, i) => (candTickers.has(t) ? i : -1)))
    for (let i = 0; i <= lastCandIdx; i++) expect(candTickers.has(o[i])).toBe(true)
    expect(lastCandIdx).toBeGreaterThanOrEqual(0)
  })

  it('higher net10 outranks lower net10 among candidates', () => {
    const o = order(renderToStaticMarkup(<Risers initial={data} />))
    const cands = data.stocks
      .filter((s) => s.riser!.candidate)
      .sort((a, b) => (b.riser!.net10 ?? -Infinity) - (a.riser!.net10 ?? -Infinity))
    if (cands.length >= 2 && cands[0].riser!.net10 !== cands[1].riser!.net10) {
      expect(o.indexOf(cands[0].ticker)).toBeLessThan(o.indexOf(cands[1].ticker))
    }
  })

  it('the riser order is the sole order — no knob exists to re-sort it (PRD §16)', () => {
    const html = renderToStaticMarkup(<Risers initial={data} />)
    expect(order(html)).toEqual(expectedRiserOrder(data.stocks))
  })

  it('riser order differs from a pure composite ranking (proves it is NOT composite-sorted)', () => {
    const compOrder = [...data.stocks]
      .sort((a, b) => (b.composite ?? 0) - (a.composite ?? 0))
      .map((s) => s.ticker)
    expect(expectedRiserOrder(data.stocks)).not.toEqual(compOrder)
  })

  it('candidate is read from the flag, never re-derived from net10_pct (C9, #92–#94 lesson)', () => {
    // the fixture has stocks where the flag and a naive pct>=90 derivation DISAGREE
    // (the gate has an up10 condition + top-N cut) — the board must follow the FLAG.
    const flagged = new Set(data.stocks.filter((s) => s.riser!.candidate).map((s) => s.ticker))
    const derived = new Set(
      data.stocks.filter((s) => (s.riser!.net10_pct ?? 0) >= 90).map((s) => s.ticker),
    )
    expect(flagged).not.toEqual(derived) // sanity: the derivation would give a DIFFERENT set
    const o = order(renderToStaticMarkup(<Risers initial={data} />))
    const lastCandIdx = Math.max(...o.map((t, i) => (flagged.has(t) ? i : -1)))
    for (let i = 0; i <= lastCandIdx; i++) expect(flagged.has(o[i])).toBe(true)
  })

  it('breakout/composite/ignition are NOT shown on the card', () => {
    const i = data.stocks.findIndex((s) => s.composite != null)
    expect(i).toBeGreaterThanOrEqual(0)
    const html = card(i)
    expect(html).not.toContain('ec-badge')          // composite badge removed
    expect(html).not.toContain('ec-comp')           // composite 5-component panel removed
    expect(html).not.toContain('Σ wᵢ')              // composite formula note removed
    expect(html).not.toContain('🔥')                // ignition marker removed
    expect(html).not.toContain('🚀')                // breakout marker removed
    expect(html).not.toContain('drift')             // base/τ/breakout evidence strip removed
    expect(html).not.toContain('τ')                 // no changepoint annotation anywhere
  })
})

// AC-M7: riser evidence on the card head.
describe('AC-M7: riser evidence on the card', () => {
  it('a candidate card shows the 📈 badge with 连续在榜 N 天', () => {
    const ci = data.stocks.findIndex((s) => s.riser?.candidate && s.riser.streak_days != null)
    expect(ci).toBeGreaterThanOrEqual(0)
    const html = card(ci)
    expect(html).toContain('ec-ign')
    expect(html).toContain('📈')
    expect(html).toContain(`在榜${data.stocks[ci].riser!.streak_days}d`)
    expect(html).toContain('连续在榜')
  })

  it('a non-candidate card shows the dim net10 chip (not the 📈 badge)', () => {
    const i = data.stocks.findIndex((s) => s.riser && !s.riser.candidate && s.riser.net10 != null)
    expect(i).toBeGreaterThanOrEqual(0)
    const html = card(i)
    expect(html).toContain('ec-ignpct')
    expect(html).toContain('10d ')
    expect(html).not.toContain('📈')
  })

  it('up-days render as x/10 (up10 × 10) and drawdown as a percent', () => {
    const i = data.stocks.findIndex((s) => s.riser?.up10 != null && s.riser.ddw10 != null)
    expect(i).toBeGreaterThanOrEqual(0)
    const r = data.stocks[i].riser!
    const html = card(i)
    expect(html).toContain(`${Math.round((r.up10 as number) * 10)}/10`)
    expect(html).toContain(((r.ddw10 as number) * 100).toFixed(1) + '%')
  })
})

// AC-M2.4 (C10): Risers respects the global scope — filter BEFORE sort (§9.3).
describe('AC-M2.4: Risers respects global scope', () => {
  it('scope=sector keeps only that sector', () => {
    const sector = data.stocks.find((s) => s.sector)!.sector as string
    const expected = data.stocks.filter((s) => s.sector === sector).length
    const html = renderToStaticMarkup(
      <Risers initial={data} scope={{ kind: 'sector', key: sector }} />,
    )
    expect(order(html).length).toBe(expected)
    expect(expected).toBeLessThan(data.stocks.length) // genuinely filtered
  })

  it('scope=pinned keeps only the pinned tickers', () => {
    const pins = [data.stocks[2].ticker, data.stocks[5].ticker]
    const html = renderToStaticMarkup(
      <Risers initial={data} scope={{ kind: 'pinned', key: null }} pinned={pins} />,
    )
    expect(order(html).sort()).toEqual([...pins].sort())
  })

  it('scope=all (or unset) shows everything', () => {
    const html = renderToStaticMarkup(<Risers initial={data} scope={{ kind: 'all', key: null }} />)
    expect(order(html).length).toBe(data.stocks.length)
  })
})
