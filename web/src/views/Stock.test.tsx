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
  it('renders the per-name header with the ignition headline (not composite)', () => {
    const html = renderToStaticMarkup(<Stock initial={bundle} ticker={bundle.meta.ticker} />)
    expect(html).toContain(`stk-tk">${bundle.meta.ticker}<`)
    expect(html).toContain('BRK PCT')        // headline = base→breakout
    expect(html).not.toContain('COMPOSITE')   // composite headline removed
  })

  it('renders theme chips with exposure %', () => {
    // fixture TT07 carries ROBO 58%
    const html = renderToStaticMarkup(<Stock initial={bundle} />)
    expect(html).toContain('stk-chip')
    expect(html).toContain(bundle.meta.themes[0].theme)
    expect(html).toContain(`${Math.round((bundle.meta.themes[0].exposure ?? 0) * 100)}%`)
  })

  it('shows the 6 valuation cards (composite 5-component stack is gone, M8)', () => {
    const html = renderToStaticMarkup(<Stock initial={bundle} />)
    expect(count(html, 'stk-vcard')).toBe(6)
    expect(count(html, 'stk-crow')).toBe(0)   // composite components removed
    expect(html).toContain('Rule of 40')
  })

  it('renders the four-pane time-aligned stack (not the preview MiniChart)', () => {
    const html = renderToStaticMarkup(<Stock initial={bundle} />)
    expect(html).toContain('stk-stack')
  })

  it('shows the formal-filing PIT basis note (period / filed / effective, §10.5)', () => {
    const html = renderToStaticMarkup(<Stock initial={bundle} />)
    expect(html).toContain('formal-filing PIT')
    expect(html).toContain('入估值序列')
    expect(html).toContain(bundle.valuation!.as_of_effective_eod!) // 2026-05-23
  })
})

// base/τ/breakout 诊断 — the CORE engine on the Stock surface (PRD §10.8, 2026-06-16 pivot).
// The fixture carries its real breakout block verbatim from the export (C9). A candidate +
// a non-candidate block are injected to exercise both branches without re-mocking the engine.
const brkEvidence = (over: Partial<NonNullable<StockBundle['breakout']>['evidence']> = {}) => ({
  tau_date: '2026-03-01',
  days_since_tau: 96,
  drift_step: 0.24,
  fit_gain: 0.88,
  clearance: 0.6,
  vol_mult: 1.2,
  ma50: 189.2,
  ...over,
})
const candidateBreakout = {
  brk_strength_pct: 96.0,
  brk_strength: 0.45,
  candidate: true,
  features: { base_slope: 0.01, brk_slope: 0.25, drift_step: 0.24, fit_gain: 0.88, clearance: 0.6, vsurge: 1.2 },
  evidence: brkEvidence(),
}
const withBreakout = (brk: StockBundle['breakout']): StockBundle => ({ ...bundle, breakout: brk })

describe('Stock base→breakout 诊断 (core engine)', () => {
  it('renders the base→breakout diagnostic panel from the fixture block (6 features + 证据)', () => {
    const html = renderToStaticMarkup(<Stock initial={bundle} />)
    expect(html).toContain('stk-ign')
    expect(html).toContain('base→breakout 诊断')
    // all 6 dimensionless features are listed
    for (const label of ['BASE', 'BRK', 'DRIFT', 'FIT', 'CLEAR', 'VSURGE'])
      expect(html).toContain(`>${label}<`)
    expect(count(html, 'stk-igncrow')).toBe(6)
    // the base/τ/breakout 证据 strip reuses the .ec-ignev idiom (τ / drift / fit / vol)
    expect(html).toContain('ec-ignev')
    expect(html).toContain('drift')
  })

  it('composite/ignition are no longer user-visible concepts (no stack, no big score, no 🔥)', () => {
    const html = renderToStaticMarkup(<Stock initial={bundle} />)
    expect(html).not.toContain('stk-comp')   // composite 5-component stack removed
    expect(count(html, 'stk-crow')).toBe(0)
    expect(html).not.toContain('COMPOSITE')  // composite headline removed
    expect(html).not.toContain('🔥')         // ignition marker removed
    expect(html).not.toContain('IGN PCT')    // ignition headline removed
    // the base→breakout diagnostic (the core engine) remains the focus.
    expect(html).toContain('base→breakout 诊断')
  })

  it('marks a base→breakout candidate (🚀) with days-since-τ', () => {
    const html = renderToStaticMarkup(<Stock initial={withBreakout(candidateBreakout)} />)
    expect(html).toContain('🚀 已突破')
    // brk_pct shown rounded
    expect(html).toContain('96')
    // τ + days-since-τ on the evidence strip
    expect(html).toContain('96d前')
  })

  it('shows ○ 未突破 for a non-candidate', () => {
    const nonCand = withBreakout({ ...candidateBreakout, candidate: false, brk_strength_pct: 50.0 })
    const html = renderToStaticMarkup(<Stock initial={nonCand} />)
    expect(html).toContain('○ 未突破')
  })

  it('base→breakout is the headline, with no knob (PRD §16): no per-k label, no slider, no early⟷reliable', () => {
    const html = renderToStaticMarkup(<Stock initial={bundle} />)
    expect(html).toContain('发现核心')      // base→breakout headline label
    expect(html).toContain('BRK PCT')
    expect(html).not.toContain('k=')
    expect(html).not.toContain('type="range"')
    expect(html).not.toContain('early')
  })

  it('hides the panel for a bundle with no breakout block (back-compat)', () => {
    const noBrk = { ...bundle, breakout: null } as StockBundle
    const html = renderToStaticMarkup(<Stock initial={noBrk} />)
    expect(html).not.toContain('class="stk-ign"')
    expect(count(html, 'stk-igncrow')).toBe(0)
    expect(html).not.toContain('base→breakout 诊断')
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

  it('draws formal-filing markers at effective_eod_date for in-window quarters (§10.5)', () => {
    const html = renderToStaticMarkup(<StockStack bundle={bundle} />)
    // the latest in-window quarter's effective marker is labeled "filed"
    expect(html).toContain('>filed<')
    // markers are dashed verticals (distinct from the solid quarter gridlines)
    expect(html).toContain('stroke-dasharray="2 2"')
  })

  it('renders empty-safe with no price data', () => {
    const empty = { ...bundle, price: { ...bundle.price, dates: [], close: [] } } as StockBundle
    const html = renderToStaticMarkup(<StockStack bundle={empty} />)
    expect(html).toContain('<svg')
  })
})
