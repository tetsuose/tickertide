import { describe, it, expect } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import stock from '../lib/__fixtures__/stock.sample.json'
import Stock from './Stock'
import StockStack from '../components/StockStack'
import type { StockBundle } from '../types'

// M5.4 Stock detail + four-pane stack from the real exported bundle (stock.sample.json,
// generated from a stock_bundle.py shard). The injected path renders without fetching.
const bundle = stock as unknown as StockBundle
const count = (html: string, cls: string) => html.split(cls).length - 1

describe('Stock detail (M5.4, per-name bundle)', () => {
  it('renders the per-name header from the bundle', () => {
    const html = renderToStaticMarkup(<Stock initial={bundle} ticker={bundle.meta.ticker} />)
    expect(html).toContain(`stk-tk">${bundle.meta.ticker}<`)
    expect(html).toContain('COMPOSITE')
  })

  it('renders theme chips with exposure %', () => {
    // fixture TT07 carries ROBO 58%
    const html = renderToStaticMarkup(<Stock initial={bundle} />)
    expect(html).toContain('stk-chip')
    expect(html).toContain(bundle.meta.themes[0].theme)
    expect(html).toContain(`${Math.round((bundle.meta.themes[0].exposure ?? 0) * 100)}%`)
  })

  it('shows the 6 valuation cards + 5 components', () => {
    const html = renderToStaticMarkup(<Stock initial={bundle} />)
    expect(count(html, 'stk-vcard')).toBe(6)
    expect(count(html, 'stk-crow')).toBe(5)
    expect(html).toContain('Rule of 40')
  })

  it('renders the four-pane time-aligned stack (not the preview MiniChart)', () => {
    const html = renderToStaticMarkup(<Stock initial={bundle} />)
    expect(html).toContain('stk-stack')
  })
})

// M7.4 点火诊断 (ignition diagnostic) — the SECOND engine on the Stock surface (PRD §10.8).
// The fixture (TT07) carries its real ignition block verbatim from the export (C9). A real
// candidate block (TT22, 🔥 ign_pct 96.6 / persist 6) and a blown-up step_rate are injected to
// exercise the candidate + clamp branches without re-mocking the engine.
const igEvidence = (over: Partial<NonNullable<StockBundle['ignition']>['evidence']> = {}) => ({
  breakout_day: '2026-06-05',
  days_since_breakout: 0,
  vol_mult: 0.994,
  step_rate_ratio: 1.59,
  reclaimed_ma50: true,
  ma50: 189.2,
  ...over,
})
const candidateIgnition = {
  ignition: 82.07,
  ign_pct: 96.6,
  ign_persist_days: 6,
  candidate: true,
  components: { accel: 0.0087, expand: 1.2455, vsurge: 0.9938, breakout: 1.0, rsturn: 0.0566 },
  evidence: igEvidence(),
}
const withIgnition = (ign: StockBundle['ignition']): StockBundle => ({ ...bundle, ignition: ign })

describe('Stock 点火诊断 (M7.4, second engine — ignition)', () => {
  it('renders the ignition diagnostic panel from the fixture block (5 components + 点火证据)', () => {
    const html = renderToStaticMarkup(<Stock initial={bundle} />)
    // panel + its title
    expect(html).toContain('stk-ign')
    expect(html).toContain('点火诊断')
    // all 5 raw ignition components are listed
    for (const label of ['ACCEL', 'EXPAND', 'VSURGE', 'BREAKOUT', 'RSTURN'])
      expect(html).toContain(`>${label}<`)
    expect(count(html, 'stk-igncrow')).toBe(5)
    // the 点火证据 strip reuses the M7.3 .ec-ignev idiom (breakout / vol× / step / MA50)
    expect(html).toContain('ec-ignev')
    expect(html).toContain('MA50')
    // persistence timeline present
    expect(html).toContain('stk-igntl')
  })

  it('does NOT touch composite (parallel engine, NOT the early⟷reliable knob; PRD P7)', () => {
    // composite stack is still its own section; ignition is additive, not a replacement.
    const html = renderToStaticMarkup(<Stock initial={bundle} />)
    expect(html).toContain('stk-comp')
    expect(count(html, 'stk-crow')).toBe(5) // composite's 5 components untouched
    expect(html).toContain('COMPOSITE')
  })

  it('marks a 持续点火 candidate (🔥) with the streak (uses TT22 real block)', () => {
    const html = renderToStaticMarkup(<Stock initial={withIgnition(candidateIgnition)} />)
    expect(html).toContain('🔥 持续点火')
    expect(html).toContain('持续')
    // persistence streak = 6 lit day-cells
    expect(count(html, 'stk-igntl-c on')).toBe(6)
    // ign_pct shown rounded
    expect(html).toContain('96')
  })

  it('shows ○ 未点火 for a non-candidate (fixture TT07: persist=0)', () => {
    const html = renderToStaticMarkup(<Stock initial={bundle} />)
    expect(html).toContain('○ 未点火')
    expect(count(html, 'stk-igntl-c on')).toBe(0) // no lit cells when persist=0
  })

  it('clamps a blown-up step_rate_ratio (>20×) on the evidence strip', () => {
    const blown = withIgnition({ ...candidateIgnition, evidence: igEvidence({ step_rate_ratio: 685 }) })
    const html = renderToStaticMarkup(<Stock initial={blown} />)
    // renderToStaticMarkup escapes '>' as '&gt;' (same as the Discovery clamp assertion)
    expect(html).toContain('&gt;20×')
  })

  it('the knob k does NOT re-render the ignition panel (k=0 == k=1 for the ignition block)', () => {
    const early = renderToStaticMarkup(<Stock initial={bundle} k={0} />)
    const reliable = renderToStaticMarkup(<Stock initial={bundle} k={1} />)
    const slice = (h: string) => h.slice(h.indexOf('stk-ign'), h.indexOf('stk-vals'))
    expect(slice(early)).toBe(slice(reliable))
  })

  it('hides the panel for a pre-M7.4 bundle with no ignition block (back-compat)', () => {
    const noIgn = { ...bundle, ignition: null } as StockBundle
    const html = renderToStaticMarkup(<Stock initial={noIgn} />)
    // the diagnostic panel + its components are gone (the foot keeps a prose mention, so we
    // assert on the panel's class structure, not the words).
    expect(html).not.toContain('class="stk-ign"')
    expect(count(html, 'stk-igncrow')).toBe(0)
    expect(html).not.toContain('点火诊断 · ignition')
  })
})

describe('StockStack (M5.4 four panes, one x axis)', () => {
  it('labels all four panes', () => {
    const html = renderToStaticMarkup(<StockStack bundle={bundle} />)
    for (const label of ['PRICE', 'VOL', 'REVENUE', 'P/S']) expect(html).toContain(`>${label}<`)
  })

  it('draws quarter gridlines (one per revenue quarter) + the P/S line', () => {
    const html = renderToStaticMarkup(<StockStack bundle={bundle} />)
    // P/S over time line uses the blue stroke
    expect(html).toContain('var(--blu)')
    // revenue bars + candles render as rects; svg present
    expect(html).toContain('<svg')
    expect(html).toContain('<rect')
  })

  it('renders empty-safe with no price data', () => {
    const empty = { ...bundle, price: { ...bundle.price, dates: [], close: [] } } as StockBundle
    const html = renderToStaticMarkup(<StockStack bundle={empty} />)
    expect(html).toContain('<svg')
  })
})
