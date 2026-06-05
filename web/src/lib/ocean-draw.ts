// Ocean canvas drawing (M2.2). Pure geometry / color / size helpers + a single
// drawOcean() that paints one weekly snapshot onto a 2D context. Kept free of React
// and of the real canvas so the logic is unit-testable headlessly (inject a mock
// ctx + a fake palette). PRD §9.2 (fixed RS×Val axes, bottom=cheap), 附录 C (colors).
//
// COLOR SoT: theme.css owns the hex values; JS holds only CSS-variable NAMES here
// (never raw hex — matching the theme.css convention). resolvePalette() reads their
// computed hex at runtime in the browser; tests pass a fake var→hex palette.
import type { OceanData, OceanStock, OceanPt, Scope } from '../types'

// Plot box in logical px (canvas backs at 2x for retina). From the UX contract
// (docs/equity-monitor-v2.jsx Ocean): 880×470 with L/R/T/B insets; domain 0-100.
export const OCEAN_GEOM = { w: 880, h: 470, pl: 46, pr: 18, pt: 16, pb: 40 } as const
export type Geom = typeof OCEAN_GEOM

export type ColorMode = 'sector' | 'theme' | 'quadrant'

// Full GICS sector name -> CSS var (附录 C 11 sectors). universe.sector carries the
// full name; the canvas needs a concrete color so we resolve the var at draw time.
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

// Concept theme key -> CSS var (附录 C 8 themes). Empty in data until M4.
export const THEME_VAR: Record<string, string> = {
  AI: '--th-ai', ROBO: '--th-robo', SPACE: '--th-space', OPTIC: '--th-optic',
  SEMI: '--th-semi', NUKE: '--th-nuke', CYBR: '--th-cybr', CLOUD: '--th-cloud',
}

const FALLBACK_VAR = '--dim2'

// Every var the canvas may need to resolve (deduped).
export const OCEAN_VARS: string[] = [
  ...new Set([
    ...Object.values(SECTOR_VAR), ...Object.values(THEME_VAR),
    '--q-lead', '--q-weak', '--q-impr', '--dim2', '--dim', '--grn', '--txt',
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

/** Ocean quadrant var: strong(rs≥50)+cheap(val<50)=lead, +expensive=weak,
 *  weak+cheap=improving, weak+expensive=dim (matches the UX contract). */
export function quadrantVar(pt: OceanPt): string {
  const strong = pt.rs >= 50
  const cheap = pt.val < 50
  return strong ? (cheap ? '--q-lead' : '--q-weak') : (cheap ? '--q-impr' : '--dim2')
}

/** CSS-var name for a stock's fill in the given mode (pure; no hex). */
export function colorVar(s: OceanStock, pt: OceanPt, mode: ColorMode, activeTheme: string | null): string {
  if (mode === 'quadrant') return quadrantVar(pt)
  if (mode === 'theme') {
    const member = activeTheme != null && s.themes.some((t) => t.theme === activeTheme)
    return member ? (THEME_VAR[activeTheme as string] ?? FALLBACK_VAR) : FALLBACK_VAR
  }
  return (s.sector != null && SECTOR_VAR[s.sector]) || FALLBACK_VAR
}

/** Whether a stock is in the global scope (PRD §9.1.2). 'pinned' is caller-handled. */
export function inScope(s: OceanStock, scope: Scope): boolean {
  if (scope.kind === 'sector') return s.sector === scope.key
  if (scope.kind === 'theme') return s.themes.some((t) => t.theme === scope.key)
  return true // 'all' | 'pinned'
}

export interface Scales {
  sx: (v: number) => number
  sy: (v: number) => number
  plotW: number
  plotH: number
}

/** Domain 0-100 → pixel. sy inverts so val=0 is the BOTTOM (cheap), 100 the top. */
export function makeScales(g: Geom = OCEAN_GEOM): Scales {
  const plotW = g.w - g.pl - g.pr
  const plotH = g.h - g.pt - g.pb
  return {
    plotW,
    plotH,
    sx: (v) => g.pl + (v / 100) * plotW,
    sy: (v) => g.pt + plotH - (v / 100) * plotH,
  }
}

/** "#rrggbb" + alpha → "rgba(...)". Falls back to a dim gray on a bad/missing hex. */
export function withAlpha(hex: string, a: number): string {
  const raw = (hex || '#56616f').replace('#', '')
  const full = raw.length === 3 ? raw.split('').map((c) => c + c).join('') : raw
  const n = parseInt(full, 16)
  if (Number.isNaN(n)) return `rgba(86,97,111,${a})`
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`
}

// Minimal 2D-context surface drawOcean touches — CanvasRenderingContext2D satisfies
// it, and tests can pass a recording mock.
export interface CanvasLike {
  clearRect(x: number, y: number, w: number, h: number): void
  fillRect(x: number, y: number, w: number, h: number): void
  beginPath(): void
  moveTo(x: number, y: number): void
  lineTo(x: number, y: number): void
  arc(x: number, y: number, r: number, a0: number, a1: number): void
  fill(): void
  stroke(): void
  // widened to the DOM types so a real CanvasRenderingContext2D is assignable
  // (we only ever assign strings); a mock just sets them to strings too.
  fillStyle: string | CanvasGradient | CanvasPattern
  strokeStyle: string | CanvasGradient | CanvasPattern
  lineWidth: number
  globalAlpha: number
}

export interface DrawOpts {
  data: OceanData
  week: number
  colorBy: ColorMode
  activeTheme: string | null
  scope: Scope
  palette: Palette
  hover?: string | null
  geom?: Geom
}

/** On-screen position of a drawn (non-faded) point, for hover hit-testing (M2.3). */
export interface DrawnPoint {
  ticker: string
  px: number
  py: number
  r: number
}

/** Paint the static layer (strong+cheap quadrant tint + (50,50) crosshair) and the
 *  `week`'s points; return the non-faded points' positions for hit-testing. In-scope
 *  / theme-member points draw at full radius; others fade to a 1.2px dot (C10). */
export function drawOcean(ctx: CanvasLike, o: DrawOpts): DrawnPoint[] {
  const g = o.geom ?? OCEAN_GEOM
  const { sx, sy, plotW, plotH } = makeScales(g)
  ctx.clearRect(0, 0, g.w, g.h)

  const cx = sx(50)
  const cy = sy(50)
  // strong+cheap quadrant tint (bottom-right) = the emerging-leader corner.
  ctx.globalAlpha = 1
  ctx.fillStyle = withAlpha(o.palette['--grn'], 0.07)
  ctx.fillRect(cx, cy, g.w - g.pr - cx, g.pt + plotH - cy)
  // crosshair at the (50,50) midpoint.
  ctx.strokeStyle = withAlpha(o.palette['--dim'], 0.5)
  ctx.lineWidth = 1
  ctx.beginPath()
  ctx.moveTo(cx, g.pt)
  ctx.lineTo(cx, g.pt + plotH)
  ctx.moveTo(g.pl, cy)
  ctx.lineTo(g.pl + plotW, cy)
  ctx.stroke()

  const drawn: DrawnPoint[] = []
  for (const s of o.data.stocks) {
    const pt = s.pts[o.week]
    if (!pt) continue
    const member =
      o.colorBy === 'theme'
        ? o.activeTheme != null && s.themes.some((t) => t.theme === o.activeTheme)
        : true
    const faded = !inScope(s, o.scope) || !member
    const r = radiusFor(s.mktcap)
    ctx.globalAlpha = faded ? 0.06 : o.colorBy === 'theme' ? 1 : 0.72
    ctx.fillStyle = o.palette[colorVar(s, pt, o.colorBy, o.activeTheme)] ?? o.palette['--dim2']
    ctx.beginPath()
    ctx.arc(sx(pt.rs), sy(pt.val), faded ? 1.2 : r, 0, 7)
    ctx.fill()
    if (!faded) drawn.push({ ticker: s.ticker, px: sx(pt.rs), py: sy(pt.val), r })
  }

  // hover ring around the hovered (non-faded) point (M2.3).
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

  ctx.globalAlpha = 1
  return drawn
}

/** Nearest drawn point to (lx,ly) in logical px, or null if none within ~r+5px
 *  (the hover/click hit test — linear scan, fine for 500-2000 points; PRD NFR-8). */
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
