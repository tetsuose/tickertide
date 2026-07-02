import { useState } from 'react'
import type { ChartSeries } from '../types'
import { viewBoxXFromClient, bandIndexAt, axisTickIndices, tickDate } from '../lib/chart-hover'
import CursorReadout from './ChartCursor'

// Pure SVG mini-chart (PRD §9.3): ~90d candlesticks + MA50/150/200 + volume +
// 52w-high dashed line, a resident MM/DD date axis, and a hover time-cursor reading the
// close at the cursored day. The cursor is a hover-only overlay (hoverIndex null at rest)
// so the chart still renders identically under SSR (Discovery.test asserts the markup).
const W = 440
const AX_H = 16 // resident date-axis strip below the volume band
const H = 148 + AX_H
const PL = 4
const PR = 4
const PT = 4
const PRICE_H = 104
const GAP = 8
const VOL_H = 30

export default function MiniChart({
  chart,
  hlLastN,
}: {
  chart: ChartSeries
  /** Optional STATIC backdrop tint over the last N trading days (the steady-riser W=10
   *  window, PRD §10.8) so the card's riser numbers are countable in the band. Static
   *  (renders under SSR too) — unlike the cursor, which must stay hover-only. */
  hlLastN?: number
}) {
  const [hi, setHi] = useState<number | null>(null)
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
  const hc = hi != null ? chart.close[hi] : null

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      width="100%"
      style={{ display: 'block' }}
      onMouseMove={(e) => {
        const r = e.currentTarget.getBoundingClientRect()
        setHi(bandIndexAt(viewBoxXFromClient(e.clientX, r.left, r.width, W), PL, PR, W, n))
      }}
      onMouseLeave={() => setHi(null)}
    >
      {/* transparent catcher so the whole plot area emits onMouseMove, not just drawn marks */}
      <rect x={PL} y={PT} width={W - PL - PR} height={volBase - PT} fill="transparent" />

      {/* static last-N-days window tint (steady-riser W=10) — behind candles/MAs/volume */}
      {hlLastN != null && hlLastN > 0 && n > 1 && (
        <rect
          className="mc-hlwin"
          x={X(Math.max(0, n - hlLastN)) - bw / 2}
          y={PT}
          width={W - PR - (X(Math.max(0, n - hlLastN)) - bw / 2)}
          height={volBase - PT}
          fill="var(--grn)"
          fillOpacity="0.055"
        />
      )}

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

      {/* resident date axis: compact MM/DD ticks under the volume band */}
      {axisTickIndices(n, 3).map((i, k, arr) => (
        <text
          key={'ax' + i}
          className="chax"
          x={X(i)}
          y={volBase + 11}
          textAnchor={k === 0 ? 'start' : k === arr.length - 1 ? 'end' : 'middle'}
        >
          {tickDate(chart.dates[i])}
        </text>
      ))}

      {/* hover time-cursor: vertical line + close marker + date·close readout */}
      {hi != null && (
        <>
          <line className="chcur-line" x1={X(hi)} y1={PT} x2={X(hi)} y2={volBase} />
          {hc != null && <circle className="chcur-dot" cx={X(hi)} cy={PY(hc)} r={2.5} fill="var(--txt)" />}
          <CursorReadout
            x={X(hi)}
            y={PT + 1}
            viewW={W}
            text={`${tickDate(chart.dates[hi])}  ${hc != null ? hc.toFixed(2) : '—'}`}
          />
        </>
      )}
    </svg>
  )
}
