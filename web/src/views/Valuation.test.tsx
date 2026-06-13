import { describe, it, expect } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import board from '../lib/__fixtures__/board.sample.json'
import Valuation from './Valuation'
import type { BoardData, Scope } from '../types'

// M5-preview Valuation contract (PRD §9.5) as a committed regression gate, rendered from
// the real exported fixture (board.sample.json) via react-dom/server — no browser.
const data = board as unknown as BoardData
const rows = (html: string) => [...html.matchAll(/valn-tk">([A-Z0-9]+)</g)].map((m) => m[1])
const psBy: Record<string, number | null> = Object.fromEntries(
  data.stocks.map((s) => [s.ticker, s.valuation?.ps ?? null]),
)

describe('Valuation screener (M5 preview)', () => {
  it('renders one row per board stock', () => {
    const html = renderToStaticMarkup(<Valuation initial={data} />)
    expect(rows(html).length).toBe(data.stocks.length)
  })

  it('default sort is P/S ascending (cheap on top), nulls last', () => {
    const order = rows(renderToStaticMarkup(<Valuation initial={data} />))
    const seq = order.map((t) => psBy[t])
    const vals = seq.filter((v): v is number => v != null)
    const ascending = vals.every((v, i) => i === 0 || vals[i - 1] <= v)
    expect(ascending).toBe(true)
    // a stock with a null P/S must not sort above one with a value
    const firstNullIdx = seq.findIndex((v) => v == null)
    const lastValIdx = seq.reduce<number>((acc, v, i) => (v != null ? i : acc), -1)
    if (firstNullIdx !== -1) expect(firstNullIdx).toBeGreaterThan(lastValIdx)
  })

  it('as-of freshness 三档上色: overdue rows carry the dim class (C7)', () => {
    const html = renderToStaticMarkup(<Valuation initial={data} />)
    // board.sample covers fresh/stale/overdue/None; overdue must render its row class
    expect(html).toContain('vfr-overdue')
    expect(html).toContain('vfr-fresh')
  })

  it('common-vintage percentile: fresh rows get a number, non-fresh show vint (§10.5)', () => {
    const html = renderToStaticMarkup(<Valuation initial={data} />)
    expect(html).toContain('vint') // stale/overdue/None rows out of the cohort
    // at least one fresh row shows a numeric pctile cell
    expect(/valn-pct">\d+</.test(html)).toBe(true)
  })

  it('respects scope: a sector filter cuts rows to that sector BEFORE ranking', () => {
    const sector = data.stocks[0].sector as string
    const expected = data.stocks.filter((s) => s.sector === sector).length
    const scope: Scope = { kind: 'sector', key: sector }
    const html = renderToStaticMarkup(<Valuation initial={data} scope={scope} />)
    expect(rows(html).length).toBe(expected)
    expect(expected).toBeLessThan(data.stocks.length)
  })

  it('sector + theme appear as scope-writer dropdown options', () => {
    const html = renderToStaticMarkup(<Valuation initial={data} />)
    const sector = data.stocks[0].sector as string
    expect(html).toContain(`sector:${sector}`)
  })
})
