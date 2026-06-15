import { useEffect, useState } from 'react'
import type { Stock, ChartSeries } from '../types'
import MiniChart from './MiniChart'
import { loadBoardChart } from '../lib/data'

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

// evidence-card = the collapsed state of a Stock (PRD §9.1.3): scannable raw facts,
// ignition-first. Composite is NO LONGER shown (M8 — composite is not a user-visible
// concept). The card header surfaces the 持续点火 state; the 点火证据 strip + the 6 raw
// evidence numbers + the mini-chart carry the rest. Click anywhere → open Stock.
export default function EvidenceCard({
  stock,
  onOpen,
  chart: chartProp,
}: {
  stock: Stock
  onOpen?: (ticker: string) => void
  /** Injected chart — SSR/tests pass it to skip the fetch. In the browser the card lazily
   *  fetches its own ~90d mini-chart (schema v2 split) so the bulk board.json stays tiny. */
  chart?: ChartSeries
}) {
  const e = stock.evidence
  const ign = stock.ignition

  // schema v2 payload split: the mini-chart is NOT in the bulk board.json — fetch this card's
  // chart on render (board/<ticker>.json). Chart source priority: injected prop (SSR/tests) →
  // inline chart on the bulk stock (transitional fallback: a stale v1 data artifact still
  // carries it, so no 404) → lazy fetch. A pending/failed fetch just shows a fixed-height
  // skeleton (the card's text evidence renders regardless — the chart is supplementary). §9.3.
  const inline = chartProp ?? stock.chart ?? null
  const [chart, setChart] = useState<ChartSeries | null>(inline)
  useEffect(() => {
    if (inline) {
      setChart(inline)
      return
    }
    const ac = new AbortController()
    loadBoardChart(stock.ticker, ac.signal)
      .then((d) => setChart(d.chart))
      .catch(() => {
        /* leave the skeleton in place; the chart is supplementary, never blocks the card */
      })
    return () => ac.abort()
  }, [stock.ticker, inline])

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
              = top-decile ign_pct AND sustained ≥persist_min days. When not a candidate, a
              dim ign_pct chip still gives the ignition read (composite badge is gone, M8). */}
          {ign?.candidate ? (
            <span
              className="ec-ign"
              title={`持续点火 candidate: ign_pct ${ign.ign_pct?.toFixed(0)} · 持续 ${ign.ign_persist_days}d`}
            >
              🔥 {ign.ign_persist_days}d
            </span>
          ) : ign?.ign_pct != null ? (
            <span className="ec-ignpct" title="ignition 横截面百分位（≥90 = 海平面以上 = 点亮）">
              ign {ign.ign_pct.toFixed(0)}
            </span>
          ) : null}
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

      <div className="ec-chart">
        {chart ? <MiniChart chart={chart} /> : <div className="ec-chart-skel" aria-hidden="true" />}
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
