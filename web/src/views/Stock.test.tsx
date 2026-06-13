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
