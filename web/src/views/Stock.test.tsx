import { describe, it, expect } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import stock from '../lib/__fixtures__/stock.sample.json'
import Stock from './Stock'
import StockStack from '../components/StockStack'
import type { StockBundle } from '../types'

// M5.4 Stock detail + four-pane stack from the real exported bundle (stock.sample.json,
// generated from a stock_bundle.py shard, schema v3 = steady-riser block). The injected
// path renders without fetching.
const bundle = stock as unknown as StockBundle
const count = (html: string, cls: string) => html.split(cls).length - 1

describe('Stock detail (M5.4, per-name bundle)', () => {
  it('renders the per-name header with the riser headline (not composite/breakout)', () => {
    const html = renderToStaticMarkup(<Stock initial={bundle} ticker={bundle.meta.ticker} />)
    expect(html).toContain(`stk-tk">${bundle.meta.ticker}<`)
    // company name sits right next to the ticker
    expect(bundle.meta.name).toBeTruthy() // fixture sanity: the assertion below is meaningful
    expect(html).toContain(`stk-name">${bundle.meta.name}<`)
    expect(html).toContain('10 日净涨幅')     // headline = steady-riser net10
    expect(html).not.toContain('BRK PCT')     // breakout headline removed
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

// riser 诊断 — the CORE screen on the Stock surface (PRD §10.8, 2026-07-02 spine pivot II).
// The fixture carries its real riser block verbatim from the export (C9). A candidate +
// a non-candidate block are injected to exercise both branches without re-mocking compute.
const candidateRiser = {
  net5: 0.04,
  net10: 0.12,
  net20: 0.2,
  up10: 0.7,
  ddw10: -0.05,
  ker10: 0.6,
  net10_pct: 96.0,
  candidate: true,
  streak_days: 5,
}
const withRiser = (r: StockBundle['riser']): StockBundle => ({ ...bundle, riser: r })

describe('Stock riser 诊断 (core screen)', () => {
  it('renders the riser diagnostic panel from the fixture block (8 evidence rows)', () => {
    const html = renderToStaticMarkup(<Stock initial={bundle} />)
    expect(html).toContain('stk-ign')
    expect(html).toContain('riser 诊断')
    // all 8 chart-countable evidence rows are listed
    for (const label of ['NET5', 'NET10', 'NET20', 'UP10', 'DDW10', 'KER10', 'NET10 PCT', 'STREAK'])
      expect(html).toContain(`>${label}<`)
    expect(count(html, 'stk-igncrow')).toBe(8)
    // the gate is documented (compute-side; the view never re-derives the flag)
    expect(html).toContain('≥6 天上涨')
  })

  it('breakout/composite/ignition are no longer user-visible concepts', () => {
    const html = renderToStaticMarkup(<Stock initial={bundle} />)
    expect(html).not.toContain('stk-comp')            // composite 5-component stack removed
    expect(count(html, 'stk-crow')).toBe(0)
    expect(html).not.toContain('COMPOSITE')           // composite headline removed
    expect(html).not.toContain('🔥')                  // ignition marker removed
    expect(html).not.toContain('IGN PCT')             // ignition headline removed
    expect(html).not.toContain('🚀')                  // breakout marker removed
    expect(html).not.toContain('base→breakout 诊断')  // breakout panel removed
    expect(html).not.toContain('brk_pct')             // breakout percentile removed
    // the riser diagnostic (the core screen) is the focus.
    expect(html).toContain('riser 诊断')
  })

  it('marks a riser candidate (📈) with net10 / up-days / streak in the panel head', () => {
    const html = renderToStaticMarkup(<Stock initial={withRiser(candidateRiser)} />)
    expect(html).toContain('📈 连续上涨')
    expect(html).toContain('+12%')     // headline + panel net10 (pct, signed)
    expect(html).toContain('7/10')     // up10 0.7 → 7/10 (chart-countable)
    expect(html).toContain('5d')       // 连续在榜 streak
  })

  it('shows ○ 未入选 for a non-candidate', () => {
    const nonCand = withRiser({ ...candidateRiser, candidate: false, net10_pct: 50.0 })
    const html = renderToStaticMarkup(<Stock initial={nonCand} />)
    expect(html).toContain('○ 未入选')
    expect(html).not.toContain('📈 连续上涨')
  })

  it('steady-riser is the headline, with no knob (PRD §16): no per-k label, no slider, no early⟷reliable', () => {
    const html = renderToStaticMarkup(<Stock initial={bundle} />)
    expect(html).toContain('核心筛法')      // steady-riser headline label
    expect(html).toContain('10 日净涨幅')
    expect(html).not.toContain('k=')
    expect(html).not.toContain('type="range"')
    expect(html).not.toContain('early')
  })

  it('hides the panel for a bundle with no riser block (back-compat)', () => {
    const noRiser = { ...bundle, riser: null } as StockBundle
    const html = renderToStaticMarkup(<Stock initial={noRiser} />)
    expect(html).not.toContain('class="stk-ign"')
    expect(count(html, 'stk-igncrow')).toBe(0)
    expect(html).not.toContain('riser 诊断')
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
