import { useEffect, useState } from 'react'
import type { BoardData, Scope, Stock } from '../types'
import { loadBoard } from '../lib/data'
import { num, pct } from '../lib/format'

// Valuation screener (PRD §9.5, M5 preview). The real M5 surface queries Parquet via
// duckdb-wasm over the full universe; this preview reads the same board.json the other
// surfaces use (C9 — one engine, one snapshot) and renders the cross-section as a
// sortable table. PEG / margin / the duckdb-wasm path land with M5 proper.
//
// Three contract behaviours are real here, not stubbed:
//  - as-of freshness 三档上色 (C7, §10.5): green fresh ≤95d / amber stale ≤160d / red
//    overdue >160d (row dims). The colour is board.py's per-row `freshness`.
//  - common-vintage percentile (§10.5): the pctile column ranks ONLY within the fresh
//    cohort; stale/overdue rows show `vint` and never enter the denominator.
//  - respect + WRITE global scope (§9.1.2): the dropdown is Valuation's scope writer
//    (the 3rd, after Ocean lasso + Rotation click); rows filter to scope BEFORE ranking,
//    so scope changes the percentile denominator.

type MetricKey = 'ps' | 'pe' | 'evs' | 'ev_ebitda' | 'growth' | 'rule40'

// cheapAsc: cheap-on-top multiples ascend; quality metrics (growth, rule40) descend.
const METRICS: { key: MetricKey; label: string; cheapAsc: boolean }[] = [
  { key: 'ps', label: 'P/S', cheapAsc: true },
  { key: 'pe', label: 'P/E', cheapAsc: true },
  { key: 'evs', label: 'EV/S', cheapAsc: true },
  { key: 'ev_ebitda', label: 'EV/EBITDA', cheapAsc: true },
  { key: 'growth', label: 'Grw%', cheapAsc: false },
  { key: 'rule40', label: 'R40', cheapAsc: false },
]

function inScope(s: Stock, scope: Scope | undefined, pinned: string[]): boolean {
  if (!scope || scope.kind === 'all') return true
  if (scope.kind === 'sector') return s.sector === scope.key
  if (scope.kind === 'theme') return s.themes.some((t) => t.theme === scope.key)
  if (scope.kind === 'pinned') return pinned.includes(s.ticker)
  return true
}

const mval = (s: Stock, k: MetricKey): number | null => (s.valuation ? s.valuation[k] : null)
const isFresh = (s: Stock): boolean => s.valuation?.freshness === 'fresh'

export default function Valuation({
  initial,
  scope,
  setScope,
  onOpen,
  pinned = [],
}: {
  initial?: BoardData
  scope?: Scope
  setScope?: (s: Scope) => void
  onOpen?: (ticker: string) => void
  pinned?: string[]
}) {
  const [board, setBoard] = useState<BoardData | null>(initial ?? null)
  const [err, setErr] = useState<string | null>(null)
  const [metricKey, setMetricKey] = useState<MetricKey>('ps')

  useEffect(() => {
    if (initial) return
    const ac = new AbortController()
    loadBoard(ac.signal)
      .then(setBoard)
      .catch((e) => {
        if (!ac.signal.aborted) setErr(String(e))
      })
    return () => ac.abort()
  }, [initial])

  if (err)
    return (
      <div className="placeholder">
        <div className="ph-tag">NO DATA</div>
        <div className="ph-msg">
          board.json 未就绪（{err}）。先跑 <code>make fixture-pipeline</code> 或 <code>make pipeline</code> 再{' '}
          <code>python export/board.py</code>。
        </div>
      </div>
    )
  if (!board)
    return (
      <div className="placeholder">
        <div className="ph-tag">LOADING</div>
        <div className="ph-msg">读取 Valuation 横截面…</div>
      </div>
    )

  const metric = METRICS.find((m) => m.key === metricKey)!
  const sectors = [...new Set(board.stocks.map((s) => s.sector).filter(Boolean))].sort() as string[]
  const themes = [...new Set(board.stocks.flatMap((s) => s.themes.map((t) => t.theme)))].sort()

  // filter to scope FIRST (PRD §9.5), then the percentile cohort is scope-relative.
  const rows = board.stocks.filter((s) => inScope(s, scope, pinned))
  // common-vintage cohort: fresh rows with a value for the active metric.
  const cohort = rows.filter((s) => isFresh(s) && mval(s, metricKey) != null).map((s) => mval(s, metricKey) as number)
  const pctile = (s: Stock): number | null => {
    if (!isFresh(s) || cohort.length === 0) return null
    const v = mval(s, metricKey)
    if (v == null) return null
    const below = cohort.filter((x) => x <= v).length
    return Math.round((below / cohort.length) * 100)
  }

  const sorted = [...rows].sort((a, b) => {
    const av = mval(a, metricKey)
    const bv = mval(b, metricKey)
    if (av == null && bv == null) return 0
    if (av == null) return 1 // nulls last
    if (bv == null) return -1
    return metric.cheapAsc ? av - bv : bv - av
  })

  const scopeValue =
    scope?.kind === 'sector' ? `sector:${scope.key}` : scope?.kind === 'theme' ? `theme:${scope.key}` : 'all'
  const onScope = (v: string) => {
    if (!setScope) return
    if (v === 'all') setScope({ kind: 'all', key: null })
    else if (v.startsWith('sector:')) setScope({ kind: 'sector', key: v.slice(7) })
    else if (v.startsWith('theme:')) setScope({ kind: 'theme', key: v.slice(6) })
  }

  return (
    <div className="valn">
      <div className="valn-ctrl">
        <label>
          scope{' '}
          <select value={scopeValue} onChange={(e) => onScope(e.target.value)}>
            <option value="all">ALL（{board.stocks.length}）</option>
            <optgroup label="sector">
              {sectors.map((s) => (
                <option key={s} value={`sector:${s}`}>
                  {s}
                </option>
              ))}
            </optgroup>
            {themes.length > 0 && (
              <optgroup label="◆ theme">
                {themes.map((t) => (
                  <option key={t} value={`theme:${t}`}>
                    ◆ {t}
                  </option>
                ))}
              </optgroup>
            )}
          </select>
        </label>
        <label>
          sort{' '}
          <select value={metricKey} onChange={(e) => setMetricKey(e.target.value as MetricKey)}>
            {METRICS.map((m) => (
              <option key={m.key} value={m.key}>
                {m.label} {m.cheapAsc ? '↑便宜在上' : '↓高在上'}
              </option>
            ))}
          </select>
        </label>
        <span className="valn-cohort">
          common-vintage cohort（fresh）= {cohort.length} / {rows.length}
        </span>
      </div>

      <div className="valn-tablewrap">
        <table className="valn-table">
          <thead>
            <tr>
              <th className="l">Ticker</th>
              <th className="l">Sector</th>
              <th className="l">As-of</th>
              <th>P/E</th>
              <th>P/S</th>
              <th>EV/S</th>
              <th>EV/EBITDA</th>
              <th>Grw%</th>
              <th>R40</th>
              <th>pctile</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((s) => {
              const v = s.valuation
              const fr = v?.freshness ?? null
              const p = pctile(s)
              return (
                <tr
                  key={s.ticker}
                  className={'valn-row' + (fr ? ' vfr-' + fr : ' vfr-none')}
                  onClick={() => onOpen?.(s.ticker)}
                >
                  <td className="l valn-tk">{s.ticker}</td>
                  <td className="l valn-sec">{s.sector ?? '—'}</td>
                  <td className="l valn-asof">
                    <span className={'vdot ' + (fr ?? 'none')} />
                    {v?.as_of_period_end ?? '—'}
                  </td>
                  <td>{num(v?.pe)}</td>
                  <td className={metricKey === 'ps' ? 'on' : ''}>{num(v?.ps)}</td>
                  <td>{num(v?.evs)}</td>
                  <td>{num(v?.ev_ebitda)}</td>
                  <td>{pct(v?.growth)}</td>
                  <td>{num(v?.rule40)}</td>
                  <td className="valn-pct">{p == null ? <span className="vint">vint</span> : p}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <div className="foot">
        横截面 screener（PRD §9.5）· 排序：{metric.label}（{metric.cheapAsc ? '便宜在上' : '高在上'}）· as-of 三档：
        <span className="vfr-inline vfr-fresh">fresh ≤95d</span>
        <span className="vfr-inline vfr-stale">stale ≤160d</span>
        <span className="vfr-inline vfr-overdue">overdue &gt;160d（行变暗）</span>
        · pctile 仅在 fresh cohort 内排（common-vintage，§10.5），stale 行显 <code>vint</code> 不进分母 · scope 下拉 = 全局
        writer（Valuation 是第 3 个）。点行 → Stock。
        <br />
        预览读 board.json（与 Discovery/Ocean 同源 C9）；正式 M5 走 duckdb-wasm 全 universe 横截面 + PEG/margin。as_of {board.as_of_date}。
      </div>
    </div>
  )
}
