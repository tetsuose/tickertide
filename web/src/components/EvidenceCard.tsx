import { useEffect, useState } from 'react'
import type { Stock, ChartSeries } from '../types'
import MiniChart from './MiniChart'
import { loadBoardChart } from '../lib/data'

function fmtMktcap(v: number | null): string {
  if (v == null) return '—'
  if (v >= 1e12) return '$' + (v / 1e12).toFixed(1) + 'T'
  if (v >= 1e9) return '$' + (v / 1e9).toFixed(1) + 'B'
  if (v >= 1e6) return '$' + (v / 1e6).toFixed(0) + 'M'
  return '$' + v.toFixed(0)
}

const pct = (v: number | null): string =>
  v == null ? '—' : (v >= 0 ? '+' : '') + (v * 100).toFixed(1) + '%'

// The steady-riser window (W=10 trading days, PRD §10.8) — highlighted on the mini-chart so
// every riser number (net10 / up-days / in-window drawdown) is countable inside the band.
const RISER_WINDOW = 10

// evidence-card = the collapsed state of a Stock (PRD §9.1.3): scannable raw facts,
// steady-riser-first (2026-07-02 spine pivot II — base→breakout retired; composite/ignition
// are not user-visible concepts). The card header surfaces the riser state (candidate 📈 +
// 连续在榜 N 天, else a dim net10 chip); the riser evidence fields (net5/net10/net20, up-days,
// in-window drawdown, vol×) + the mini-chart (last-10d window highlighted) carry the rest —
// every number is countable on the chart. Click → open Stock.
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
  const r = stock.riser

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
          <span title={stock.name ?? undefined}>{stock.ticker}</span>{' '}
          <span className="ec-sec">
            {stock.sector ?? '—'} · {fmtMktcap(stock.mktcap)}
          </span>
        </div>
        <div className="ec-headr">
          {/* steady-riser badge: this IS the Risers sort signal (PRD §10.8). candidate =
              the compute-layer gate + top-N flag (read-only, C9 — never re-derived here).
              When not a candidate, a dim net10 chip still gives the riser read. */}
          {r?.candidate ? (
            <span
              className="ec-ign"
              title={`连续上涨候选: net10 ${pct(r.net10)} · 连续在榜 ${r.streak_days ?? '—'} 天`}
            >
              📈 {r.streak_days != null ? `在榜${r.streak_days}d` : '连续上涨'}
            </span>
          ) : r?.net10 != null ? (
            <span className="ec-ignpct" title="10 日净涨幅（steady-riser 排序键；candidate 由 compute 层判定，非阈值推导）">
              10d {pct(r.net10)}
            </span>
          ) : null}
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

      <div className="ec-chart">
        {chart ? (
          <MiniChart chart={chart} hlLastN={RISER_WINDOW} />
        ) : (
          <div className="ec-chart-skel" aria-hidden="true" />
        )}
      </div>

      {/* riser evidence fields (PRD §9.3/§10.8) — every number countable inside the
          highlighted 10-day window on the chart above (C9). 涨绿跌红. */}
      <div className="ec-fields">
        <div className="ec-f" title="5 日净涨幅">
          <span>5d</span>
          <b style={{ color: (r?.net5 ?? 0) >= 0 ? 'var(--grn)' : 'var(--red)' }}>{pct(r?.net5 ?? null)}</b>
        </div>
        <div className="ec-f" title="10 日净涨幅（排序键）">
          <span>10d</span>
          <b style={{ color: (r?.net10 ?? 0) >= 0 ? 'var(--grn)' : 'var(--red)' }}>{pct(r?.net10 ?? null)}</b>
        </div>
        <div className="ec-f" title="20 日净涨幅">
          <span>20d</span>
          <b style={{ color: (r?.net20 ?? 0) >= 0 ? 'var(--grn)' : 'var(--red)' }}>{pct(r?.net20 ?? null)}</b>
        </div>
        <div className="ec-f" title="10 天里上涨天数（gate: ≥6/10）">
          <span>上涨天数</span>
          <b style={{ color: (r?.up10 ?? 0) >= 0.6 ? 'var(--grn)' : 'var(--txt)' }}>
            {r?.up10 == null ? '—' : `${Math.round(r.up10 * 10)}/10`}
          </b>
        </div>
        <div className="ec-f" title="10 日窗口内最大回撤（证据列，不做过滤）">
          <span>回撤</span>
          <b style={{ color: 'var(--txt)' }}>{r?.ddw10 == null ? '—' : (r.ddw10 * 100).toFixed(1) + '%'}</b>
        </div>
        <div className="ec-f" title="50 日均量放大倍数">
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
