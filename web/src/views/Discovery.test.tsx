import { describe, it, expect } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import board from '../lib/__fixtures__/board.sample.json'
import chartFixture from '../lib/__fixtures__/board.chart.sample.json'
import Discovery from './Discovery'
import EvidenceCard from '../components/EvidenceCard'
import type { BoardData, BoardChartDetail, Stock } from '../types'

// AC-M1 / AC-M7 / M8 (PRD §14, §10.8) as a committed regression gate: render Discovery +
// EvidenceCard from the real exported fixture (board.sample.json — export/board.py product,
// carrying the ignition block) via react-dom/server and assert the milestone's user-visible
// contract. M8: the card is ignition-first; composite is no longer shown. No browser needed.
// schema v2: the bulk fixture has no chart (payload split) — the mini-chart loads lazily per
// card; tests inject board.chart.sample.json (a BoardChartDetail) to render it under SSR.
const data = board as unknown as BoardData
const chart = (chartFixture as unknown as BoardChartDetail).chart
const order = (html: string) => [...html.matchAll(/ec-tk">\s*([A-Za-z0-9]+)/g)].map((m) => m[1])
const card = (i: number) => renderToStaticMarkup(<EvidenceCard stock={data.stocks[i]} />)

// Sustained-ignition sort key (PRD §10.8.2): candidate first, then persist desc, then pct desc.
const ignKey = (s: Stock): [number, number, number] => [
  s.ignition?.candidate ? 1 : 0,
  s.ignition?.ign_persist_days ?? 0,
  s.ignition?.ign_pct ?? 0,
]
const expectedIgnOrder = (stocks: Stock[]) =>
  [...stocks]
    .sort((a, b) => {
      const ka = ignKey(a)
      const kb = ignKey(b)
      for (let i = 0; i < 3; i++) if (kb[i] !== ka[i]) return kb[i] - ka[i]
      return 0
    })
    .map((s) => s.ticker)

describe('AC-M1: Discovery evidence-card board', () => {
  it('renders >=18 cards', () => {
    const html = renderToStaticMarkup(<Discovery initial={data} />)
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
    // The bulk board.json carries no chart; the card fetches it on render. SSR runs no
    // effects, so the fetch never fires — the card renders its text evidence + a fixed-height
    // skeleton placeholder (no MiniChart svg). The chart is supplementary (PRD §9.3).
    const html = card(0)
    expect(html).toContain('ec-chart-skel')
    expect(html).not.toContain('<svg')
  })
})

// AC-M7 (PRD §10.8.2): Discovery is the 持续点火 (sustained-ignition) board — sorted by
// candidate → ign_persist_days → ign_pct, NOT by composite. ignition is the project's
// core engine with no tunable parameter; the former early⟷reliable knob is gone (PRD §16),
// so nothing perturbs this order. composite stays as a fixed-weight 已确认 side-read badge.
describe('AC-M7: Discovery is the sustained-ignition board (not composite)', () => {
  it('fixture carries the ignition block with >=1 candidate (sanity for the sort assertions)', () => {
    expect(data.stocks.every((s) => s.ignition !== undefined)).toBe(true)
    const cands = data.stocks.filter((s) => s.ignition!.candidate)
    expect(cands.length).toBeGreaterThanOrEqual(1)
  })

  it('sorts by sustained ignition: candidate first → persist desc → pct desc', () => {
    const html = renderToStaticMarkup(<Discovery initial={data} />)
    expect(order(html)).toEqual(expectedIgnOrder(data.stocks))
  })

  it('candidates float to the very top of the board', () => {
    const html = renderToStaticMarkup(<Discovery initial={data} />)
    const o = order(html)
    const candTickers = new Set(data.stocks.filter((s) => s.ignition!.candidate).map((s) => s.ticker))
    // every candidate occupies a prefix slot — no non-candidate ranks above any candidate.
    const lastCandIdx = Math.max(...o.map((t, i) => (candTickers.has(t) ? i : -1)))
    for (let i = 0; i <= lastCandIdx; i++) expect(candTickers.has(o[i])).toBe(true)
    expect(lastCandIdx).toBeGreaterThanOrEqual(0)
  })

  it('higher persistence outranks lower persistence among candidates', () => {
    const o = order(renderToStaticMarkup(<Discovery initial={data} />))
    const cands = data.stocks
      .filter((s) => s.ignition!.candidate)
      .sort((a, b) => (b.ignition!.ign_persist_days ?? 0) - (a.ignition!.ign_persist_days ?? 0))
    if (cands.length >= 2 && cands[0].ignition!.ign_persist_days !== cands[1].ignition!.ign_persist_days) {
      expect(o.indexOf(cands[0].ticker)).toBeLessThan(o.indexOf(cands[1].ticker))
    }
  })

  it('the ignition order is the sole order — no knob exists to re-sort it (PRD §16)', () => {
    // Discovery no longer takes a k prop; the board's only order is sustained ignition.
    const html = renderToStaticMarkup(<Discovery initial={data} />)
    expect(order(html)).toEqual(expectedIgnOrder(data.stocks))
  })

  it('ignition order differs from a pure composite ranking (proves it is NOT composite-sorted)', () => {
    // composite still exists in the engine export (calc-layer), but it no longer drives any
    // order or UI — the board order must not coincide with a composite ranking.
    const compOrder = [...data.stocks]
      .sort((a, b) => (b.composite ?? 0) - (a.composite ?? 0))
      .map((s) => s.ticker)
    expect(expectedIgnOrder(data.stocks)).not.toEqual(compOrder)
  })

  it('M8: composite is NOT shown on the card (no badge, no 5-component panel)', () => {
    const i = data.stocks.findIndex((s) => s.composite != null)
    expect(i).toBeGreaterThanOrEqual(0)
    const html = card(i)
    expect(html).not.toContain('ec-badge')          // composite badge removed
    expect(html).not.toContain('ec-comp')           // composite 5-component panel removed
    expect(html).not.toContain('Σ wᵢ')              // composite formula note removed
  })
})

// AC-M7: 点火证据 (ignition evidence) on the card head + step-rate clamp (M7.2 pitfall).
describe('AC-M7: ignition evidence + step-rate clamp on the card', () => {
  it('renders the 点火证据 strip (breakout / vol× / step / MA50) for an ignition stock', () => {
    const i = data.stocks.findIndex((s) => s.ignition && s.ignition.evidence.breakout_day != null)
    expect(i).toBeGreaterThanOrEqual(0)
    const html = card(i)
    expect(html).toContain('ec-ignev')
    for (const label of ['brk', 'vol', 'step', 'MA50']) expect(html).toContain(label)
  })

  it('a candidate card shows the 🔥 sustained-ignition marker with its persist days', () => {
    const ci = data.stocks.findIndex((s) => s.ignition?.candidate)
    expect(ci).toBeGreaterThanOrEqual(0)
    const html = card(ci)
    expect(html).toContain('ec-ign')
    expect(html).toContain(`${data.stocks[ci].ignition!.ign_persist_days}d`)
  })

  it('reclaimed_ma50 renders as 收复/未收复 (the ig_breakout gate is human-readable)', () => {
    const i = data.stocks.findIndex((s) => s.ignition?.evidence.reclaimed_ma50 === true)
    expect(i).toBeGreaterThanOrEqual(0)
    expect(card(i)).toContain('收复')
  })

  it('clamps a blown-up step_rate_ratio for display (ret50≈0 → huge value, M7.2 pitfall)', () => {
    // fixture has a stock with |step_rate_ratio| >> 20 (e.g. TT20≈685): the raw number
    // must NOT appear verbatim; the card shows a clamped >20× instead.
    const SR_CLAMP = 20
    const i = data.stocks.findIndex(
      (s) => (s.ignition?.evidence.step_rate_ratio ?? 0) > SR_CLAMP,
    )
    expect(i).toBeGreaterThanOrEqual(0)
    const raw = data.stocks[i].ignition!.evidence.step_rate_ratio as number
    const html = card(i)
    expect(html).toContain(`&gt;${SR_CLAMP}×`) // clamped marker (renderToStaticMarkup escapes >)
    expect(html).not.toContain(raw.toFixed(1)) // the blown-up value is never shown verbatim
  })
})

// AC-M2.4 (C10): Discovery respects the global scope — filter BEFORE sort (§9.3).
describe('AC-M2.4: Discovery respects global scope', () => {
  it('scope=sector keeps only that sector', () => {
    const sector = data.stocks.find((s) => s.sector)!.sector as string
    const expected = data.stocks.filter((s) => s.sector === sector).length
    const html = renderToStaticMarkup(
      <Discovery initial={data} scope={{ kind: 'sector', key: sector }} />,
    )
    expect(order(html).length).toBe(expected)
    expect(expected).toBeLessThan(data.stocks.length) // genuinely filtered
  })

  it('scope=pinned keeps only the pinned tickers', () => {
    const pins = [data.stocks[2].ticker, data.stocks[5].ticker]
    const html = renderToStaticMarkup(
      <Discovery initial={data} scope={{ kind: 'pinned', key: null }} pinned={pins} />,
    )
    expect(order(html).sort()).toEqual([...pins].sort())
  })

  it('scope=all (or unset) shows everything', () => {
    const html = renderToStaticMarkup(<Discovery initial={data} scope={{ kind: 'all', key: null }} />)
    expect(order(html).length).toBe(data.stocks.length)
  })
})
