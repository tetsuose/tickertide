// Ocean canvas drawing. Pure geometry / color / size helpers + a single
// drawOcean() that paints ONE animation frame onto a 2D context. Kept free of React and of
// the real canvas so the logic is unit-testable headlessly (inject a mock ctx + a fake
// palette). The surface is a steady-riser × Valuation SEA-LEVEL map (PRD §9.2, 2026-07-02
// spine pivot II):
//   y = rise_pct (0-100, the 10-day net-return cross-sectional percentile), with a fixed
//       sea level at 90 — a VISUAL reference line only. Above the line is highlighted,
//       below is darkened. candidate is NOT derived from y (cand ≠ y>=90).
//   x = raw trailing P/S TTM on a LOG scale (data-driven domain; NOT a percentile, §16).
// Points are sized by √mktcap, colored by sector/theme, faded by scope; candidates (the
// Risers candidate flag, read verbatim from the export's `cand` column — recall-first, C9)
// get a glow + bright ring. Play tweens positions between adjacent
// real EOD snapshots via interpolateOceanPoint — visual only; tooltip/state read the REAL
// snapshot, never an interpolated value.
//
// COLOR SoT: theme.css owns the hex values; JS holds only CSS-variable NAMES here (never
// raw hex). resolvePalette() reads their computed hex at runtime in the browser; tests pass
// a fake var→hex palette.
import type { OceanData, OceanStock, OceanDrawPt, Scope } from '../types'

// Plot box in logical px (canvas backs at 2x for retina). 880×470 with L/R/T/B insets:
// left for the rise_pct axis labels, bottom for the P/S log-axis labels.
export const OCEAN_GEOM = { w: 880, h: 470, pl: 46, pr: 18, pt: 16, pb: 40 } as const
export type Geom = typeof OCEAN_GEOM

// Past this many pins (a lasso pins a whole region for SCOPE, not for reading), drawOcean
// stops drawing a per-stock ticker label — the scope fade carries the selection, no
// text spaghetti (C2). Under the cap, each pin gets an emphasized dot + label.
export const PIN_LABEL_CAP = 8

// sector / theme only — the old rs/val `quadrant` mode is gone with the RS×Val axes (M8).
export type ColorMode = 'sector' | 'theme'

// Full GICS sector name -> CSS var (附录 C 11 sectors). universe.sector carries the full
// name; the canvas needs a concrete color so we resolve the var at draw time.
export const SECTOR_VAR: Record<string, string> = {
  'Information Technology': '--sec-tech',
  'Communication Services': '--sec-comm',
  'Consumer Discretionary': '--sec-disc',
  'Health Care': '--sec-hlth',
  Financials: '--sec-fin',
  Industrials: '--sec-indu',
  Energy: '--sec-nrg',
  'Consumer Staples': '--sec-stpl',
  Materials: '--sec-matl',
  Utilities: '--sec-util',
  'Real Estate': '--sec-re',
}

// Concept theme key -> CSS var (附录 C 8 themes).
export const THEME_VAR: Record<string, string> = {
  AI: '--th-ai', ROBO: '--th-robo', SPACE: '--th-space', OPTIC: '--th-optic',
  SEMI: '--th-semi', NUKE: '--th-nuke', CYBR: '--th-cybr', CLOUD: '--th-cloud',
}

const FALLBACK_VAR = '--dim2'

// Every var the canvas may need to resolve (deduped). --grn = the waterline + above-sea
// tint; --bg = below-sea darken + pin ring outline.
export const OCEAN_VARS: string[] = [
  ...new Set([
    ...Object.values(SECTOR_VAR), ...Object.values(THEME_VAR),
    '--grn', '--txt', '--dim', '--dim2', '--bg',
  ]),
]

export type Palette = Record<string, string>

/** Read every Ocean CSS var's computed hex off an element (browser only). */
export function resolvePalette(root: Element): Palette {
  const cs = getComputedStyle(root)
  const p: Palette = {}
  for (const v of OCEAN_VARS) p[v] = cs.getPropertyValue(v).trim()
  return p
}

/** clamp(2 + √(mktcap$B)·0.34, 1.6, 11) — radius grows with √market-cap (PRD §9.2). */
export function radiusFor(mktcapUSD: number | null): number {
  const b = Math.max(0, (mktcapUSD ?? 0) / 1e9)
  return Math.max(1.6, Math.min(11, 2.0 + Math.sqrt(b) * 0.34))
}

export function clamp(v: number, lo: number, hi: number): number {
  return v < lo ? lo : v > hi ? hi : v
}
export function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t
}
/** Interpolate in LOG space so motion along the log P/S axis is visually uniform. */
export function lerpLog(a: number, b: number, t: number): number {
  const la = Math.log10(Math.max(1e-9, a))
  const lb = Math.log10(Math.max(1e-9, b))
  return Math.pow(10, lerp(la, lb, t))
}

/** CSS-var name for a stock's fill in the given mode (pure; no hex). */
export function colorVar(s: OceanStock, mode: ColorMode, activeTheme: string | null): string {
  if (mode === 'theme') {
    const member = activeTheme != null && s.themes.some((t) => t.theme === activeTheme)
    return member ? (THEME_VAR[activeTheme as string] ?? FALLBACK_VAR) : FALLBACK_VAR
  }
  return (s.sector != null && SECTOR_VAR[s.sector]) || FALLBACK_VAR
}

/** Whether a stock is in the global scope (PRD §9.1.2). 'pinned' = in the pinned set. */
export function inScope(s: OceanStock, scope: Scope, pinned: string[] = []): boolean {
  if (scope.kind === 'sector') return s.sector === scope.key
  if (scope.kind === 'theme') return s.themes.some((t) => t.theme === scope.key)
  if (scope.kind === 'pinned') return pinned.includes(s.ticker)
  return true // 'all'
}

export interface Scales {
  sx: (ps: number) => number       // raw P/S -> px (log scale over x_domain)
  sy: (risePct: number) => number   // rise_pct -> px (split axis: 0 bottom, seaLevel mid, 100 top)
  plotW: number
  plotH: number
  seaY: number                     // px of the sea level (=== sy(seaLevel)) — the plot midpoint
}

/** x = log10 P/S mapped over [x_domain] -> plot width; y = rise_pct on a SPLIT (broken) axis:
 *  the sea level (90) sits at the plot's vertical MIDPOINT, so the narrow above-sea band
 *  [seaLevel,100] (the top-decile zone — the only rise_pct worth resolving finely) and the wide
 *  below-sea band [0,seaLevel] each own half the height — different px-per-pct on each side. */
export function makeScales(
  xDomain: readonly [number, number], seaLevel: number, g: Geom = OCEAN_GEOM,
): Scales {
  const plotW = g.w - g.pl - g.pr
  const plotH = g.h - g.pt - g.pb
  const lo = Math.max(1e-6, xDomain[0])
  const hi = Math.max(lo * 1.0001, xDomain[1])   // guard a degenerate [v,v] domain
  const l0 = Math.log10(lo)
  const l1 = Math.log10(hi)
  const sea = clamp(seaLevel, 0, 100)
  const midY = g.pt + plotH / 2                  // the waterline anchors the vertical midpoint
  const half = plotH / 2
  // piecewise-linear y: [0,sea]→lower half (bottom..mid), (sea,100]→upper half (mid..top).
  // anchors sy(0)=bottom, sy(sea)=mid, sy(100)=top hold, so the existing orientation invariants
  // and the above/below-sea hit-tests are preserved — only the px-per-pct slope differs per band.
  const sy = (v: number): number => {
    const vc = clamp(v, 0, 100)
    return vc <= sea
      ? g.pt + plotH - (sea <= 0 ? 1 : vc / sea) * half           // below sea → lower half
      : midY - (sea >= 100 ? 0 : (vc - sea) / (100 - sea)) * half // above sea → upper half
  }
  return {
    plotW,
    plotH,
    sx: (ps) => g.pl + clamp((Math.log10(Math.max(1e-6, ps)) - l0) / (l1 - l0), 0, 1) * plotW,
    sy,
    seaY: midY,
  }
}

/** "1-2-5" log gridline values within [lo,hi] (P/S axis ticks). */
export function logTicks(lo: number, hi: number): number[] {
  if (!(lo > 0) || !(hi > lo)) return []
  const out: number[] = []
  for (let k = Math.floor(Math.log10(lo)); k <= Math.ceil(Math.log10(hi)); k++) {
    for (const m of [1, 2, 5]) {
      const v = m * Math.pow(10, k)
      if (v >= lo && v <= hi) out.push(v)
    }
  }
  return out
}

/** Compact P/S tick label: "5", "0.5", "12". */
export function fmtPsTick(v: number): string {
  if (v >= 10) return String(Math.round(v))
  if (v >= 1) return v.toFixed(v % 1 === 0 ? 0 : 1)
  return v.toFixed(1)
}

/** "#rrggbb" + alpha → "rgba(...)". Falls back to a dim gray on a bad/missing hex. */
export function withAlpha(hex: string, a: number): string {
  const raw = (hex || '#56616f').replace('#', '')
  const full = raw.length === 3 ? raw.split('').map((c) => c + c).join('') : raw
  const n = parseInt(full, 16)
  if (Number.isNaN(n)) return `rgba(86,97,111,${a})`
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`
}

// --- play/scrub-animation interpolation (visual only) ---

// Scrub tween timing (slider drag / prev-next step): the dots glide from the current frame
// to the target date instead of hard-jumping. Duration scales with the distance in days and
// is clamped so a far slider jump still lands fast (the play loop keeps its own STEP_MS).
export const SCRUB_MS_PER_DAY = 150
export const SCRUB_MIN_MS = 180
export const SCRUB_MAX_MS = 600

/** Front-loaded ease for the scrub tween — starts fast so rapid retargets (slider drags)
 *  never feel stalled, settles gently on the target date. */
export function easeOutCubic(t: number): number {
  const u = 1 - clamp(t, 0, 1)
  return 1 - u * u * u
}

/** Tween duration for a scrub crossing `deltaDays` (fractional ok): per-day rate clamped
 *  to [SCRUB_MIN_MS, SCRUB_MAX_MS] so 1-day steps stay snappy and far jumps stay bounded. */
export function scrubDurationMs(deltaDays: number): number {
  return clamp(Math.abs(deltaDays) * SCRUB_MS_PER_DAY, SCRUB_MIN_MS, SCRUB_MAX_MS)
}

/** Reconstruct a stock's DRAW snapshot at date index i from the v3 columnar bulk, or null if
 *  there's no renderable position that day (ps or rise_pct missing). The candidate flag is
 *  read VERBATIM from the precomputed `cand` column (cand[i]===1 — compute's single source,
 *  C9; never re-derived from rise_pct); the riser evidence columns are not here (they live in
 *  OceanDetail, fetched lazily on hover). This is the single place the columnar arrays become
 *  a point. */
export function drawPtAt(s: OceanStock, i: number): OceanDrawPt | null {
  const ps = s.ps[i]
  const rise = s.rise_pct[i]
  if (ps == null || rise == null) return null
  return { ps, rise_pct: rise, candidate: s.cand[i] === 1 }
}

/** One animation frame for a stock: interpolated position (data space) + the REAL snapshot
 *  it reads draw state from + a fade alpha. position is lerped; `snap` is NEVER synthesized. */
export interface FramePoint {
  ps: number
  rise_pct: number
  snap: OceanDrawPt
  fade: number   // 0..1 — 1 fully present; <1 while fading in/out at a gap
}

/** Interpolate a stock's position between adjacent real EOD snapshots for the play tween.
 *  - both present: lerp x (log) + y; state comes from the NEAREST real snapshot (so the
 *    tooltip always shows a real snapshot, never a fabricated mid-value).
 *  - prev only (next missing): hold at prev, fade OUT (fade = 1 - phase).
 *  - next only (prev missing): hold at next, fade IN (fade = phase).
 *  - neither: null (not drawn). */
export function interpolateOceanPoint(
  prev: OceanDrawPt | null, next: OceanDrawPt | null, phase: number,
): FramePoint | null {
  const t = clamp(phase, 0, 1)
  if (prev && next) {
    return { ps: lerpLog(prev.ps, next.ps, t), rise_pct: lerp(prev.rise_pct, next.rise_pct, t), snap: t < 0.5 ? prev : next, fade: 1 }
  }
  if (prev) return { ps: prev.ps, rise_pct: prev.rise_pct, snap: prev, fade: 1 - t } // fade out
  if (next) return { ps: next.ps, rise_pct: next.rise_pct, snap: next, fade: t }     // fade in
  return null
}

// Minimal 2D-context surface drawOcean touches — CanvasRenderingContext2D satisfies it,
// and tests can pass a recording mock.
export interface CanvasLike {
  clearRect(x: number, y: number, w: number, h: number): void
  fillRect(x: number, y: number, w: number, h: number): void
  beginPath(): void
  moveTo(x: number, y: number): void
  lineTo(x: number, y: number): void
  arc(x: number, y: number, r: number, a0: number, a1: number): void
  closePath(): void
  fill(): void
  stroke(): void
  fillText(text: string, x: number, y: number): void
  setLineDash?(segments: number[]): void
  // widened to the DOM types so a real CanvasRenderingContext2D is assignable.
  fillStyle: string | CanvasGradient | CanvasPattern
  strokeStyle: string | CanvasGradient | CanvasPattern
  lineWidth: number
  globalAlpha: number
  font: string
}

/** A selection rectangle in logical px (lasso). */
export interface Rect {
  x0: number
  y0: number
  x1: number
  y1: number
}

export interface DrawOpts {
  data: OceanData
  dateIndex: number     // current EOD snapshot index into data.dates
  phase: number         // 0..1 tween between dateIndex and dateIndex+1 (play); 0 at rest
  colorBy: ColorMode
  activeTheme: string | null
  scope: Scope
  palette: Palette
  hover?: string | null
  pinned?: string[]
  lassoRect?: Rect | null
  geom?: Geom
}

/** On-screen position of a drawn (non-faded) point, for hover hit-testing. */
export interface DrawnPoint {
  ticker: string
  px: number
  py: number
  r: number
}

/** Paint the sea-level backdrop (above highlighted, below darkened, waterline at rise 90 +
 *  the rise_pct / P/S axis ticks) and this frame's points, then return the non-faded points'
 *  on-screen (interpolated) positions for hit-testing. In-scope / theme-member points draw
 *  bright above the sea, dimmer below; out-of-scope fade to a 1.2px dot (C10). Candidates
 *  (the read-only 连续上涨 flag) get a glow halo + bright ring. */
export function drawOcean(ctx: CanvasLike, o: DrawOpts): DrawnPoint[] {
  const g = o.geom ?? OCEAN_GEOM
  const seaLevel = o.data.axis?.sea_level ?? 90
  const { sx, sy, plotW, plotH, seaY } = makeScales(o.data.x_domain, seaLevel, g)
  ctx.clearRect(0, 0, g.w, g.h)

  const topY = g.pt
  const botY = g.pt + plotH
  // below-sea darken (rise_pct < 90): a translucent dark band.
  ctx.globalAlpha = 1
  ctx.fillStyle = withAlpha(o.palette['--bg'] || '#080b11', 0.35)
  ctx.fillRect(g.pl, seaY, plotW, botY - seaY)
  // above-sea highlight (rise_pct >= 90 = top decile, visual reference): a faint green wash.
  ctx.fillStyle = withAlpha(o.palette['--grn'], 0.06)
  ctx.fillRect(g.pl, topY, plotW, seaY - topY)

  // P/S log gridlines + bottom tick labels.
  ctx.strokeStyle = withAlpha(o.palette['--dim'], 0.35)
  ctx.lineWidth = 1
  ctx.fillStyle = o.palette['--dim'] || '#56616f'
  ctx.font = '10px IBM Plex Mono, monospace'
  for (const v of logTicks(o.data.x_domain[0], o.data.x_domain[1])) {
    const X = sx(v)
    ctx.beginPath()
    ctx.moveTo(X, topY)
    ctx.lineTo(X, botY)
    ctx.stroke()
    ctx.fillText(fmtPsTick(v), X - 6, botY + 14)
  }
  // rise_pct y ticks. 90 = the sea level (plot midpoint); 95 anchors the magnified above-sea
  // half so the expanded catch-zone band stays readable on the split axis.
  for (const v of [0, 50, seaLevel, 95, 100]) {
    ctx.fillStyle = v === seaLevel ? o.palette['--grn'] || '#2ec07a' : o.palette['--dim'] || '#56616f'
    ctx.fillText(String(v), g.pl - 24, sy(v) + 3)
  }

  // the waterline at rise_pct = 90.
  ctx.strokeStyle = withAlpha(o.palette['--grn'], 0.85)
  ctx.lineWidth = 1.5
  ctx.beginPath()
  ctx.moveTo(g.pl, seaY)
  ctx.lineTo(g.pl + plotW, seaY)
  ctx.stroke()
  ctx.globalAlpha = 1
  ctx.fillStyle = o.palette['--grn'] || '#2ec07a'
  ctx.font = '600 10px IBM Plex Mono, monospace'
  ctx.fillText(`sea level · rise ${seaLevel}`, g.pl + plotW - 110, seaY - 5)

  const lastDate = o.dateIndex >= o.data.dates.length - 1
  const ph = lastDate ? 0 : o.phase
  const drawn: DrawnPoint[] = []
  for (const s of o.data.stocks) {
    const prev = drawPtAt(s, o.dateIndex)
    const next = lastDate ? prev : drawPtAt(s, o.dateIndex + 1)
    const fp = interpolateOceanPoint(prev, next, ph)
    if (!fp) continue
    const member =
      o.colorBy === 'theme'
        ? o.activeTheme != null && s.themes.some((t) => t.theme === o.activeTheme)
        : true
    const faded = !inScope(s, o.scope, o.pinned) || !member
    const X = sx(fp.ps)
    const Y = sy(fp.rise_pct)
    const lit = fp.rise_pct >= seaLevel
    const r = radiusFor(s.mktcap)
    const fill = o.palette[colorVar(s, o.colorBy, o.activeTheme)] ?? o.palette['--dim2']

    if (faded) {
      ctx.globalAlpha = 0.06 * fp.fade
      ctx.fillStyle = fill
      ctx.beginPath()
      ctx.arc(X, Y, 1.2, 0, 7)
      ctx.fill()
      continue
    }

    // candidate (连续上涨候选, read-only flag): a glow halo behind the dot.
    if (fp.snap.candidate) {
      ctx.globalAlpha = 0.22 * fp.fade
      ctx.fillStyle = fill
      ctx.beginPath()
      ctx.arc(X, Y, r + 4, 0, 7)
      ctx.fill()
    }
    // the dot: bright above the sea, dimmer below.
    ctx.globalAlpha = (lit ? 0.92 : 0.5) * fp.fade
    ctx.fillStyle = fill
    ctx.beginPath()
    ctx.arc(X, Y, r, 0, 7)
    ctx.fill()
    // candidate bright ring on top.
    if (fp.snap.candidate) {
      ctx.globalAlpha = fp.fade
      ctx.strokeStyle = o.palette['--txt'] || '#e9eef5'
      ctx.lineWidth = 1.5
      ctx.beginPath()
      ctx.arc(X, Y, r + 2, 0, 7)
      ctx.stroke()
    }
    drawn.push({ ticker: s.ticker, px: X, py: Y, r })
  }

  // hover ring around the hovered (non-faded) point.
  if (o.hover) {
    const hp = drawn.find((p) => p.ticker === o.hover)
    if (hp) {
      ctx.globalAlpha = 1
      ctx.strokeStyle = o.palette['--txt'] || '#e9eef5'
      ctx.lineWidth = 1.5
      ctx.beginPath()
      ctx.arc(hp.px, hp.py, hp.r + 3, 0, 7)
      ctx.stroke()
    }
  }

  // pinned emphasis: an outlined dot per pin (+ ticker label under PIN_LABEL_CAP — a big
  // lasso is a SCOPE selection carried by the fade, not a reading set, C2). Uses the same
  // interpolated frame position so the marker tracks the play tween.
  if (o.pinned && o.pinned.length) {
    const labels = o.pinned.length <= PIN_LABEL_CAP
    const byTicker = new Map(o.data.stocks.map((s) => [s.ticker, s]))
    for (const tk of o.pinned) {
      const s = byTicker.get(tk)
      if (!s) continue
      const prev = drawPtAt(s, o.dateIndex)
      const next = lastDate ? prev : drawPtAt(s, o.dateIndex + 1)
      const fp = interpolateOceanPoint(prev, next, ph)
      if (!fp) continue
      const X = sx(fp.ps)
      const Y = sy(fp.rise_pct)
      const col = o.palette[colorVar(s, o.colorBy, o.activeTheme)] || o.palette['--dim2']
      ctx.globalAlpha = 1
      ctx.fillStyle = col
      ctx.beginPath()
      ctx.arc(X, Y, radiusFor(s.mktcap) + 1, 0, 7)
      ctx.fill()
      ctx.strokeStyle = o.palette['--bg'] || '#080b11'
      ctx.lineWidth = 1.5
      ctx.stroke()
      if (labels) {
        ctx.fillStyle = o.palette['--txt'] || '#e9eef5'
        ctx.font = '600 11px IBM Plex Mono, monospace'
        ctx.fillText(s.ticker, X + 8, Y - 7)
      }
    }
  }

  // lasso selection rectangle while dragging.
  if (o.lassoRect) {
    const { x0, y0, x1, y1 } = o.lassoRect
    ctx.globalAlpha = 1
    ctx.strokeStyle = o.palette['--txt'] || '#e9eef5'
    ctx.lineWidth = 1
    ctx.fillStyle = withAlpha(o.palette['--txt'] as string, 0.06)
    ctx.fillRect(Math.min(x0, x1), Math.min(y0, y1), Math.abs(x1 - x0), Math.abs(y1 - y0))
    ctx.beginPath()
    ctx.moveTo(x0, y0)
    ctx.lineTo(x1, y0)
    ctx.lineTo(x1, y1)
    ctx.lineTo(x0, y1)
    ctx.closePath()
    ctx.stroke()
  }

  ctx.globalAlpha = 1
  return drawn
}

/** Tickers whose drawn position falls inside the rect (lasso selection; pure). */
export function pointsInRect(points: DrawnPoint[], r: Rect): string[] {
  const xlo = Math.min(r.x0, r.x1)
  const xhi = Math.max(r.x0, r.x1)
  const ylo = Math.min(r.y0, r.y1)
  const yhi = Math.max(r.y0, r.y1)
  return points.filter((p) => p.px >= xlo && p.px <= xhi && p.py >= ylo && p.py <= yhi).map((p) => p.ticker)
}

/** Nearest drawn point to (lx,ly) in logical px, or null if none within ~r+5px (the
 *  hover/click hit test — linear scan, fine for 500-2000 points; PRD NFR-8). Hit-tests the
 *  CURRENT frame's interpolated positions (drawn[]), so hover tracks the play tween. */
export function nearestPoint(points: DrawnPoint[], lx: number, ly: number): string | null {
  let best: DrawnPoint | null = null
  let bd = Infinity
  for (const p of points) {
    const d = (p.px - lx) ** 2 + (p.py - ly) ** 2
    if (d < bd) {
      bd = d
      best = p
    }
  }
  return best && bd < (best.r + 5) ** 2 ? best.ticker : null
}
