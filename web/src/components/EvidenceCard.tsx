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

// step-rate ratio = (ret10/10)/(ret50/50): the readable form of ig_accel (PRD §10.8).
// It blows up when ret50≈0 (M7.2 pitfall: fixture TT20=685) — mathematically faithful
// but useless on the card. Clamp the DISPLAY at ±SR_CLAMP (the engine's ranked ig_accel
// is unaffected — this is display-only) and mark clamped values with a leading >/<.
const SR_CLAMP = 20
function fmtStepRate(v: number | null): string {
  if (v == null) return '—'
  if (v > SR_CLAMP) return `>${SR_CLAMP}×`
  if (v < -SR_CLAMP) return `<-${SR_CLAMP}×`
  return v.toFixed(1) + '×'
}

const fmtDate = (d: string | null): string => (d == null ? '—' : d.slice(5)) // MM-DD

function fmtMktcap(v: number | null): string {
  if (v == null) return '—'
  if (v >= 1e12) return '$' + (v / 1e12).toFixed(1) + 'T'
  if (v >= 1e9) return '$' + (v / 1e9).toFixed(1) + 'B'
  if (v >= 1e6) return '$' + (v / 1e6).toFixed(0) + 'M'
  return '$' + v.toFixed(0)
}

const pct = (v: number | null): string =>
  v == null ? '—' : (v >= 0 ? '+' : '') + (v * 100).toFixed(0) + '%'

// 5 components in fixed-weight order, with display labels (PRD §9.1.1 / §10.6).
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
  /** fixed composite weights (WEIGHTS, no knob) — shown per component for informed consent. */
  weights: Components
  /** the engine's composite at the fixed weighting (stock.composite, C9). Side-read badge. */
  score: number
  onOpen?: (ticker: string) => void
  defaultOpen?: boolean
}) {
  const [open, setOpen] = useState(defaultOpen)
  const e = stock.evidence
  const ign = stock.ignition
  // d/d: the engine's day-over-day composite move at the fixed weighting. Both the
  // badge (score = stock.composite) and this delta are the engine's exported composite
  // (no knob, PRD §16), so the delta lines up with the badge exactly.
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
          {/* 持续点火 badge: this IS the Discovery sort signal (PRD §10.8.2). candidate
              = top-decile ign_pct AND sustained ≥persist_min days. */}
          {ign?.candidate && (
            <span
              className="ec-ign"
              title={`持续点火 candidate: ign_pct ${ign.ign_pct?.toFixed(0)} · 持续 ${ign.ign_persist_days}d`}
            >
              🔥 {ign.ign_persist_days}d
            </span>
          )}
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
          {/* composite is now a 已确认 (confirmation) side-read, NOT the sort key (M7.3). */}
          <button
            className="ec-badge"
            style={{ color: scoreColor(score) }}
            onClick={(ev) => {
              ev.stopPropagation()
              setOpen(!open)
            }}
            aria-expanded={open}
            title="composite（已确认副读，固定权重；非点火榜排序）"
          >
            {score.toFixed(0)} <i>▾</i>
          </button>
        </div>
      </div>

      {/* 点火证据 (ignition evidence, PRD §10.8) — the card's primary read on the
          ignition board: breakout day / vol surge× / step-rate (clamped) / reclaimed MA50.
          Same source as the chart bars (C9). vol_mult here is ig_vsurge (5/60 ratio),
          distinct from the 50d vol_mult in the field strip below. */}
      {ign && (
        <div className="ec-ignev">
          <span className="ec-ignev-i" title="trailing-60d high (breakout reference) + 距今天数">
            <em>brk</em> {fmtDate(ign.evidence.breakout_day)}
            {ign.evidence.days_since_breakout != null && (
              <i className="ec-ignev-d"> ·{ign.evidence.days_since_breakout}d前</i>
            )}
          </span>
          <span className="ec-ignev-i" title="放量× = ig_vsurge（5日/60日成交量比）">
            <em>vol</em>{' '}
            <b style={{ color: (ign.evidence.vol_mult ?? 0) >= 1.5 ? 'var(--grn)' : 'var(--txt)' }}>
              {ign.evidence.vol_mult == null ? '—' : ign.evidence.vol_mult.toFixed(2) + '×'}
            </b>
          </span>
          <span className="ec-ignev-i" title="步速比 = (ret10/10)/(ret50/50)，ig_accel 可读形（显示已 clamp ±20×）">
            <em>step</em>{' '}
            <b style={{ color: (ign.evidence.step_rate_ratio ?? 0) >= 1 ? 'var(--grn)' : 'var(--txt)' }}>
              {fmtStepRate(ign.evidence.step_rate_ratio)}
            </b>
          </span>
          <span className="ec-ignev-i" title="是否收复 MA50（ig_breakout 的 gate：close>MA50）">
            <em>MA50</em>{' '}
            <b style={{ color: ign.evidence.reclaimed_ma50 ? 'var(--grn)' : 'var(--dim)' }}>
              {ign.evidence.reclaimed_ma50 == null ? '—' : ign.evidence.reclaimed_ma50 ? '收复✓' : '未收复'}
            </b>
          </span>
        </div>
      )}

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
