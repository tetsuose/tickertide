// Pure SVG geometry for the Rotation multi-line + N=1 solo charts (no DOM; SSR-testable).
// Rotation (PRD §9.4) draws RS-Ratio as SVG paths — ~11-22 lines × ~52 weeks render
// crisply as DOM, no canvas (Occam; unlike Ocean's thousands of points). These functions
// compute scales, paths, end-label stacking, and N=1 slope segments. Colors are CSS-var
// NAMES (附录 C sector vars via ocean-draw); the SVG resolves var() itself, so no hex
// palette is needed here (that was a canvas concern). UX contract: docs/equity-monitor-v2.jsx
// RSRatioLines / SoloRSLine.
import { SECTOR_VAR, THEME_VAR } from './ocean-draw'

export interface Geom {
  W: number
  H: number
  padL: number
  padR: number
  padT: number
  padB: number
}

// Geometry from the UX-contract viewBoxes (jsx RSRatioLines / SoloRSLine).
export const MULTI: Geom = { W: 860, H: 350, padL: 38, padR: 120, padT: 14, padB: 26 }
export const SOLO: Geom = { W: 860, H: 300, padL: 44, padR: 66, padT: 18, padB: 28 }

export interface LineScale {
  lo: number
  hi: number
  X: (i: number, n: number) => number
  Y: (v: number) => number
}

function scaleOf(lo: number, hi: number, geom: Geom): LineScale {
  const { padL, padR, padT, padB, W, H } = geom
  return {
    lo,
    hi,
    X: (i, n) => padL + (n > 1 ? i / (n - 1) : 0) * (W - padL - padR),
    Y: (v) => padT + (H - padT - padB) * (1 - (v - lo) / (hi - lo)),
  }
}

/** y-scale over all series, clamped to bracket 100 (jsx: lo≤98.5, hi≥101.5, pad 8%). */
export function multiScale(seriesList: (number | null)[][], geom: Geom = MULTI): LineScale {
  let lo = Infinity
  let hi = -Infinity
  for (const s of seriesList) {
    for (const v of s) {
      if (v != null) {
        if (v < lo) lo = v
        if (v > hi) hi = v
      }
    }
  }
  if (!isFinite(lo) || !isFinite(hi)) {
    lo = 98.5
    hi = 101.5
  }
  lo = Math.min(lo, 98.5)
  hi = Math.max(hi, 101.5)
  const pad = (hi - lo) * 0.08
  return scaleOf(lo - pad, hi + pad, geom)
}

/** y-scale for one N=1 series (jsx SoloRSLine: lo≤99, hi≥101, pad 14%). */
export function soloScale(series: number[], geom: Geom = SOLO): LineScale {
  let lo = series.length ? Math.min(...series) : 99
  let hi = series.length ? Math.max(...series) : 101
  if (!isFinite(lo) || !isFinite(hi)) {
    lo = 99
    hi = 101
  }
  lo = Math.min(lo, 99)
  hi = Math.max(hi, 101)
  const pad = (hi - lo) * 0.14
  return scaleOf(lo - pad, hi + pad, geom)
}

/** SVG path for a series; null values break the line (no fabricated segments). */
export function linePath(series: (number | null)[], sc: LineScale): string {
  const n = series.length
  let d = ''
  let pen = false
  for (let i = 0; i < n; i++) {
    const v = series[i]
    if (v == null) {
      pen = false
      continue
    }
    d += (pen ? 'L' : 'M') + sc.X(i, n).toFixed(1) + ' ' + sc.Y(v).toFixed(1) + ' '
    pen = true
  }
  return d.trim()
}

/** Last non-null value of a series (the line's current level). */
export function lastNonNull(series: (number | null)[]): number | null {
  for (let i = series.length - 1; i >= 0; i--) if (series[i] != null) return series[i] as number
  return null
}

export interface EndLabel {
  key: string
  name: string
  colorVar: string
  v: number
  y: number
}

/** Right-edge labels stacked by last value, nudged apart so they don't overlap
 *  (jsx RSRatioLines: sort by y ascending, push down when the gap < `gap`). */
export function endLabels(
  lines: { key: string; name: string; colorVar: string; series: (number | null)[] }[],
  sc: LineScale,
  gap = 13,
): EndLabel[] {
  const ends = lines
    .map((l) => {
      const v = lastNonNull(l.series) ?? 100
      return { key: l.key, name: l.name, colorVar: l.colorVar, v, y: sc.Y(v) }
    })
    .sort((a, b) => a.y - b.y)
  for (let i = 1; i < ends.length; i++) {
    if (ends[i].y - ends[i - 1].y < gap) ends[i].y = ends[i - 1].y + gap
  }
  return ends
}

export interface SoloSeg {
  x1: number
  y1: number
  x2: number
  y2: number
  up: boolean
}

/** N=1 line split into colored segments; up = value ≥ value K weeks back (short-window
 *  slope, jsx SoloRSLine K=3): ↑ green strengthening, ↓ red weakening (= momentum). */
export function soloSegments(series: number[], sc: LineScale, K = 3): SoloSeg[] {
  const n = series.length
  const segs: SoloSeg[] = []
  for (let i = 1; i < n; i++) {
    const a = series[Math.max(0, i - K)]
    segs.push({
      x1: sc.X(i - 1, n),
      y1: sc.Y(series[i - 1]),
      x2: sc.X(i, n),
      y2: sc.Y(series[i]),
      up: series[i] >= a,
    })
  }
  return segs
}

/** Integer y-grid ticks within [lo,hi] that are multiples of `step` (RSRatioLines
 *  brackets 100 with even ticks). */
export function gridTicks(sc: LineScale, step = 2): number[] {
  const out: number[] = []
  for (let t = Math.ceil(sc.lo); t <= Math.floor(sc.hi); t++) if (t % step === 0) out.push(t)
  return out
}

/** CSS-var name for a bucket's line color: GICS sector name -> SECTOR_VAR, theme key ->
 *  THEME_VAR (附录 C; sector names and theme keys don't collide). Fallback --dim2. */
export function bucketColorVar(bucket: string): string {
  return SECTOR_VAR[bucket] ?? THEME_VAR[bucket] ?? '--dim2'
}
