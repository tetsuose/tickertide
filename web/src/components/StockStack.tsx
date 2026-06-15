import { useState } from 'react'
import type { StockBundle, RevenueQuarter } from '../types'
import { viewBoxXFromClient, bandIndexAt, axisTickIndices, tickDate } from '../lib/chart-hover'
import CursorReadout from './ChartCursor'

// M5.4 the time-aligned price↔fundamentals stack (PRD §9.6): four panes sharing ONE x axis
// (the ~2y daily date axis) with quarter gridlines running through all of them, so you read
// price ↔ revenue ↔ P/S against the same calendar:
//   PRICE   candlesticks + MA50/150/200 + 52w-high dashed
//   VOLUME  daily bars (up green / down red)
//   REVENUE quarterly TTM bars (YoY up green / down red) at each fiscal period_end, plus a dim
//           formal-filing marker at each quarter's effective_eod_date (PRD §10.5) — where its
//           revenue actually enters P/S, a filing-lag right of the bar — so the period_end
//           placement can't be misread as "known then"
//   P/S     daily P/S line (steps at effective_eod_date, never period_end)
// A resident MM/DD date axis runs beneath, and a hover time-cursor spans all four panes —
// reading close / volume / TTM-revenue / P/S at the cursored day off one vertical, which is
// the stack's whole point. The cursor is a hover-only overlay (hoverIndex null at rest) so
// the stack still renders identically under SSR (Stock.test asserts the markup).
const W = 880
const PL = 50
const PR = 10
const PT = 8
const PRICE_H = 168
const VOL_H = 38
const REV_H = 76
const PS_H = 76
const GAP = 16

const priceTop = PT
const volTop = priceTop + PRICE_H + GAP
const revTop = volTop + VOL_H + GAP
const psTop = revTop + REV_H + GAP
const axisY = psTop + PS_H + 14 // resident date-axis baseline
const H = psTop + PS_H + 26

const fmtRev = (v: number): string =>
  v >= 1e9 ? (v / 1e9).toFixed(0) + 'B' : v >= 1e6 ? (v / 1e6).toFixed(0) + 'M' : v.toFixed(0)

const fmtVol = (v: number): string =>
  v >= 1e9
    ? (v / 1e9).toFixed(1) + 'B'
    : v >= 1e6
      ? (v / 1e6).toFixed(1) + 'M'
      : v >= 1e3
        ? (v / 1e3).toFixed(0) + 'K'
        : v.toFixed(0)

export default function StockStack({ bundle }: { bundle: StockBundle }) {
  const [hi, setHi] = useState<number | null>(null)
  const p = bundle.price
  const n = p.dates.length
  if (n === 0) return <svg viewBox={`0 0 ${W} ${H}`} width="100%" />

  const bw = (W - PL - PR) / n
  const X = (i: number) => PL + i * bw + bw / 2
  const dateIndex = new Map(p.dates.map((d, i) => [d, i] as const))
  // a quarter's period_end maps to the latest trading day on or before it
  const idxOnOrBefore = (date: string | null): number | null => {
    if (date == null) return null
    if (dateIndex.has(date)) return dateIndex.get(date)!
    let lo = -1
    for (let i = 0; i < n; i++) {
      if (p.dates[i] != null && (p.dates[i] as string) <= date) lo = i
      else break
    }
    return lo >= 0 ? lo : null
  }

  // PRICE range over visible lows/highs + MA50/200 + the 52w-high line.
  let pmin = Infinity
  let pmax = -Infinity
  let vmax = 0
  for (let i = 0; i < n; i++) {
    const lo = p.low[i]
    const hi = p.high[i]
    const m200 = p.ma200[i]
    const m50 = p.ma50[i]
    const v = p.volume[i]
    if (lo != null) pmin = Math.min(pmin, lo)
    if (m200 != null) pmin = Math.min(pmin, m200)
    if (hi != null) pmax = Math.max(pmax, hi)
    if (m50 != null) pmax = Math.max(pmax, m50)
    if (v != null) vmax = Math.max(vmax, v)
  }
  if (p.high_52w != null) pmax = Math.max(pmax, p.high_52w)
  if (!isFinite(pmin) || !isFinite(pmax) || pmax <= pmin) {
    pmin = 0
    pmax = 1
  }
  const ppad = (pmax - pmin) * 0.06
  pmin -= ppad
  pmax += ppad
  const priceY = (v: number) => priceTop + PRICE_H - ((v - pmin) / (pmax - pmin)) * PRICE_H
  const volY = (v: number) => (vmax > 0 ? volTop + VOL_H - (v / vmax) * VOL_H : volTop + VOL_H)

  // REVENUE: quarterly TTM bars at each period_end's x, height ∝ revenue, color by YoY.
  const revs = bundle.revenue_q.filter((r) => r.revenue_ttm != null && idxOnOrBefore(r.period_end) != null)
  const revMax = Math.max(1, ...revs.map((r) => r.revenue_ttm as number))
  const revBarW = Math.max(3, bw * 18) // ~a quarter's worth of trading days, capped readable
  const revBaseline = revTop + REV_H
  const revY = (v: number) => revBaseline - (v / revMax) * REV_H

  // P/S over time
  const psPts = bundle.ps_series
    .map((s) => ({ i: s.date != null ? dateIndex.get(s.date) ?? null : null, ps: s.ps }))
    .filter((q) => q.i != null && q.ps != null) as { i: number; ps: number }[]
  let psMin = Infinity
  let psMax = -Infinity
  for (const q of psPts) {
    psMin = Math.min(psMin, q.ps)
    psMax = Math.max(psMax, q.ps)
  }
  if (!isFinite(psMin) || psMax <= psMin) {
    psMin = 0
    psMax = 1
  }
  const psPad = (psMax - psMin) * 0.08
  psMin -= psPad
  psMax += psPad
  const psY = (v: number) => psTop + PS_H - ((v - psMin) / (psMax - psMin)) * PS_H

  const maPath = (arr: (number | null)[]) => {
    let d = ''
    let pen = false
    for (let i = 0; i < n; i++) {
      const y = arr[i]
      if (y == null) {
        pen = false
        continue
      }
      d += (pen ? 'L' : 'M') + X(i).toFixed(1) + ' ' + priceY(y).toFixed(1)
      pen = true
    }
    return d
  }
  const psPath = psPts
    .map((q, k) => (k === 0 ? 'M' : 'L') + X(q.i).toFixed(1) + ' ' + psY(q.ps).toFixed(1))
    .join('')

  const yh = p.high_52w != null ? priceY(p.high_52w) : null
  const panes: [number, number, string][] = [
    [priceTop, PRICE_H, 'PRICE'],
    [volTop, VOL_H, 'VOL'],
    [revTop, REV_H, 'REVENUE'],
    [psTop, PS_H, 'P/S'],
  ]

  // values at the cursored day (hover overlay only; null when a series has no point there)
  const hClose = hi != null ? p.close[hi] : null
  const hVol = hi != null ? p.volume[hi] : null
  const hPs = hi != null ? psPts.find((q) => q.i === hi)?.ps ?? null : null
  // TTM revenue *formally effective* at the cursored day (formal-filing PIT, PRD §10.5): the
  // latest quarter whose effective_eod_date ≤ that day — NOT period_end ≤ day, which would
  // surface a quarter's revenue before it was filed (the lookahead this view avoids), and
  // would disagree with the P/S line (which steps at effective_eod). Falls back to period_end
  // for pre-PIT bundles that omit effective_eod_date.
  const hDate = hi != null ? p.dates[hi] : null
  let hRev: number | null = null
  let hRevQ: RevenueQuarter | null = null
  if (hDate != null) {
    for (const r of revs) {
      const eff = r.effective_eod_date ?? r.period_end
      if (eff != null && eff <= hDate && r.revenue_ttm != null) {
        hRev = r.revenue_ttm as number
        hRevQ = r
      }
    }
  }

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      width="100%"
      style={{ display: 'block' }}
      className="stk-stack"
      onMouseMove={(e) => {
        const r = e.currentTarget.getBoundingClientRect()
        setHi(bandIndexAt(viewBoxXFromClient(e.clientX, r.left, r.width, W), PL, PR, W, n))
      }}
      onMouseLeave={() => setHi(null)}
    >
      {/* transparent catcher so the whole stack emits onMouseMove, not just drawn marks */}
      <rect x={PL} y={priceTop} width={W - PL - PR} height={psTop + PS_H - priceTop} fill="transparent" />

      {/* quarter gridlines through all four panes (period_end of each quarter) */}
      {revs.map((r, k) => {
        const xi = X(idxOnOrBefore(r.period_end) as number)
        return (
          <line
            key={'q' + k}
            x1={xi}
            y1={priceTop}
            x2={xi}
            y2={psTop + PS_H}
            stroke="var(--line)"
            strokeWidth="1"
          />
        )
      })}

      {/* pane frames + labels */}
      {panes.map(([top, h, label]) => (
        <g key={label}>
          <rect x={PL} y={top} width={W - PL - PR} height={h} fill="none" stroke="var(--line)" strokeWidth="1" />
          <text x={PL + 4} y={top + 12} fontSize="9" fill="var(--dim)" fontFamily="var(--mono)">
            {label}
          </text>
        </g>
      ))}

      {/* PRICE: 52w-high dashed + candles + MAs */}
      {yh != null && (
        <line x1={PL} y1={yh} x2={W - PR} y2={yh} stroke="var(--dim2)" strokeDasharray="3 3" strokeWidth="1" />
      )}
      {p.close.map((c, i) => {
        const o = p.open[i]
        const hi = p.high[i]
        const lo = p.low[i]
        if (c == null || o == null) return null
        const up = c >= o
        const col = up ? 'var(--grn)' : 'var(--red)'
        const y1 = priceY(o)
        const y2 = priceY(c)
        const top = Math.min(y1, y2)
        const bh = Math.max(0.6, Math.abs(y1 - y2))
        const cw = Math.max(0.6, bw * 0.6)
        return (
          <g key={'c' + i}>
            {hi != null && lo != null && (
              <line x1={X(i)} y1={priceY(hi)} x2={X(i)} y2={priceY(lo)} stroke={col} strokeWidth="0.6" />
            )}
            <rect x={X(i) - cw / 2} y={top} width={cw} height={bh} fill={col} />
          </g>
        )
      })}
      <path d={maPath(p.ma50)} fill="none" stroke="var(--ma50)" strokeWidth="1" />
      <path d={maPath(p.ma150)} fill="none" stroke="var(--ma150)" strokeWidth="1" />
      <path d={maPath(p.ma200)} fill="none" stroke="var(--ma200)" strokeWidth="1" />

      {/* VOLUME bars */}
      {p.volume.map((v, i) => {
        if (v == null) return null
        const c = p.close[i]
        const o = p.open[i]
        const up = c != null && o != null ? c >= o : true
        const y = volY(v)
        return (
          <rect
            key={'v' + i}
            x={X(i) - Math.max(0.5, bw * 0.6) / 2}
            y={y}
            width={Math.max(0.5, bw * 0.6)}
            height={volTop + VOL_H - y}
            fill={up ? 'var(--grn)' : 'var(--red)'}
            opacity="0.7"
          />
        )
      })}

      {/* REVENUE quarterly bars (YoY up green / down red), labeled latest */}
      {revs.map((r, k) => {
        const xi = X(idxOnOrBefore(r.period_end) as number)
        const rv = r.revenue_ttm as number
        const y = revY(rv)
        const up = r.yoy == null ? null : r.yoy >= 0
        const col = up == null ? 'var(--dim2)' : up ? 'var(--grn)' : 'var(--red)'
        return (
          <g key={'r' + k}>
            <rect x={xi - revBarW / 2} y={y} width={revBarW} height={revBaseline - y} fill={col} opacity="0.8" />
            {k === revs.length - 1 && (
              <text x={xi} y={y - 3} fontSize="8" fill="var(--dim)" textAnchor="middle" fontFamily="var(--mono)">
                {fmtRev(rv)}
                {r.yoy != null ? ` ${r.yoy >= 0 ? '+' : ''}${(r.yoy * 100).toFixed(0)}%` : ''}
              </text>
            )}
          </g>
        )
      })}

      {/* formal-filing markers (PRD §10.5): each REVENUE bar sits at its fiscal period_end, but
          its data only enters P/S from effective_eod_date (~a filing lag later). A dim dashed
          tick at the effective x + a baseline connector from the bar make that gap visible, so
          the period_end placement can't be misread as "known then". Skipped when the bundle
          predates PIT (no effective_eod_date) or the two map to the same trading day. */}
      {revs.map((r, k) => {
        const eff = r.effective_eod_date ?? r.period_end
        const ei = eff != null ? idxOnOrBefore(eff) : null
        const pi = idxOnOrBefore(r.period_end)
        if (ei == null || pi == null || ei === pi) return null
        const ex = X(ei)
        return (
          <g key={'f' + k}>
            <line x1={X(pi)} y1={revBaseline} x2={ex} y2={revBaseline} stroke="var(--dim2)" strokeWidth="0.8" strokeDasharray="1 2" />
            <line x1={ex} y1={revTop} x2={ex} y2={revBaseline} stroke="var(--dim2)" strokeWidth="0.8" strokeDasharray="2 2" />
            {k === revs.length - 1 && (
              <text x={ex + 2} y={revTop + 9} fontSize="7" fill="var(--dim2)" textAnchor="start" fontFamily="var(--mono)">
                filed
              </text>
            )}
          </g>
        )
      })}

      {/* P/S over time line */}
      <path d={psPath} fill="none" stroke="var(--blu)" strokeWidth="1.2" />
      {psPts.length > 0 && (
        <text
          x={X(psPts[psPts.length - 1].i)}
          y={psY(psPts[psPts.length - 1].ps) - 3}
          fontSize="8"
          fill="var(--blu)"
          textAnchor="end"
          fontFamily="var(--mono)"
        >
          {psPts[psPts.length - 1].ps.toFixed(1)}×
        </text>
      )}

      {/* resident date axis: MM/DD ticks shared by all four panes */}
      {axisTickIndices(n, 6).map((i, k, arr) => (
        <text
          key={'ax' + i}
          className="chax"
          x={X(i)}
          y={axisY}
          textAnchor={k === 0 ? 'start' : k === arr.length - 1 ? 'end' : 'middle'}
        >
          {tickDate(p.dates[i])}
        </text>
      ))}

      {/* hover time-cursor spanning all four panes; each pane reads its own series */}
      {hi != null && (
        <>
          <line className="chcur-line" x1={X(hi)} y1={priceTop} x2={X(hi)} y2={psTop + PS_H} />
          {hClose != null && <circle className="chcur-dot" cx={X(hi)} cy={priceY(hClose)} r={2.5} fill="var(--txt)" />}
          {hPs != null && <circle className="chcur-dot" cx={X(hi)} cy={psY(hPs)} r={2.5} fill="var(--blu)" />}
          <CursorReadout
            x={X(hi)}
            y={priceTop + 2}
            viewW={W}
            text={`${tickDate(p.dates[hi])}  ${hClose != null ? hClose.toFixed(2) : '—'}`}
          />
          <CursorReadout x={X(hi)} y={volTop + 2} viewW={W} text={hVol != null ? fmtVol(hVol) : '—'} />
          <CursorReadout x={X(hi)} y={revTop + 2} viewW={W} text={hRev != null ? fmtRev(hRev) : '—'} />
          {/* which fiscal quarter (and from which effective date) this TTM enters P/S — the
              formal-filing PIT context for the cursored day (§10.5). */}
          {hRevQ?.period_end != null && (
            <CursorReadout
              x={X(hi)}
              y={revTop + 16}
              viewW={W}
              color="var(--dim2)"
              text={`Q${tickDate(hRevQ.period_end)}${hRevQ.effective_eod_date ? '→' + tickDate(hRevQ.effective_eod_date) : ''}`}
            />
          )}
          <CursorReadout
            x={X(hi)}
            y={psTop + 2}
            viewW={W}
            color="var(--blu)"
            text={hPs != null ? hPs.toFixed(1) + '×' : '—'}
          />
        </>
      )}
    </svg>
  )
}
