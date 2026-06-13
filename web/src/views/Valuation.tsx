import { useEffect, useState } from 'react'
import type { Scope, ValuationRow } from '../types'
import { queryValuation, VALUATION_METRICS, type MetricKey } from '../lib/duckdb'
import { num, pct } from '../lib/format'

// Valuation screener (PRD §9.5, M5.2). The FULL-universe cross-section, read from
// valuation.parquet by duckdb-wasm in the browser (lib/duckdb.ts): duckdb does the metric
// ORDER BY, this view does scope filter + common-vintage percentile + as-of tri-color.
// `initial` injects rows for SSR/tests (no wasm); there the sort runs in JS so the same
// table renders identically. Same valuation_daily as board.json (C9); PEG/Mgn% are the two
// columns the #53 preview couldn't show (board.json never exported them).

function inScope(r: ValuationRow, scope: Scope | undefined, pinned: string[]): boolean {
  if (!scope || scope.kind === 'all') return true
  if (scope.kind === 'sector') return r.sector === scope.key
  if (scope.kind === 'theme') return r.themes ? r.themes.split(',').includes(scope.key) : false
  if (scope.kind === 'pinned') return pinned.includes(r.ticker)
  return true
}

const mval = (r: ValuationRow, k: MetricKey): number | null => (r[k] as number | null) ?? null

/** Pure JS sort matching buildValuationSql (cheap-asc / quality-desc, NULLs last). Used in
 *  the injected/SSR path; the duckdb path returns rows already sorted by the same rule. */
function sortRows(rows: ValuationRow[], metric: MetricKey): ValuationRow[] {
  const m = VALUATION_METRICS.find((x) => x.key === metric) ?? VALUATION_METRICS[0]
  return [...rows].sort((a, b) => {
    const av = mval(a, metric)
    const bv = mval(b, metric)
    if (av == null && bv == null) return a.ticker < b.ticker ? -1 : 1
    if (av == null) return 1
    if (bv == null) return -1
    return m.cheapAsc ? av - bv : bv - av
  })
}

export default function Valuation({
  initial,
  scope,
  setScope,
  onOpen,
  pinned = [],
}: {
  initial?: ValuationRow[]
  scope?: Scope
  setScope?: (s: Scope) => void
  onOpen?: (ticker: string) => void
  pinned?: string[]
}) {
  const [metric, setMetric] = useState<MetricKey>('ps')
  const [rows, setRows] = useState<ValuationRow[] | null>(initial ?? null)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    if (initial) return // injected (SSR/tests): skip duckdb-wasm
    let alive = true
    setRows(null)
    queryValuation(metric)
      .then((r) => alive && setRows(r))
      .catch((e) => alive && setErr(String(e)))
    return () => {
      alive = false
    }
  }, [initial, metric])

  if (err)
    return (
      <div className="placeholder">
        <div className="ph-tag">NO DATA</div>
        <div className="ph-msg">
          valuation.parquet 未就绪（{err}）。先跑 <code>make export</code> 产出 web/public/data/valuation.parquet。
        </div>
      </div>
    )
  if (!rows)
    return (
      <div className="placeholder">
        <div className="ph-tag">LOADING</div>
        <div className="ph-msg">duckdb-wasm 读取 Valuation 横截面…</div>
      </div>
    )

  const m = VALUATION_METRICS.find((x) => x.key === metric)!
  // duckdb pre-sorts; the injected path sorts in JS so both render identically.
  const sorted = initial ? sortRows(rows, metric) : rows
  const sectors = [...new Set(rows.map((r) => r.sector).filter(Boolean))].sort() as string[]
  const themes = [...new Set(rows.flatMap((r) => (r.themes ? r.themes.split(',') : [])))].sort()

  // filter to scope FIRST (PRD §9.5), then the percentile cohort is scope-relative.
  const filtered = sorted.filter((r) => inScope(r, scope, pinned))
  const cohort = filtered
    .filter((r) => r.freshness === 'fresh' && mval(r, metric) != null)
    .map((r) => mval(r, metric) as number)
  const pctile = (r: ValuationRow): number | null => {
    if (r.freshness !== 'fresh' || cohort.length === 0) return null
    const v = mval(r, metric)
    if (v == null) return null
    return Math.round((cohort.filter((x) => x <= v).length / cohort.length) * 100)
  }

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
            <option value="all">ALL（{rows.length}）</option>
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
          <select value={metric} onChange={(e) => setMetric(e.target.value as MetricKey)}>
            {VALUATION_METRICS.map((x) => (
              <option key={x.key} value={x.key}>
                {x.label} {x.cheapAsc ? '↑便宜在上' : '↓高在上'}
              </option>
            ))}
          </select>
        </label>
        <span className="valn-cohort">
          duckdb-wasm · common-vintage cohort（fresh）= {cohort.length} / {filtered.length}
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
              <th>PEG</th>
              <th>Grw%</th>
              <th>Mgn%</th>
              <th>R40</th>
              <th>pctile</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((r) => {
              const fr = r.freshness
              const p = pctile(r)
              return (
                <tr
                  key={r.ticker}
                  className={'valn-row' + (fr ? ' vfr-' + fr : ' vfr-none')}
                  onClick={() => onOpen?.(r.ticker)}
                >
                  <td className="l valn-tk">{r.ticker}</td>
                  <td className="l valn-sec">{r.sector ?? '—'}</td>
                  <td className="l valn-asof">
                    <span className={'vdot ' + (fr ?? 'none')} />
                    {r.as_of_period_end ?? '—'}
                  </td>
                  <td>{num(r.pe)}</td>
                  <td className={metric === 'ps' ? 'on' : ''}>{num(r.ps)}</td>
                  <td>{num(r.evs)}</td>
                  <td>{num(r.ev_ebitda)}</td>
                  <td>{num(r.peg)}</td>
                  <td>{pct(r.growth)}</td>
                  <td>{r.margin == null ? '—' : pct(r.margin)}</td>
                  <td>{num(r.rule40)}</td>
                  <td className="valn-pct">{p == null ? <span className="vint">vint</span> : p}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <div className="foot">
        全 universe 横截面 screener（PRD §9.5）· <b>duckdb-wasm 浏览器查 valuation.parquet</b> · 排序：{m.label}（
        {m.cheapAsc ? '便宜在上' : '高在上'}）· as-of 三档：
        <span className="vfr-inline vfr-fresh">fresh ≤95d</span>
        <span className="vfr-inline vfr-stale">stale ≤160d</span>
        <span className="vfr-inline vfr-overdue">overdue &gt;160d（行变暗）</span>
        · pctile 仅在 fresh cohort 内排（common-vintage，§10.5），stale 行显 <code>vint</code> 不进分母 · scope 下拉 = 全局
        writer（先 filter 再排序再 pctile）。点行 → Stock。读同一 valuation_daily（与 board/Ocean 同源 C9）。
      </div>
    </div>
  )
}
