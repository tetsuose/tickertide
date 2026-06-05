import { describe, it, expect } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import ocean from '../lib/__fixtures__/ocean.sample.json'
import Ocean, { Tip } from './Ocean'
import type { OceanData, OceanStock, OceanPt, Scope } from '../types'
import {
  radiusFor, colorVar, quadrantVar, makeScales, withAlpha, drawOcean, nearestPoint,
  SECTOR_VAR, OCEAN_GEOM, type CanvasLike, type Palette, type DrawnPoint,
} from '../lib/ocean-draw'

// AC-M2.2 (ROADMAP) as a committed regression gate: the Ocean canvas renders the
// latest week's ≥500 points on the fixed RS×Val plane with √mktcap sizing and the
// three color modes. The real <canvas> never runs headlessly, so we test the pure
// draw lib (geometry / color / size) and drawOcean against a recording mock ctx,
// plus the component scaffold via SSR. Fixture: export/ocean.py on a 520-ticker
// synthetic DB (seed 7) -> 517 stocks (regenerate: make fixture-pipeline
// FIXTURE_ARGS="--tickers 520 --seed 7" && python export/ocean.py --out <here>).
const data = ocean as unknown as OceanData
const ALL: Scope = { kind: 'all', key: null }

// A mock 2D context recording the calls drawOcean makes. Any palette var resolves
// to a valid hex so withAlpha() parses; we assert structure, not exact colors.
function mockCtx() {
  const calls = { arc: [] as number[][], fillRect: 0, stroke: 0, clearRect: 0 }
  const ctx: CanvasLike & { calls: typeof calls } = {
    calls,
    fillStyle: '', strokeStyle: '', lineWidth: 0, globalAlpha: 1,
    clearRect: () => { calls.clearRect++ },
    fillRect: () => { calls.fillRect++ },
    beginPath: () => {},
    moveTo: () => {}, lineTo: () => {},
    arc: (x, y, r) => { calls.arc.push([x, y, r]) },
    fill: () => {}, stroke: () => { calls.stroke++ },
  }
  return ctx
}
const PAL: Palette = new Proxy({}, { get: () => '#2ec07a' })
const latest = data.n_weeks - 1

describe('Ocean draw lib (pure)', () => {
  it('radiusFor grows with √mktcap and clamps to [1.6, 11]', () => {
    // base 2.0 (UX contract jsx) -> formula min is 2.0; the 1.6 floor is a guard bound.
    expect(radiusFor(null)).toBeCloseTo(2.0)            // null -> 2 + √0
    expect(radiusFor(0)).toBeCloseTo(2.0)
    expect(radiusFor(1e9)).toBeCloseTo(2.34)            // $1B: 2 + √1·0.34
    expect(radiusFor(25e9)).toBeCloseTo(3.7)            // $25B: 2 + 5·0.34
    expect(radiusFor(1e16)).toBe(11)                    // huge -> clamp ceiling
    expect(radiusFor(-5)).toBeGreaterThanOrEqual(1.6)   // negative guarded -> >= floor
  })

  it('makeScales maps domain 0-100 to the plot box; y inverts so val=0 is the BOTTOM (cheap)', () => {
    const g = OCEAN_GEOM
    const { sx, sy, plotW, plotH } = makeScales(g)
    expect(sx(0)).toBe(g.pl)
    expect(sx(100)).toBeCloseTo(g.pl + plotW)
    expect(sy(0)).toBeCloseTo(g.pt + plotH)             // cheap at bottom
    expect(sy(100)).toBe(g.pt)                          // dear at top
    expect(sy(0)).toBeGreaterThan(sy(100))              // bottom=cheap orientation
  })

  it('quadrantVar: strong+cheap=lead, strong+dear=weak, weak+cheap=improving, weak+dear=dim', () => {
    expect(quadrantVar({ rs: 80, val: 20, ps: 1 })).toBe('--q-lead')
    expect(quadrantVar({ rs: 80, val: 80, ps: 1 })).toBe('--q-weak')
    expect(quadrantVar({ rs: 20, val: 20, ps: 1 })).toBe('--q-impr')
    expect(quadrantVar({ rs: 20, val: 80, ps: 1 })).toBe('--dim2')
  })

  it('colorVar resolves sector var; theme falls back when no active theme', () => {
    const pt: OceanPt = { rs: 60, val: 40, ps: 5 }
    const s = { ticker: 'X', sector: 'Information Technology', mktcap: 1e9, themes: [], pts: [pt] } as OceanStock
    expect(colorVar(s, pt, 'sector', null)).toBe('--sec-tech')
    expect(colorVar(s, pt, 'theme', null)).toBe('--dim2')      // no theme selected -> faded
    expect(colorVar(s, pt, 'quadrant', null)).toBe('--q-lead') // rs60 strong + val40 cheap (<50)
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

describe('AC-M2.2: drawOcean renders the latest week', () => {
  it('draws one point per stock with a non-null latest pt, and ≥500 of them', () => {
    const ctx = mockCtx()
    const drawn = drawOcean(ctx, { data, week: latest, colorBy: 'sector', activeTheme: null, scope: ALL, palette: PAL })
    const renderable = data.stocks.filter((s) => s.pts[latest]).length
    expect(ctx.calls.arc.length).toBe(renderable)
    expect(renderable).toBe(data.count)               // ocean.py invariant: all latest pts non-null
    expect(ctx.calls.arc.length).toBeGreaterThanOrEqual(500)
    expect(drawn.length).toBe(renderable)             // all in scope -> all returned for hit-testing
  })

  it('paints the static layer: clear + strong/cheap quadrant tint + crosshair', () => {
    const ctx = mockCtx()
    drawOcean(ctx, { data, week: latest, colorBy: 'quadrant', activeTheme: null, scope: ALL, palette: PAL })
    expect(ctx.calls.clearRect).toBe(1)
    expect(ctx.calls.fillRect).toBe(1)                // the bottom-right quadrant tint
    expect(ctx.calls.stroke).toBeGreaterThanOrEqual(1) // crosshair
  })

  it('points sit inside the plot box (domain 0-100 -> pixels)', () => {
    const ctx = mockCtx()
    drawOcean(ctx, { data, week: latest, colorBy: 'sector', activeTheme: null, scope: ALL, palette: PAL })
    const g = OCEAN_GEOM
    for (const [x, y] of ctx.calls.arc) {
      expect(x).toBeGreaterThanOrEqual(g.pl - 0.001)
      expect(x).toBeLessThanOrEqual(g.w - g.pr + 0.001)
      expect(y).toBeGreaterThanOrEqual(g.pt - 0.001)
      expect(y).toBeLessThanOrEqual(g.h - g.pb + 0.001)
    }
  })

  it('respects scope=sector: only in-sector points are non-faded (C10)', () => {
    const sector = data.stocks[0].sector as string
    const ctx = mockCtx()
    const drawn = drawOcean(ctx, {
      data, week: latest, colorBy: 'sector', activeTheme: null,
      scope: { kind: 'sector', key: sector }, palette: PAL,
    })
    const inSector = data.stocks.filter((s) => s.sector === sector && s.pts[latest]).length
    expect(drawn.length).toBe(inSector)               // only in-scope returned
    expect(drawn.length).toBeLessThan(data.count)     // others faded out
    expect(ctx.calls.arc.length).toBe(data.count)     // faded still drawn (as 1.2px dots)
  })
})

describe('AC-M2.2: Ocean component scaffold (SSR)', () => {
  const html = renderToStaticMarkup(<Ocean initial={data} scope={ALL} />)
  it('renders the canvas + 3 color-mode toggles + axis labels', () => {
    expect(html).toContain('<canvas')
    for (const m of ['sector', 'theme', 'quadrant']) expect(html).toContain(`>${m}</button>`)
    expect(html).toContain('RS percentile')
    expect(html).toContain('Valuation')
  })
  it('labels the latest week', () => {
    expect(html).toContain(`WEEK ${data.n_weeks}/${data.n_weeks}`)
    expect(html).toContain(data.weeks[latest])
  })
})

// AC-M2.3 (ROADMAP): manual WEEK scrubber (no autoplay — C2) moves the points;
// hover → nearest-neighbor tip(ticker/sector/RS/Val/P-S/mktcap/themes).
describe('AC-M2.3: scrubber + hover', () => {
  const PTS: DrawnPoint[] = [
    { ticker: 'A', px: 100, py: 100, r: 4 },
    { ticker: 'B', px: 300, py: 200, r: 6 },
  ]

  it('nearestPoint hits within ~r+5px, picks the closest, misses far away', () => {
    expect(nearestPoint(PTS, 101, 102)).toBe('A')          // on top of A
    expect(nearestPoint(PTS, 304, 203)).toBe('B')          // on top of B
    expect(nearestPoint(PTS, 800, 400)).toBe(null)         // empty space -> no tip
    expect(nearestPoint([], 1, 1)).toBe(null)              // nothing drawn
  })

  it('scrubbing the week moves points (different positions than the latest week)', () => {
    const c0 = mockCtx()
    drawOcean(c0, { data, week: 0, colorBy: 'sector', activeTheme: null, scope: ALL, palette: PAL })
    const cN = mockCtx()
    drawOcean(cN, { data, week: latest, colorBy: 'sector', activeTheme: null, scope: ALL, palette: PAL })
    const moved = c0.calls.arc.some(([x, y], i) => {
      const b = cN.calls.arc[i]
      return b && (Math.abs(x - b[0]) > 0.5 || Math.abs(y - b[1]) > 0.5)
    })
    expect(moved).toBe(true)
  })

  it('drawOcean adds a hover ring (one extra stroke) for the hovered point', () => {
    const base = mockCtx()
    drawOcean(base, { data, week: latest, colorBy: 'sector', activeTheme: null, scope: ALL, palette: PAL })
    const withHover = mockCtx()
    drawOcean(withHover, {
      data, week: latest, colorBy: 'sector', activeTheme: null, scope: ALL, palette: PAL,
      hover: data.stocks[0].ticker,
    })
    expect(withHover.calls.stroke).toBe(base.calls.stroke + 1)
  })

  it('Tip shows ticker / sector / RS / Val / P-S / mkt cap', () => {
    const s = data.stocks[0]
    const pt = s.pts[latest] as OceanPt
    const html = renderToStaticMarkup(<Tip stock={s} pt={pt} />)
    expect(html).toContain(s.ticker)
    if (s.sector) expect(html).toContain(s.sector)
    for (const label of ['RS pct', 'Val pct', 'P/S', 'Mkt cap']) expect(html).toContain(label)
    expect(html).toContain(pt.rs.toFixed(0))
  })

  it('renders a manual week range input (max = n_weeks-1, no autoplay)', () => {
    const html = renderToStaticMarkup(<Ocean initial={data} scope={ALL} />)
    expect(html).toContain('type="range"')
    expect(html).toContain(`max="${data.n_weeks - 1}"`)
    expect(html).toContain('week scrubber')
  })
})
