import { useState } from 'react'
import type { Stock, Components } from '../types'
import MiniChart from './MiniChart'

// composite score color (PRD 附录C): >=62 grn / >=47 amb / else dim.
function scoreColor(score: number | null): string {
  if (score == null) return 'var(--score-lo)'
  if (score >= 62) return 'var(--score-hi)'
  if (score >= 47) return 'var(--score-mid)'
  return 'var(--score-lo)'
}

function fmtMktcap(v: number | null): string {
  if (v == null) return '—'
  if (v >= 1e12) return '$' + (v / 1e12).toFixed(1) + 'T'
  if (v >= 1e9) return '$' + (v / 1e9).toFixed(1) + 'B'
  if (v >= 1e6) return '$' + (v / 1e6).toFixed(0) + 'M'
  return '$' + v.toFixed(0)
}

const pct = (v: number | null): string =>
  v == null ? '—' : (v >= 0 ? '+' : '') + (v * 100).toFixed(0) + '%'

// 5 components in weight-curve order, with display labels (PRD §9.1.1 / §10.6).
const COMPONENTS: { key: keyof Components; label: string }[] = [
  { key: 'rs', label: 'RS' },
  { key: 'high', label: '52WH' },
  { key: 'trend', label: 'TREND' },
  { key: 'vol', label: 'VOL' },
  { key: 'accel', label: 'ACCEL' },
]

// evidence-card = the collapsed state of a Stock (PRD §9.1.3): scannable raw
// facts; composite is an expandable badge, never a buy/target. The 5 raw
// components + their weights are revealed on the badge (no black box).
export default function EvidenceCard({
  stock,
  weights,
  score,
  onOpen,
  defaultOpen = false,
}: {
  stock: Stock
  /** weights at the current knob k (live — re-weighted by the early⟷reliable knob). */
  weights: Components
  /** composite recomputed at the current k (composite.ts, C9). Drives badge + sort. */
  score: number
  onOpen?: (ticker: string) => void
  defaultOpen?: boolean
}) {
  const [open, setOpen] = useState(defaultOpen)
  const e = stock.evidence
  // d/d: the engine's day-over-day composite move at the default weighting.
  // prev-day components aren't exported, so this is a snapshot fact (it does not
  // track the knob); at the default k it lines up with the badge.
  const dd =
    stock.composite != null && stock.composite_prev != null
      ? stock.composite - stock.composite_prev
      : null

  return (
    <div className="ecard" onClick={() => onOpen?.(stock.ticker)}>
      <div className="ec-head">
        <div className="ec-tk">
          {stock.ticker}{' '}
          <span className="ec-sec">
            {stock.sector ?? '—'} · {fmtMktcap(stock.mktcap)}
          </span>
        </div>
        <div className="ec-headr">
          {dd != null && (
            <span
              className="ec-dd"
              style={{ color: dd >= 0 ? 'var(--grn)' : 'var(--red)' }}
              title="d/d composite (engine default weighting)"
            >
              {dd >= 0 ? '▲' : '▼'}
              {Math.abs(dd).toFixed(1)}
            </span>
          )}
          <button
            className="ec-badge"
            style={{ color: scoreColor(score) }}
            onClick={(ev) => {
              ev.stopPropagation()
              setOpen(!open)
            }}
            aria-expanded={open}
          >
            {score.toFixed(0)} <i>▾</i>
          </button>
        </div>
      </div>

      {stock.themes.length > 0 && (
        <div className="ec-themes">
          {stock.themes.map((t) => (
            <span key={t.theme} style={{ color: `var(--th-${t.theme.toLowerCase()}, var(--dim))` }}>
              {t.theme}
            </span>
          ))}
        </div>
      )}

      {open && (
        <div className="ec-comp" onClick={(ev) => ev.stopPropagation()}>
          {COMPONENTS.map(({ key, label }) => {
            const cv = stock.components[key] // raw component ∈ [0,1]
            const wv = weights[key]
            return (
              <div key={key} className="ec-crow">
                <span>{label}</span>
                <span className="ec-bar">
                  <span className="ec-bar-fill" style={{ width: `${Math.round((cv ?? 0) * 100)}%` }} />
                </span>
                <b>{cv == null ? '—' : cv.toFixed(2)}</b>
                <em>{Math.round((wv ?? 0) * 100)}%</em>
              </div>
            )
          })}
          <div className="ec-note">composite = Σ wᵢ·分量（原始分的加权和，无黑箱）</div>
        </div>
      )}

      <div className="ec-chart">
        <MiniChart chart={stock.chart} />
      </div>

      <div className="ec-fields">
        <div className="ec-f">
          <span>1M</span>
          <b style={{ color: (e.ret_1m ?? 0) >= 0 ? 'var(--grn)' : 'var(--red)' }}>{pct(e.ret_1m)}</b>
        </div>
        <div className="ec-f">
          <span>3M</span>
          <b style={{ color: (e.ret_3m ?? 0) >= 0 ? 'var(--grn)' : 'var(--red)' }}>{pct(e.ret_3m)}</b>
        </div>
        <div className="ec-f">
          <span>6M</span>
          <b style={{ color: (e.ret_6m ?? 0) >= 0 ? 'var(--grn)' : 'var(--red)' }}>{pct(e.ret_6m)}</b>
        </div>
        <div className="ec-f">
          <span>from high</span>
          <b>{pct(e.from_high)}</b>
        </div>
        <div className="ec-f">
          <span>week</span>
          <b>{e.weeks_since_breakout ?? '—'}</b>
        </div>
        <div className="ec-f">
          <span>vol</span>
          <b style={{ color: (e.vol_mult ?? 0) >= 1.5 ? 'var(--grn)' : 'var(--txt)' }}>
            {e.vol_mult == null ? '—' : e.vol_mult.toFixed(1) + '×'}
          </b>
        </div>
      </div>

      <div className="ec-why">
        <span className="ec-wl">why moving</span> <span className="ec-dim">— AI enrichment placeholder</span>
      </div>
    </div>
  )
}
