import { useEffect, useState } from 'react'
import type { StockBundle, RiserBlock } from '../types'
import { loadStockBundle, loadStockIndex } from '../lib/data'
import StockStack from '../components/StockStack'
import { fmtMktcap, num, pct } from '../lib/format'

// Stock detail (PRD §9.6, M5.4) — per-name, NOT scope-filtered. Reads one lazily-fetched
// bundle (export/stock_bundle.py) for ANY universe ticker, not board.json's top-N. The core
// is the time-aligned price↔fundamentals stack (StockStack: PRICE/VOLUME/REVENUE/P-S sharing
// one x axis with quarter gridlines), upgrading the #53 preview's single MiniChart. `initial`
// injects a bundle for SSR/tests. Same valuation_daily/fundamentals_q as every surface (C9).
// The headline is the steady-riser read (the core screen, 2026-07-02 spine pivot II);
// composite/ignition/base→breakout are no longer shown.

// steady-riser evidence rows (PRD §10.8, W=10 window) — every value is countable on the
// price chart above. Shown raw with a short "what it measures" label. Smoothness (ker/ddw)
// is evidence only, never a filter.
const RISER_ROWS: { key: keyof RiserBlock; label: string; what: string; fmt: (v: number) => string }[] = [
  { key: 'net5', label: 'NET5', what: '5 日净涨幅', fmt: (v) => pct(v) },
  { key: 'net10', label: 'NET10', what: '10 日净涨幅（排序键）', fmt: (v) => pct(v) },
  { key: 'net20', label: 'NET20', what: '20 日净涨幅', fmt: (v) => pct(v) },
  { key: 'up10', label: 'UP10', what: '10 天里上涨天数（gate: ≥6/10）', fmt: (v) => `${Math.round(v * 10)}/10` },
  { key: 'ddw10', label: 'DDW10', what: '10 日窗口内最大回撤（证据列，不做过滤）', fmt: (v) => (v * 100).toFixed(1) + '%' },
  { key: 'ker10', label: 'KER10', what: '路径效率（证据列，不做过滤）', fmt: (v) => v.toFixed(2) },
  { key: 'net10_pct', label: 'NET10 PCT', what: 'net10 横截面百分位（Ocean 纵轴）', fmt: (v) => v.toFixed(0) },
  { key: 'streak_days', label: 'STREAK', what: '连续在榜天数', fmt: (v) => `${v}d` },
]

type ValKey = 'ps' | 'evs' | 'ev_ebitda' | 'pe' | 'growth' | 'rule40'
const VAL_CARDS: { key: ValKey; label: string; kind: 'num' | 'pct' }[] = [
  { key: 'ps', label: 'P/S', kind: 'num' },
  { key: 'evs', label: 'EV/S', kind: 'num' },
  { key: 'ev_ebitda', label: 'EV/EBITDA', kind: 'num' },
  { key: 'pe', label: 'P/E', kind: 'num' },
  { key: 'growth', label: 'Rev growth', kind: 'pct' },
  { key: 'rule40', label: 'Rule of 40', kind: 'num' },
]

export default function Stock({
  initial,
  ticker,
  setTicker,
}: {
  initial?: StockBundle
  ticker?: string | null
  setTicker?: (t: string) => void
}) {
  const [bundle, setBundle] = useState<StockBundle | null>(initial ?? null)
  const [tickers, setTickers] = useState<string[]>(initial ? [initial.meta.ticker] : [])
  const [err, setErr] = useState<string | null>(null)

  // index once: the per-name ticker dropdown
  useEffect(() => {
    if (initial) return
    const ac = new AbortController()
    loadStockIndex(ac.signal)
      .then((idx) => setTickers(idx.tickers))
      .catch(() => {})
    return () => ac.abort()
  }, [initial])

  // bundle whenever the selected ticker (or the default first) changes
  useEffect(() => {
    if (initial) return
    const t = ticker ?? tickers[0]
    if (!t) return
    const ac = new AbortController()
    setBundle(null)
    setErr(null)
    loadStockBundle(t, ac.signal)
      .then((b) => setBundle(b))
      .catch((e) => {
        if (!ac.signal.aborted) setErr(String(e))
      })
    return () => ac.abort()
  }, [initial, ticker, tickers])

  if (err)
    return (
      <div className="placeholder">
        <div className="ph-tag">NO DATA</div>
        <div className="ph-msg">
          stock bundle 未就绪（{err}）。先跑 <code>make export</code> 产出 web/public/data/stock/。
        </div>
      </div>
    )
  if (!bundle)
    return (
      <div className="placeholder">
        <div className="ph-tag">LOADING</div>
        <div className="ph-msg">读取 Stock…</div>
      </div>
    )

  const m = bundle.meta
  const v = bundle.valuation
  const r = bundle.riser
  const opts = tickers.length ? tickers : [m.ticker]

  return (
    <div className="stk">
      <div className="stk-top">
        <label>
          ticker{' '}
          <select value={m.ticker} onChange={(e) => setTicker?.(e.target.value)}>
            {opts.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </label>
        <span className="stk-pernote">per-name · 不受 scope 影响（PRD §9.1.2）</span>
      </div>

      <div className="stk-head">
        <div className="stk-id">
          <div className="stk-tk">
            {m.ticker}
            {m.name && <span className="stk-name">{m.name}</span>}
          </div>
          <div className="stk-sec">
            {m.sector ?? '—'} · {fmtMktcap(m.mktcap)}
          </div>
          {m.themes.length > 0 && (
            <div className="stk-themes">
              {m.themes.map((t) => (
                <span key={t.theme} className="stk-chip" style={{ color: `var(--th-${t.theme.toLowerCase()}, var(--dim))` }}>
                  {t.theme}
                  {t.exposure != null && <em>{(t.exposure * 100).toFixed(0)}%</em>}
                </span>
              ))}
            </div>
          )}
        </div>
        {/* headline = the steady-riser read (core screen, PRD §10.8). green when a riser
            candidate (compute-layer flag, recall-first). composite/ignition/breakout gone. */}
        <div className="stk-score" style={{ color: r?.candidate ? 'var(--score-hi)' : 'var(--txt)' }}>
          <div className="stk-scorev">{r?.net10 == null ? '—' : pct(r.net10)}</div>
          <div className="stk-scorel">10 日净涨幅 · 核心筛法</div>
        </div>
      </div>

      <div className="stk-stackwrap">
        <StockStack bundle={bundle} />
      </div>

      {/* riser 诊断 (PRD §10.8) — the CORE screen. Bridges the price↔fundamentals chart
          (where the last-2-weeks steady rise is countable) into 翻财报: steady-riser flags
          "过去两周持续走高"; the user confirms with fundamentals (recall-first, the user IS
          the precision stage). Verbatim from derived_daily (same block as the Risers card,
          C9). candidate is compute's read-only flag — never re-derived here (PRD §16). */}
      {r && (
        <div className="stk-ign">
          <div className="stk-ignt">
            <span className="stk-ignt-l">riser 诊断</span>
            <span className="stk-ignt-r">核心筛法（10 天里 ≥6 天上涨且 net10&gt;0 · 无可调参）</span>
          </div>

          {/* recall-first gate: candidate = compute-layer gate + net10 top-N (read-only). */}
          <div className="stk-ignhead">
            <span
              className={r.candidate ? 'stk-ignflag on' : 'stk-ignflag'}
              title={
                r.candidate
                  ? 'steady-riser candidate：gate（10 天里 ≥6 天上涨且 net10>0）+ net10 top-N（recall-first；flag 由 compute 层判定）'
                  : '未入选 Risers 榜（gate + net10 top-N，flag 由 compute 层判定）'
              }
            >
              {r.candidate ? '📈 连续上涨' : '○ 未入选'}
            </span>
            <span className="stk-ignmeta" title="10 日净涨幅（Risers 排序键）">
              net10 <b>{r.net10 == null ? '—' : pct(r.net10)}</b>
            </span>
            <span className="stk-ignmeta" title="10 天里上涨天数（gate: ≥6/10）">
              上涨天数 <b>{r.up10 == null ? '—' : `${Math.round(r.up10 * 10)}/10`}</b>
            </span>
            <span className="stk-ignmeta" title="连续在榜天数">
              连续在榜 <b>{r.streak_days == null ? '—' : `${r.streak_days}d`}</b>
            </span>
          </div>

          {/* the riser evidence rows (PRD §10.8) — all countable on the chart above. */}
          <div className="stk-igncomp">
            <div className="stk-igncompt">steady-riser 证据（W=10 主窗 · 全部图上可数 · 平滑度只做证据不做过滤）</div>
            {RISER_ROWS.map(({ key, label, what, fmt }) => {
              const cv = r[key]
              return (
                <div key={key} className="stk-igncrow" title={what}>
                  <span className="stk-igncl">{label}</span>
                  <span className="stk-igncw">{what}</span>
                  <b>{typeof cv === 'number' ? fmt(cv) : '—'}</b>
                </div>
              )
            })}
          </div>
        </div>
      )}

      <div className="stk-vals">
        {VAL_CARDS.map(({ key, label, kind }) => (
          <div key={key} className="stk-vcard">
            <span className="stk-vl">{label}</span>
            <b className="stk-vv">{v == null ? '—' : kind === 'pct' ? pct(v[key]) : num(v[key])}</b>
          </div>
        ))}
      </div>

      {/* formal-filing PIT (PRD §10.5): which fiscal quarter these multiples use, and when it
          formally entered the daily valuation series (v1: effective == filed). period_end is the
          business period, NOT a market-known date. */}
      {v && (
        <div className="stk-valbasis" style={{ fontSize: '10px', color: 'var(--dim)', fontFamily: 'var(--mono)', marginTop: '2px' }}>
          估值口径 <b style={{ color: 'var(--dim2)' }}>formal-filing PIT</b> · 财季 {v.as_of_period_end ?? '—'}
          {v.as_of_filed && <> · 正式披露 {v.as_of_filed}</>}
          {v.as_of_effective_eod && <> · 入估值序列 {v.as_of_effective_eod}</>}
          {v.disclosure_lag_days != null && <> · 披露滞后 {v.disclosure_lag_days}d</>}
        </div>
      )}

      <div className="foot">
        Stock = evidence card 的展开态（PRD §9.6）· 核心是 price↔fundamentals 时间轴对齐 stack（四格共用 x 轴、季度网格贯穿）：价↑营收平 → P/S 扩 = 变贵无基本面；价↑营收↑ = 赚到这波。头部 + riser 证据（steady-riser，§10.8）= 核心筛法（W=10 窗口，无可调参，每个数字图上可数）：过去两周持续走高 → 翻财报终筛。composite/ignition/base→breakout 均已退役（§16）。来自 per-name bundle（懒加载，与 board/Risers/Ocean/Valuation 同源 C9）。估值口径 = <b>formal-filing PIT</b>：倍数分母只用正式 SEC filing 的 trailing-4Q；REVENUE bar 在 period_end（业务期），P/S 在 effective_eod_date 才阶进（v1 == filed），不用预披露/8-K/分析师预测。最新 filing AI 摘要留后续。as_of {bundle.as_of_date}。
      </div>
    </div>
  )
}
