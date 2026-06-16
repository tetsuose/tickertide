import { useEffect, useState } from 'react'
import type { Stock, ChartSeries } from '../types'
import MiniChart from './MiniChart'
import { loadBoardChart } from '../lib/data'

const fmtDate = (d: string | null): string => (d == null ? '—' : d.slice(5)) // MM-DD
const fmtNum = (v: number | null, nd = 2): string => (v == null ? '—' : v.toFixed(nd))

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
// base→breakout-first (2026-06-16 spine pivot — ignition retired; composite is not a
// user-visible concept). The card header surfaces the base→breakout state; the base/τ/breakout
// 证据 strip + the 6 raw evidence numbers + the mini-chart carry the rest. Click → open Stock.
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
  const brk = stock.breakout

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
          {/* base→breakout badge: this IS the Breakouts sort signal (PRD §10.8). candidate
              = brk_strength_pct top decile (recall-first, no persistence). When not a candidate,
              a dim brk_pct chip still gives the breakout read (composite/ignition are gone). */}
          {brk?.candidate ? (
            <span
              className="ec-ign"
              title={`突破候选: brk_pct ${brk.brk_strength_pct?.toFixed(0)} · τ ${brk.evidence.tau_date ?? '—'}`}
            >
              🚀 {brk.evidence.days_since_tau != null ? `${brk.evidence.days_since_tau}d` : '突破'}
            </span>
          ) : brk?.brk_strength_pct != null ? (
            <span className="ec-ignpct" title="base→breakout 强度横截面百分位（≥90 = 海平面以上 = 已突破）">
              brk {brk.brk_strength_pct.toFixed(0)}
            </span>
          ) : null}
        </div>
      </div>

      {/* base/τ/breakout 证据 (PRD §10.8) — the card's primary read on the breakout board:
          estimated kink τ + days-since / drift_step (slope jump) / fit_gain (kink salience) /
          breakout-side volume surge. Same source as the chart bars (C9). vol_mult here is
          brk_vsurge, distinct from the 50d vol_mult in the field strip below. */}
      {brk && (
        <div className="ec-ignev">
          <span className="ec-ignev-i" title="估计变点 τ（base→breakout 拐点）+ 距今天数">
            <em>τ</em> {fmtDate(brk.evidence.tau_date)}
            {brk.evidence.days_since_tau != null && (
              <i className="ec-ignev-d"> ·{brk.evidence.days_since_tau}d前</i>
            )}
          </span>
          <span className="ec-ignev-i" title="drift_step = (s2−s1)/σ，斜率跳变（最强判别，≳0.13）">
            <em>drift</em>{' '}
            <b style={{ color: (brk.evidence.drift_step ?? 0) >= 0.13 ? 'var(--grn)' : 'var(--txt)' }}>
              {fmtNum(brk.evidence.drift_step)}
            </b>
          </span>
          <span className="ec-ignev-i" title="fit_gain = 1−SSE2/SSE1，拐点显著度（≳0.7）">
            <em>fit</em>{' '}
            <b style={{ color: (brk.evidence.fit_gain ?? 0) >= 0.7 ? 'var(--grn)' : 'var(--txt)' }}>
              {fmtNum(brk.evidence.fit_gain)}
            </b>
          </span>
          <span className="ec-ignev-i" title="突破段放量× = brk_vsurge">
            <em>vol</em>{' '}
            <b style={{ color: (brk.evidence.vol_mult ?? 0) >= 1.5 ? 'var(--grn)' : 'var(--txt)' }}>
              {brk.evidence.vol_mult == null ? '—' : brk.evidence.vol_mult.toFixed(2) + '×'}
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
