import { describe, it, expect } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import ocean from '../lib/__fixtures__/ocean.sample.json'
import Ocean, { Tip } from './Ocean'
import type { OceanData, OceanStock, OceanDrawPt, OceanDetail, ThemeTag, Scope } from '../types'
import {
  radiusFor, colorVar, makeScales, withAlpha, logTicks, fmtPsTick, lerp, lerpLog, clamp,
  interpolateOceanPoint, drawPtAt, drawOcean, nearestPoint, pointsInRect, inScope, SECTOR_VAR,
  OCEAN_GEOM, type CanvasLike, type Palette, type DrawnPoint, type DrawOpts,
} from '../lib/ocean-draw'

// AC-M8: the Ocean canvas is an Ignition × Valuation SEA-LEVEL map — y = ign_pct (0-100,
// sea level at 90), x = raw P/S on a LOG axis — scrubbed by a date slider with smooth play
// interpolation between real EOD snapshots. The real <canvas> never runs headlessly, so we
// test the pure draw lib (geometry / color / size / interpolation) + drawOcean against a
// recording mock ctx, plus the component scaffold via SSR. Fixture: export/ocean.py (schema v3,
// columnar draw fields) on a 520-ticker synthetic DB (seed 7) (regenerate: make fixture-pipeline
// FIXTURE_ARGS="--tickers 520 --seed 7" && python export/ocean.py --days 4 --out <here> &&
// rm -rf <here-dir>/ocean). The nine hover fields live in the lazy OceanDetail, built inline here.
const data = ocean as unknown as OceanData
const ALL: Scope = { kind: 'all', key: null }
const latest = data.dates.length - 1

// A mock 2D context recording the calls drawOcean makes.
function mockCtx() {
  const calls = { arc: [] as number[][], fillRect: 0, stroke: 0, clearRect: 0, text: [] as string[] }
  const ctx: CanvasLike & { calls: typeof calls } = {
    calls,
    fillStyle: '', strokeStyle: '', lineWidth: 0, globalAlpha: 1, font: '',
    clearRect: () => { calls.clearRect++ },
    fillRect: () => { calls.fillRect++ },
    beginPath: () => {},
    moveTo: () => {}, lineTo: () => {},
    arc: (x, y, r) => { calls.arc.push([x, y, r]) },
    closePath: () => {},
    fill: () => {}, stroke: () => { calls.stroke++ },
    fillText: (t: string) => { calls.text.push(t) },
  }
  return ctx
}
const PAL: Palette = new Proxy({}, { get: () => '#2ec07a' })
const base = (over: Partial<DrawOpts> = {}): DrawOpts => ({
  data, dateIndex: latest, phase: 0, colorBy: 'sector', activeTheme: null, scope: ALL, palette: PAL, ...over,
})

// a tiny hand-built dataset for isolated draw assertions (candidate glow etc.). v3 stocks are
// COLUMNAR — mkStock turns a list of per-day draw pts (or nulls) into ps/ign_pct/cand arrays.
function synth(stocks: OceanStock[], xDomain: [number, number] = [1, 100]): OceanData {
  return {
    schema_version: 3, as_of_date: '2026-06-05',
    axis: { x_metric: 'ps', x_scale: 'log', y_metric: 'ign_pct', sea_level: 90 },
    dates: ['2026-06-04', '2026-06-05'], x_domain: xDomain, count: stocks.length, stocks,
  }
}
function mkPt(over: Partial<OceanDrawPt> = {}): OceanDrawPt {
  return { ps: 5, ign_pct: 50, candidate: false, ...over }
}
function mkStock(
  ticker: string, sector: string, mktcap: number,
  days: (OceanDrawPt | null)[], themes: ThemeTag[] = [],
): OceanStock {
  return {
    ticker, sector, mktcap, themes,
    ps: days.map((d) => (d ? d.ps : null)),
    ign_pct: days.map((d) => (d ? d.ign_pct : null)),
    cand: days.map((d) => (d && d.candidate ? 1 : 0)),
  }
}
// the lazy per-stock hover detail (nine columnar fields, index-aligned to dates 0..di).
function mkDetail(di: number, over: Partial<OceanDetail> = {}): OceanDetail {
  const n = di + 1
  const num = (v: number) => Array<number | null>(n).fill(v)
  return {
    schema_version: 3, ticker: 'X', n,
    ignition: num(40), ign_persist_days: num(3), evs: num(5), pe: num(20),
    ev_ebitda: num(12), ret_10d: num(0.01), ret_1m: num(0.03), vol_mult: num(1.1),
    freshness: Array<'fresh' | null>(n).fill('fresh'),
    ...over,
  }
}

describe('Ocean draw lib (pure)', () => {
  it('radiusFor grows with √mktcap and clamps to [1.6, 11]', () => {
    expect(radiusFor(null)).toBeCloseTo(2.0)
    expect(radiusFor(1e9)).toBeCloseTo(2.34)
    expect(radiusFor(25e9)).toBeCloseTo(3.7)
    expect(radiusFor(1e16)).toBe(11)
    expect(radiusFor(-5)).toBeGreaterThanOrEqual(1.6)
  })

  it('makeScales: y inverts (ign 0 at bottom, 100 top) and the sea level sits at ign 90', () => {
    const g = OCEAN_GEOM
    const sc = makeScales(data.x_domain, 90, g)
    expect(sc.sy(0)).toBeCloseTo(g.pt + sc.plotH)        // ign 0 at bottom
    expect(sc.sy(100)).toBe(g.pt)                         // ign 100 at top
    expect(sc.sy(0)).toBeGreaterThan(sc.sy(100))          // bottom..top orientation
    expect(sc.seaY).toBeCloseTo(sc.sy(90))                // sea level === sy(90)
    expect(sc.sy(100)).toBeLessThan(sc.seaY)              // above the line is higher up
    expect(sc.seaY).toBeLessThan(sc.sy(0))
  })

  it('makeScales: split y-axis puts the sea level at the vertical midpoint, magnifying the above-sea band', () => {
    const g = OCEAN_GEOM
    const sc = makeScales(data.x_domain, 90, g)
    const mid = g.pt + sc.plotH / 2
    expect(sc.seaY).toBeCloseTo(mid)                       // waterline anchors the plot midpoint
    expect(sc.sy(90)).toBeCloseTo(mid)                     // sy(seaLevel) === seaY
    expect(sc.sy(45)).toBeCloseTo(g.pt + sc.plotH * 0.75)  // below-sea [0,90] owns the lower half
    expect(sc.sy(95)).toBeCloseTo(g.pt + sc.plotH * 0.25)  // above-sea [90,100] owns the upper half
    // the upper band is magnified: 5 ign_pct above the line span more px than 5 below it.
    expect(sc.sy(90) - sc.sy(95)).toBeGreaterThan(sc.sy(45) - sc.sy(50))
  })

  it('makeScales: P/S x is a monotone LOG scale over x_domain', () => {
    const g = OCEAN_GEOM
    const sc = makeScales([2, 20], 90, g)
    expect(sc.sx(2)).toBeCloseTo(g.pl)                    // domain lo -> left edge
    expect(sc.sx(20)).toBeCloseTo(g.pl + sc.plotW)        // domain hi -> right edge
    expect(sc.sx(2)).toBeLessThan(sc.sx(6))               // monotone increasing
    expect(sc.sx(6)).toBeLessThan(sc.sx(20))
    // log midpoint: √(2·20) maps to the pixel midpoint (linear in log space).
    expect(sc.sx(Math.sqrt(40))).toBeCloseTo(g.pl + sc.plotW / 2, 1)
  })

  it('logTicks gives 1-2-5 ticks within the domain; fmtPsTick formats them', () => {
    expect(logTicks(2, 20)).toEqual([2, 5, 10, 20])
    expect(logTicks(0.5, 3)).toEqual([0.5, 1, 2])
    expect(fmtPsTick(5)).toBe('5')
    expect(fmtPsTick(0.5)).toBe('0.5')
    expect(fmtPsTick(12.3)).toBe('12')
  })

  it('lerp / lerpLog / clamp', () => {
    expect(lerp(0, 10, 0.5)).toBe(5)
    expect(lerpLog(1, 100, 0.5)).toBeCloseTo(10)          // geometric midpoint
    expect(clamp(5, 0, 3)).toBe(3)
    expect(clamp(-1, 0, 3)).toBe(0)
  })

  it('colorVar resolves sector var; theme falls back when no active theme', () => {
    const s = { ticker: 'X', sector: 'Information Technology', mktcap: 1e9, themes: [], ps: [], ign_pct: [], cand: [] } as OceanStock
    expect(colorVar(s, 'sector', null)).toBe('--sec-tech')
    expect(colorVar(s, 'theme', null)).toBe('--dim2')
  })

  it('withAlpha turns a hex into rgba and survives a bad hex', () => {
    expect(withAlpha('#2ec07a', 0.5)).toBe('rgba(46,192,122,0.5)')
    expect(withAlpha('', 0.2)).toContain('rgba(')
  })

  it('every fixture sector is a known GICS name (no fallback in sector mode)', () => {
    const unknown = data.stocks.filter((s) => s.sector && !SECTOR_VAR[s.sector])
    expect(unknown).toEqual([])
  })
})

// AC-M8 v3: the bulk is COLUMNAR draw-only; drawPtAt rebuilds a point, hover detail is lazy.
describe('AC-M8 v3: columnar draw fields + lazy hover detail', () => {
  it('drawPtAt reconstructs ps/ign_pct/candidate from the columns; null on a gap day', () => {
    const s = mkStock('A', 'Energy', 1e9, [null, mkPt({ ps: 7, ign_pct: 95, candidate: true })])
    expect(drawPtAt(s, 0)).toBeNull()                              // null day (no position)
    expect(drawPtAt(s, 1)).toEqual({ ps: 7, ign_pct: 95, candidate: true })
  })

  it('Tip renders the 3 draw fields immediately and a `…` skeleton until detail loads', () => {
    const s = data.stocks[0]
    const draw = drawPtAt(s, latest)!
    const loading = renderToStaticMarkup(<Tip stock={s} draw={draw} detail={null} di={latest} />)
    expect(loading).toContain(draw.ign_pct.toFixed(0))            // ign_pct comes from the bulk
    expect(loading).toContain(draw.ps.toFixed(1))                 // P/S comes from the bulk
    expect(loading).toContain('…')                                // EV/S etc. still loading
    // once the detail lands, the evidence values render (no skeleton).
    const loaded = renderToStaticMarkup(<Tip stock={s} draw={draw} detail={mkDetail(latest)} di={latest} />)
    expect(loaded).toContain('5.0')                               // EV/S from the loaded detail
    expect(loaded).not.toContain('…')
  })
})

// AC-M8: interpolateOceanPoint — visual tween between real snapshots; state is never faked.
describe('AC-M8: play interpolation', () => {
  const a = mkPt({ ps: 2, ign_pct: 40 })
  const b = mkPt({ ps: 8, ign_pct: 95, candidate: true })

  it('both present: lerps x (log) + y; snap is the NEAREST real snapshot (never synthesized)', () => {
    const mid = interpolateOceanPoint(a, b, 0.5)!
    expect(mid.ps).toBeCloseTo(lerpLog(2, 8, 0.5))        // log-space lerp of x
    expect(mid.ign_pct).toBeCloseTo(67.5)                 // linear lerp of y
    expect(mid.fade).toBe(1)
    expect(interpolateOceanPoint(a, b, 0.25)!.snap).toBe(a) // nearer prev
    expect(interpolateOceanPoint(a, b, 0.75)!.snap).toBe(b) // nearer next
    // the interpolated x stays between the two real snapshots
    expect(mid.ps).toBeGreaterThan(2)
    expect(mid.ps).toBeLessThan(8)
  })

  it('prev present, next missing → fade OUT (held at prev)', () => {
    const fp = interpolateOceanPoint(a, null, 0.3)!
    expect(fp.snap).toBe(a)
    expect(fp.ps).toBe(2)
    expect(fp.fade).toBeCloseTo(0.7)                      // 1 - phase
  })

  it('prev missing, next present → fade IN (held at next)', () => {
    const fp = interpolateOceanPoint(null, b, 0.3)!
    expect(fp.snap).toBe(b)
    expect(fp.ign_pct).toBe(95)
    expect(fp.fade).toBeCloseTo(0.3)                      // phase
  })

  it('neither present → not drawn', () => {
    expect(interpolateOceanPoint(null, null, 0.5)).toBeNull()
  })
})

describe('AC-M8: drawOcean paints the sea-level map', () => {
  it('draws the backdrop (clear + below-sea darken + above-sea wash) and the waterline', () => {
    const ctx = mockCtx()
    drawOcean(ctx, base())
    expect(ctx.calls.clearRect).toBe(1)
    expect(ctx.calls.fillRect).toBeGreaterThanOrEqual(2)  // below-sea + above-sea bands
    expect(ctx.calls.stroke).toBeGreaterThanOrEqual(1)    // gridlines + waterline
    expect(ctx.calls.text.some((t) => t.includes('sea level'))).toBe(true)
  })

  it('returns one drawn point per stock with a non-null latest pt, and ≥500 of them', () => {
    const ctx = mockCtx()
    const drawn = drawOcean(ctx, base())
    const renderable = data.stocks.filter((s) => drawPtAt(s, latest)).length
    expect(renderable).toBe(data.count)                  // ocean.py invariant: all latest pts non-null
    expect(drawn.length).toBe(renderable)                // all in scope -> all returned for hit-testing
    expect(drawn.length).toBeGreaterThanOrEqual(500)
  })

  it('points sit inside the plot box', () => {
    const ctx = mockCtx()
    const drawn = drawOcean(ctx, base())
    const g = OCEAN_GEOM
    for (const p of drawn) {
      expect(p.px).toBeGreaterThanOrEqual(g.pl - 0.001)
      expect(p.px).toBeLessThanOrEqual(g.w - g.pr + 0.001)
      expect(p.py).toBeGreaterThanOrEqual(g.pt - 0.001)
      expect(p.py).toBeLessThanOrEqual(g.h - g.pb + 0.001)
    }
  })

  it('a candidate point is highlighted with a glow halo + bright ring (extra arcs + stroke)', () => {
    const xs: [number, number] = [1, 100]
    const plain = synth([mkStock('A', 'Energy', 1e9, [null, mkPt({ ign_pct: 95, candidate: false })])], xs)
    const cand = synth([mkStock('A', 'Energy', 1e9, [null, mkPt({ ign_pct: 95, candidate: true })])], xs)
    const cp = mockCtx(); drawOcean(cp, base({ data: plain, dateIndex: 1 }))
    const cc = mockCtx(); drawOcean(cc, base({ data: cand, dateIndex: 1 }))
    expect(cc.calls.arc.length).toBeGreaterThan(cp.calls.arc.length)   // glow + ring add arcs
    expect(cc.calls.stroke).toBeGreaterThan(cp.calls.stroke)           // the bright ring strokes
  })

  it('a sea-level y placement: an ign_pct=95 point is above the waterline, ign_pct=50 below', () => {
    const xs: [number, number] = [1, 100]
    const d = synth([
      mkStock('HI', 'Energy', 1e9, [null, mkPt({ ign_pct: 95 })]),
      mkStock('LO', 'Energy', 1e9, [null, mkPt({ ign_pct: 50 })]),
    ], xs)
    const drawn = drawOcean(mockCtx(), base({ data: d, dateIndex: 1 }))
    const sc = makeScales(xs, 90)
    const hi = drawn.find((p) => p.ticker === 'HI')!
    const lo = drawn.find((p) => p.ticker === 'LO')!
    expect(hi.py).toBeLessThan(sc.seaY)                  // above sea
    expect(lo.py).toBeGreaterThan(sc.seaY)               // below sea
  })

  it('scrubbing the date moves points', () => {
    const d0 = drawOcean(mockCtx(), base({ dateIndex: 0 }))
    const dN = drawOcean(mockCtx(), base({ dateIndex: latest }))
    const byT = new Map(dN.map((p) => [p.ticker, p]))
    const moved = d0.some((p) => {
      const q = byT.get(p.ticker)
      return q && (Math.abs(p.px - q.px) > 0.5 || Math.abs(p.py - q.py) > 0.5)
    })
    expect(moved).toBe(true)
  })

  it('respects scope=sector: only in-sector points are non-faded (C10)', () => {
    const sector = data.stocks[0].sector as string
    const drawn = drawOcean(mockCtx(), base({ scope: { kind: 'sector', key: sector } }))
    const inSector = data.stocks.filter((s) => s.sector === sector && drawPtAt(s, latest)).length
    expect(drawn.length).toBe(inSector)                  // only in-scope returned
    expect(drawn.length).toBeLessThan(data.count)        // others faded out
  })

  it('adds a hover ring (one extra stroke) for the hovered point', () => {
    const b0 = mockCtx(); drawOcean(b0, base())
    const bh = mockCtx(); drawOcean(bh, base({ hover: data.stocks[0].ticker }))
    expect(bh.calls.stroke).toBe(b0.calls.stroke + 1)
  })
})

// hit-testing + pin/lasso scope (C10 — Ocean is the first scope writer).
describe('AC-M8: hit-testing + pin/lasso scope', () => {
  const PTS: DrawnPoint[] = [
    { ticker: 'A', px: 100, py: 100, r: 4 },
    { ticker: 'B', px: 300, py: 200, r: 6 },
    { ticker: 'C', px: 700, py: 400, r: 6 },
  ]

  it('nearestPoint hits within ~r+5px, picks the closest, misses far away', () => {
    expect(nearestPoint(PTS, 101, 102)).toBe('A')
    expect(nearestPoint(PTS, 304, 203)).toBe('B')
    expect(nearestPoint(PTS, 800, 460)).toBe(null)
    expect(nearestPoint([], 1, 1)).toBe(null)
  })

  it('pointsInRect selects only enclosed tickers (and handles an inverted drag)', () => {
    expect(pointsInRect(PTS, { x0: 50, y0: 50, x1: 350, y1: 250 }).sort()).toEqual(['A', 'B'])
    expect(pointsInRect(PTS, { x0: 350, y0: 250, x1: 50, y1: 50 }).sort()).toEqual(['A', 'B'])
    expect(pointsInRect(PTS, { x0: 600, y0: 350, x1: 800, y1: 450 })).toEqual(['C'])
  })

  it("inScope('pinned') is membership in the pinned set", () => {
    const s = data.stocks[0]
    expect(inScope(s, { kind: 'pinned', key: null }, [s.ticker])).toBe(true)
    expect(inScope(s, { kind: 'pinned', key: null }, ['ZZZ'])).toBe(false)
    expect(inScope(s, { kind: 'all', key: null }, [])).toBe(true)
  })

  it('a pinned stock under the label cap gets an emphasized dot + ticker label', () => {
    const tk = data.stocks[0].ticker
    const b0 = mockCtx(); drawOcean(b0, base())
    const bp = mockCtx(); drawOcean(bp, base({ pinned: [tk] }))
    expect(bp.calls.text).toContain(tk)                  // ticker label on the pin
    expect(b0.calls.text).not.toContain(tk)
  })

  it('drawing a lasso rect adds a selection rectangle (fillRect + stroke)', () => {
    const b0 = mockCtx(); drawOcean(b0, base())
    const bl = mockCtx(); drawOcean(bl, base({ lassoRect: { x0: 100, y0: 100, x1: 300, y1: 250 } }))
    expect(bl.calls.fillRect).toBe(b0.calls.fillRect + 1)
    expect(bl.calls.stroke).toBe(b0.calls.stroke + 1)
  })
})

describe('AC-M8: Ocean component scaffold (SSR)', () => {
  const html = renderToStaticMarkup(<Ocean initial={data} scope={ALL} />)
  it('renders the canvas + color-mode toggles + the ignition/P-S axis labels', () => {
    expect(html).toContain('<canvas')
    for (const m of ['sector', 'theme']) expect(html).toContain(`>${m}</button>`)
    expect(html).toContain('ign_pct')
    expect(html).toContain('P/S')
  })
  it('renders a date slider (max = dates-1) + a play button, opening on the latest EOD', () => {
    expect(html).toContain('type="range"')
    expect(html).toContain(`max="${data.dates.length - 1}"`)
    expect(html).toContain('date slider')
    expect(html).toContain('▶')                          // play control
    expect(html).toContain('latest EOD')
    expect(html).toContain(data.dates[latest])
  })
  it('accepts an onOpen prop and documents the right-click → Stock affordance', () => {
    const h = renderToStaticMarkup(<Ocean initial={data} scope={ALL} onOpen={() => {}} />)
    expect(h).toContain('右键')                            // foot documents right-click → open in Stock
  })
})

describe('AC-M8: Tip shows ignition + valuation evidence (not RS/Val pct)', () => {
  const s = data.stocks[0]
  const draw = drawPtAt(s, latest)!
  const html = renderToStaticMarkup(<Tip stock={s} draw={draw} detail={mkDetail(latest)} di={latest} />)
  it('shows ticker + ignition + the valuation multiples + freshness', () => {
    expect(html).toContain(s.ticker)
    for (const label of ['ign_pct', '持续点火', 'P/S', 'EV/S', 'P/E', 'EV/EBITDA', 'vol surge', 'val freshness'])
      expect(html).toContain(label)
    expect(html).toContain(draw.ign_pct.toFixed(0))
  })
  it('no longer shows the old RS percentile / Val percentile rows', () => {
    expect(html).not.toContain('RS pct')
    expect(html).not.toContain('Val pct')
  })
})
