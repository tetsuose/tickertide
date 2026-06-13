// Shared pure geometry for the chart time-cursor (Discovery MiniChart / Rotation
// RS-Ratio / Stock stack). The cursor is a HOVER-ONLY overlay: each chart holds a
// hoverIndex state that is null at rest, so SSR / initial render emits no cursor and
// the existing renderToStaticMarkup assertions (path counts, pane labels) are untouched.
// These helpers map a mouse position to the nearest data index and lay out the resident
// date axis — no DOM, no React, so they unit-test directly (chart-hover.test.ts).

/** Map a mouse clientX to the SVG's internal viewBox x. The charts render at width=100%,
 *  so the on-screen pixel scale is viewBoxW / renderedWidth (from getBoundingClientRect). */
export function viewBoxXFromClient(clientX: number, rectLeft: number, rectWidth: number, viewBoxW: number): number {
  if (rectWidth <= 0) return 0
  return (clientX - rectLeft) * (viewBoxW / rectWidth)
}

/** Same for the y axis — Rotation uses it to pick the RS-Ratio line nearest the cursor. */
export function viewBoxYFromClient(clientY: number, rectTop: number, rectHeight: number, viewBoxH: number): number {
  if (rectHeight <= 0) return 0
  return (clientY - rectTop) * (viewBoxH / rectHeight)
}

/** Nearest data index for a BAND layout — points centered at PL + i·bw + bw/2 with
 *  bw = (W−PL−PR)/n (MiniChart, StockStack). Returns null when the cursor sits outside
 *  the plot band (half-cell tolerance keeps the first/last bar reachable). */
export function bandIndexAt(vx: number, PL: number, PR: number, W: number, n: number): number | null {
  if (n <= 0) return null
  const plot = W - PL - PR
  if (plot <= 0) return null
  const bw = plot / n
  if (vx < PL - bw * 0.5 || vx > W - PR + bw * 0.5) return null
  return Math.max(0, Math.min(n - 1, Math.floor((vx - PL) / bw)))
}

/** Nearest data index for a POINT layout — points at padL + i/(n−1)·(W−padL−padR)
 *  (Rotation RS-Ratio lines). Returns null when outside, half-step tolerance at edges. */
export function pointIndexAt(vx: number, padL: number, padR: number, W: number, n: number): number | null {
  if (n <= 0) return null
  if (n === 1) return 0
  const plot = W - padL - padR
  if (plot <= 0) return null
  const step = plot / (n - 1)
  if (vx < padL - step * 0.5 || vx > W - padR + step * 0.5) return null
  return Math.max(0, Math.min(n - 1, Math.round((vx - padL) / step)))
}

/** Index (into `seriesList`) whose value at column `idx` is vertically closest to the
 *  cursor's viewBox y; null points are skipped. Returns -1 if nothing renders there.
 *  `yOf` is the chart's value→y scale. Rotation overview: which line the cursor reads. */
export function nearestSeriesAt(
  seriesList: (number | null)[][],
  idx: number,
  vy: number,
  yOf: (v: number) => number,
): number {
  let best = -1
  let bd = Infinity
  for (let s = 0; s < seriesList.length; s++) {
    const v = seriesList[s][idx]
    if (v == null) continue
    const d = Math.abs(yOf(v) - vy)
    if (d < bd) {
      bd = d
      best = s
    }
  }
  return best
}

/** Evenly spaced tick indices across [0, n−1] (≈`count`, both ends included) for the
 *  resident date axis. Deduped + ascending; [] for n≤0, [0] for n==1. */
export function axisTickIndices(n: number, count = 5): number[] {
  if (n <= 0) return []
  if (n === 1) return [0]
  const c = Math.max(2, Math.min(count, n))
  const out: number[] = []
  for (let t = 0; t < c; t++) out.push(Math.round((t / (c - 1)) * (n - 1)))
  return Array.from(new Set(out)).sort((a, b) => a - b)
}

/** 'YYYY-MM-DD' → 'MM/DD' for compact axis ticks; returns the input unchanged if it is
 *  not a full ISO date (defensive — never fabricates). */
export function tickDate(iso: string | null | undefined): string {
  if (!iso || iso.length < 10) return iso ?? ''
  return iso.slice(5, 7) + '/' + iso.slice(8, 10)
}
