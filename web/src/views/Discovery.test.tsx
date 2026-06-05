import { describe, it, expect } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import board from '../lib/__fixtures__/board.sample.json'
import Discovery from './Discovery'
import EvidenceCard from '../components/EvidenceCard'
import { composite } from '../lib/composite'
import type { BoardData } from '../types'

// AC-M1 (PRD §14) as a committed regression gate: render Discovery + EvidenceCard
// from the real exported fixture (board.sample.json) via react-dom/server and
// assert the milestone's user-visible contract. No browser needed.
const data = board as unknown as BoardData
const order = (html: string) => [...html.matchAll(/ec-tk">\s*([A-Za-z0-9]+)/g)].map((m) => m[1])
const card = (i: number, k: number, defaultOpen = false) =>
  renderToStaticMarkup(
    <EvidenceCard stock={data.stocks[i]} weights={data.weights_default} score={composite(data.stocks[i].components, k)} defaultOpen={defaultOpen} />,
  )

describe('AC-M1: Discovery evidence-card board', () => {
  it('renders >=18 cards', () => {
    const html = renderToStaticMarkup(<Discovery initial={data} k={data.knob_default_k} />)
    expect(order(html).length).toBeGreaterThanOrEqual(18)
  })

  it('knob re-sorts the grid live (reliable vs early → different order)', () => {
    const o0 = order(renderToStaticMarkup(<Discovery initial={data} k={0} />))
    const o1 = order(renderToStaticMarkup(<Discovery initial={data} k={1} />))
    expect(o0.length).toBe(o1.length)
    expect(o0).not.toEqual(o1)
  })

  it('badge shows the composite recomputed at the current k (C9)', () => {
    const top = [...data.stocks].sort((a, b) => composite(b.components, 1) - composite(a.components, 1))[0]
    const html = renderToStaticMarkup(<Discovery initial={data} k={1} />)
    expect(html).toContain(`${composite(top.components, 1).toFixed(0)} <i>▾`)
  })

  it('card carries the 6 raw evidence fields', () => {
    const html = card(0, 0.5)
    for (const label of ['1M', '3M', '6M', 'from high', 'week', 'vol']) expect(html).toContain(label)
  })

  it('expanded badge reveals 5 components + weights (no black box)', () => {
    const html = card(0, 0.5, true)
    for (const c of ['RS', '52WH', 'TREND', 'VOL', 'ACCEL']) expect(html).toContain(c)
    expect(html).toContain('无黑箱')
    expect(html).toContain('%')
  })

  it('annotates d/d (day-over-day composite)', () => {
    const i = data.stocks.findIndex((s) => s.composite != null && s.composite_prev != null)
    expect(i).toBeGreaterThanOrEqual(0)
    expect(/[▲▼]/.test(card(i, 0.5))).toBe(true)
  })

  it('renders the mini-chart SVG with MA lines + 52w dashed line', () => {
    const html = card(0, 0.5)
    expect(html).toContain('<svg')
    expect(html).toContain('var(--ma50)')
    expect(html).toContain('stroke-dasharray')
  })
})

// AC-M2.4 (C10): Discovery respects the global scope — filter BEFORE sort (§9.3).
describe('AC-M2.4: Discovery respects global scope', () => {
  it('scope=sector keeps only that sector', () => {
    const sector = data.stocks.find((s) => s.sector)!.sector as string
    const expected = data.stocks.filter((s) => s.sector === sector).length
    const html = renderToStaticMarkup(
      <Discovery initial={data} k={0.5} scope={{ kind: 'sector', key: sector }} />,
    )
    expect(order(html).length).toBe(expected)
    expect(expected).toBeLessThan(data.stocks.length) // genuinely filtered
  })

  it('scope=pinned keeps only the pinned tickers', () => {
    const pins = [data.stocks[2].ticker, data.stocks[5].ticker]
    const html = renderToStaticMarkup(
      <Discovery initial={data} k={0.5} scope={{ kind: 'pinned', key: null }} pinned={pins} />,
    )
    expect(order(html).sort()).toEqual([...pins].sort())
  })

  it('scope=all (or unset) shows everything', () => {
    const html = renderToStaticMarkup(<Discovery initial={data} k={0.5} scope={{ kind: 'all', key: null }} />)
    expect(order(html).length).toBe(data.stocks.length)
  })
})
