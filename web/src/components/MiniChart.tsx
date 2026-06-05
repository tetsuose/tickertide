import type { ChartSeries } from '../types'

// Pure SVG mini-chart (PRD §9.3): ~90d candlesticks + MA50/150/200 + volume +
// 52w-high dashed line. Props-only, no DOM measurement, so it renders identically
// under SSR and in the browser. Geometry transcribed from the UX contract.
const W = 440
const H = 148
const PL = 4
const PR = 4
const PT = 4
const PRICE_H = 104
const GAP = 8
const VOL_H = 30

export default function MiniChart({ chart }: { chart: ChartSeries }) {
  const n = chart.close.length
  if (n === 0) return <svg viewBox={`0 0 ${W} ${H}`} width="100%" />

  const bw = (W - PL - PR) / n
  const cw = Math.max(1, bw * 0.62)

  // price range over visible lows/highs + MA50/200 + the 52w-high line (so the
  // dashed line stays in view); volume scaled to its own band.
  let pmin = Infinity
  let pmax = -Infinity
  let vmax = 0
  for (let i = 0; i < n; i++) {
    const lo = chart.low[i]
    const hi = chart.high[i]
    const m200 = chart.ma200[i]
    const m50 = chart.ma50[i]
    const v = chart.volume[i]
    if (lo != null) pmin = Math.min(pmin, lo)
    if (m200 != null) pmin = Math.min(pmin, m200)
    if (hi != null) pmax = Math.max(pmax, hi)
    if (m50 != null) pmax = Math.max(pmax, m50)
    if (v != null) vmax = Math.max(vmax, v)
  }
  if (chart.high_52w != null) pmax = Math.max(pmax, chart.high_52w)
  if (!isFinite(pmin) || !isFinite(pmax) || pmax <= pmin) {
    pmin = 0
    pmax = 1
  }
  const pad = (pmax - pmin) * 0.06
  pmin -= pad
  pmax += pad

  const X = (i: number) => PL + i * bw + bw / 2
  const PY = (p: number) => PT + PRICE_H - ((p - pmin) / (pmax - pmin)) * PRICE_H
  const volBase = PT + PRICE_H + GAP + VOL_H
  const VY = (v: number) => (vmax > 0 ? volBase - (v / vmax) * VOL_H : volBase)

  // MA polyline with gaps on null (short history leaves leading MAs undefined).
  const maPath = (arr: (number | null)[]) => {
    let d = ''
    let pen = false
    for (let i = 0; i < n; i++) {
      const y = arr[i]
      if (y == null) {
        pen = false
        continue
      }
      d += (pen ? 'L' : 'M') + X(i).toFixed(1) + ' ' + PY(y).toFixed(1)
      pen = true
    }
    return d
  }

  const yh = chart.high_52w != null ? PY(chart.high_52w) : null

  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ display: 'block' }}>
      {yh != null && (
        <line x1={PL} y1={yh} x2={W - PR} y2={yh} stroke="var(--dim2)" strokeDasharray="3 3" strokeWidth="1" />
      )}

      {/* candlesticks: wick high→low + body open→close, green up / red down */}
      {chart.close.map((c, i) => {
        const o = chart.open[i]
        const hi = chart.high[i]
        const lo = chart.low[i]
        if (c == null || o == null) return null
        const up = c >= o
        const col = up ? 'var(--grn)' : 'var(--red)'
        const y1 = PY(o)
        const y2 = PY(c)
        const top = Math.min(y1, y2)
        const h = Math.max(0.8, Math.abs(y1 - y2))
        return (
          <g key={i}>
            {hi != null && lo != null && (
              <line x1={X(i)} y1={PY(hi)} x2={X(i)} y2={PY(lo)} stroke={col} strokeWidth="0.7" />
            )}
            <rect x={X(i) - cw / 2} y={top} width={cw} height={h} fill={col} />
          </g>
        )
      })}

      {/* MA lines drawn 200 → 150 → 50 so the fast MA sits on top */}
      <path d={maPath(chart.ma200)} fill="none" stroke="var(--ma200)" strokeWidth="1.3" />
      <path d={maPath(chart.ma150)} fill="none" stroke="var(--ma150)" strokeWidth="1.3" />
      <path d={maPath(chart.ma50)} fill="none" stroke="var(--ma50)" strokeWidth="1.3" />

      {/* volume band */}
      {chart.volume.map((v, i) => {
        if (v == null) return null
        const c = chart.close[i]
        const o = chart.open[i]
        const up = c != null && o != null ? c >= o : true
        const y = VY(v)
        return (
          <rect
            key={'v' + i}
            x={X(i) - cw / 2}
            y={y}
            width={cw}
            height={volBase - y}
            fill={up ? 'rgba(46,192,122,.5)' : 'rgba(255,93,87,.5)'}
          />
        )
      })}
    </svg>
  )
}
