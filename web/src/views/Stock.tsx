import { useEffect, useState } from 'react'
import type { StockBundle, BreakoutFeatures } from '../types'
import { loadStockBundle, loadStockIndex } from '../lib/data'
import StockStack from '../components/StockStack'
import { fmtMktcap, fmtMonthDay, num, pct } from '../lib/format'

// Stock detail (PRD §9.6, M5.4) — per-name, NOT scope-filtered. Reads one lazily-fetched
// bundle (export/stock_bundle.py) for ANY universe ticker, not board.json's top-N. The core
// is the time-aligned price↔fundamentals stack (StockStack: PRICE/VOLUME/REVENUE/P-S sharing
// one x axis with quarter gridlines), upgrading the #53 preview's single MiniChart. `initial`
// injects a bundle for SSR/tests. Same valuation_daily/fundamentals_q as every surface (C9).
// The headline is the ignition read (the core engine); composite is no longer shown (M8).

// base→breakout's 6 dimensionless features (PRD §10.8, ÷ daily-return σ) — the kink the
// changepoint fit found. Shown raw with a short "what it measures" label.
const BRK_FEATURES: { key: keyof BreakoutFeatures; label: string; what: string }[] = [
  { key: 'base_slope', label: 'BASE', what: 'base 段斜率/σ（≈0 = 平台）' },
  { key: 'brk_slope', label: 'BRK', what: 'breakout 段斜率/σ（陡）' },
  { key: 'drift_step', label: 'DRIFT', what: '(s2−s1)/σ 斜率跳变（最强判别，≳0.13）' },
  { key: 'fit_gain', label: 'FIT', what: '1−SSE2/SSE1 拐点显著度（≳0.7）' },
  { key: 'clearance', label: 'CLEAR', what: '清越 base 平台高点（>0 = 已突破）' },
  { key: 'vsurge', label: 'VSURGE', what: '突破段放量（vs base）' },
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
  const brk = bundle.breakout
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
          <div className="stk-tk">{m.ticker}</div>
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
        {/* headline = the base→breakout read (core engine, PRD §10.8). green when a
            base→breakout candidate (top decile, recall-first). composite/ignition gone. */}
        <div className="stk-score" style={{ color: brk?.candidate ? 'var(--score-hi)' : 'var(--txt)' }}>
          <div className="stk-scorev">{brk?.brk_strength_pct == null ? '—' : brk.brk_strength_pct.toFixed(0)}</div>
          <div className="stk-scorel">BRK PCT · 发现核心</div>
        </div>
      </div>

      <div className="stk-stackwrap">
        <StockStack bundle={bundle} />
      </div>

      {/* base/τ/breakout 诊断 (PRD §10.8) — the CORE engine. Bridges the price↔fundamentals
          chart (where the flat base → steep breakout is visible) into 翻财报: base→breakout
          flags "刚从长平台突破"; the user confirms with fundamentals (recall-first, the user IS
          the precision stage). Verbatim from derived_daily (same block as the Breakouts card,
          C9). base→breakout is the core engine and has no tunable parameter (PRD §16). */}
      {brk && (
        <div className="stk-ign">
          <div className="stk-ignt">
            <span className="stk-ignt-l">base→breakout 诊断</span>
            <span className="stk-ignt-r">发现引擎（log 价单变点 τ · 核心 · 无可调参）</span>
          </div>

          {/* recall-first gate: candidate = brk_strength_pct top decile (no persistence). */}
          <div className="stk-ignhead">
            <span
              className={brk.candidate ? 'stk-ignflag on' : 'stk-ignflag'}
              title={
                brk.candidate
                  ? 'base→breakout candidate：强度横截面 top decile（recall-first，无 persistence）'
                  : '未达 base→breakout 门槛（强度 top decile）'
              }
            >
              {brk.candidate ? '🚀 已突破' : '○ 未突破'}
            </span>
            <span className="stk-ignmeta" title="base→breakout 强度的每日横截面 percentile（≥90 = top decile = 已突破）">
              brk_pct <b>{brk.brk_strength_pct == null ? '—' : brk.brk_strength_pct.toFixed(0)}</b>
            </span>
            <span className="stk-ignmeta" title="估计变点 τ（log 价 2 段分段线性拟合的拐点）">
              τ <b>{brk.evidence.tau_date ?? '—'}</b>
            </span>
            <span className="stk-ignmeta" title="(s2−s1)/σ 斜率跳变（最强判别量）">
              drift <b>{brk.evidence.drift_step == null ? '—' : brk.evidence.drift_step.toFixed(2)}</b>
            </span>
          </div>

          {/* base/τ/breakout 证据 — same fields/source as the Breakouts card strip (reused
              .ec-ignev idiom): kink τ + days-since / drift_step / fit_gain / volume surge. */}
          <div className="ec-ignev stk-ignev">
            <span className="ec-ignev-i" title="估计变点 τ（base→breakout 拐点）+ 距今天数">
              <em>τ</em> {fmtMonthDay(brk.evidence.tau_date)}
              {brk.evidence.days_since_tau != null && (
                <i className="ec-ignev-d"> ·{brk.evidence.days_since_tau}d前</i>
              )}
            </span>
            <span className="ec-ignev-i" title="drift_step = (s2−s1)/σ 斜率跳变（≳0.13）">
              <em>drift</em>{' '}
              <b style={{ color: (brk.evidence.drift_step ?? 0) >= 0.13 ? 'var(--grn)' : 'var(--txt)' }}>
                {brk.evidence.drift_step == null ? '—' : brk.evidence.drift_step.toFixed(2)}
              </b>
            </span>
            <span className="ec-ignev-i" title="fit_gain = 1−SSE2/SSE1 拐点显著度（≳0.7）">
              <em>fit</em>{' '}
              <b style={{ color: (brk.evidence.fit_gain ?? 0) >= 0.7 ? 'var(--grn)' : 'var(--txt)' }}>
                {brk.evidence.fit_gain == null ? '—' : brk.evidence.fit_gain.toFixed(2)}
              </b>
            </span>
            <span className="ec-ignev-i" title="突破段放量× = brk_vsurge">
              <em>vol</em>{' '}
              <b style={{ color: (brk.evidence.vol_mult ?? 0) >= 1.5 ? 'var(--grn)' : 'var(--txt)' }}>
                {brk.evidence.vol_mult == null ? '—' : brk.evidence.vol_mult.toFixed(2) + '×'}
              </b>
            </span>
          </div>

          {/* the 6 dimensionless features (PRD §10.8) — what the changepoint fit found. */}
          <div className="stk-igncomp">
            <div className="stk-igncompt">base→breakout 6 无量纲特征（÷ 日收益 σ · log 价单变点 τ 拟合）</div>
            {BRK_FEATURES.map(({ key, label, what }) => {
              const cv = brk.features[key]
              return (
                <div key={key} className="stk-igncrow" title={what}>
                  <span className="stk-igncl">{label}</span>
                  <span className="stk-igncw">{what}</span>
                  <b>{cv == null ? '—' : cv.toFixed(2)}</b>
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
        Stock = evidence card 的展开态（PRD §9.6）· 核心是 price↔fundamentals 时间轴对齐 stack（四格共用 x 轴、季度网格贯穿）：价↑营收平 → P/S 扩 = 变贵无基本面；价↑营收↑ = 赚到这波。头部 + 点火诊断（ignition，§10.8）= 发现核心引擎（短窗口，无可调参）：刚起步在加速 → 翻财报终筛。composite 不再作为用户可见概念（M8）。来自 per-name bundle（懒加载，与 board/Discovery/Ocean/Valuation 同源 C9）。估值口径 = <b>formal-filing PIT</b>：倍数分母只用正式 SEC filing 的 trailing-4Q；REVENUE bar 在 period_end（业务期），P/S 在 effective_eod_date 才阶进（v1 == filed），不用预披露/8-K/分析师预测。最新 filing AI 摘要留后续。as_of {bundle.as_of_date}。
      </div>
    </div>
  )
}
