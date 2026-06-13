import { useEffect, useState } from 'react'
import type { StockBundle, Components, IgnitionComponents } from '../types'
import { loadStockBundle, loadStockIndex } from '../lib/data'
import { weights, composite } from '../lib/composite'
import StockStack from '../components/StockStack'
import { fmtMktcap, fmtMonthDay, fmtStepRate, num, pct, scoreColor } from '../lib/format'

// Stock detail (PRD §9.6, M5.4) — per-name, NOT scope-filtered. Reads one lazily-fetched
// bundle (export/stock_bundle.py) for ANY universe ticker, not board.json's top-N. The core
// is the time-aligned price↔fundamentals stack (StockStack: PRICE/VOLUME/REVENUE/P-S sharing
// one x axis with quarter gridlines), upgrading the #53 preview's single MiniChart. `initial`
// injects a bundle for SSR/tests. Same valuation_daily/fundamentals_q as every surface (C9).

const COMPONENTS: { key: keyof Components; label: string }[] = [
  { key: 'rs', label: 'RS' },
  { key: 'high', label: '52WH' },
  { key: 'trend', label: 'TREND' },
  { key: 'vol', label: 'VOL' },
  { key: 'accel', label: 'ACCEL' },
]

// ignition's 5 raw self-relative components (PRD §10.8). Unlike composite's c_* ∈ [0,1],
// these are the engine's RAW signals (the [0,1] normalization happens cross-sectionally in
// run.py and is folded into ign_pct) — so we show the raw value + a short "what it measures"
// label, NOT a 0–100% bar (a bar would misrepresent an un-normalized number).
const IGN_COMPONENTS: { key: keyof IgnitionComponents; label: string; what: string }[] = [
  { key: 'accel', label: 'ACCEL', what: '10d–50d 步速比（加速度）' },
  { key: 'expand', label: 'EXPAND', what: '收缩→扩张（波动率展开）' },
  { key: 'vsurge', label: 'VSURGE', what: '放量（5日/60日成交量比）' },
  { key: 'breakout', label: 'BREAKOUT', what: '突破 + 收复 MA50（gate ∈ [0,1]）' },
  { key: 'rsturn', label: 'RSTURN', what: 'RS 拐点（相对强度转向）' },
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

// persistence streak as a discrete day-cell row (newest at right). `days` consecutive lit
// cells (top-decile ign_pct) precede an "今" anchor; capped at TL_MAX so a long streak stays
// a bounded strip. persistence — not an instantaneous spike — is what carries the lift
// (PRD §10.8.2, 实证 analysis/precision_ignition.py), so it gets its own timeline.
const TL_MAX = 10
function PersistTimeline({ days }: { days: number | null }) {
  const n = days ?? 0
  const lit = Math.min(n, TL_MAX)
  const cells = Array.from({ length: TL_MAX }, (_, i) => i < lit) // oldest..newest (left..right)
  return (
    <div className="stk-igntl" title={`持续点火 ${n} 个交易日（连续位于 top decile）`}>
      <span className="stk-igntl-lab">持续</span>
      <span className="stk-igntl-cells">
        {cells.map((on, i) => (
          <i key={i} className={on ? 'stk-igntl-c on' : 'stk-igntl-c'} />
        ))}
      </span>
      <span className="stk-igntl-now">今 · {n}d{n > TL_MAX ? ` (显示末 ${TL_MAX})` : ''}</span>
    </div>
  )
}

export default function Stock({
  initial,
  ticker,
  setTicker,
  k,
}: {
  initial?: StockBundle
  ticker?: string | null
  setTicker?: (t: string) => void
  k?: number
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
  const kEff = k ?? 0.5
  const comps = bundle.components
  const score = comps ? composite(comps, kEff) : (m.composite ?? 0)
  const w = weights(kEff)
  const v = bundle.valuation
  const ign = bundle.ignition
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
        <div className="stk-score" style={{ color: scoreColor(score) }}>
          <div className="stk-scorev">{score.toFixed(0)}</div>
          <div className="stk-scorel">COMPOSITE · k={kEff.toFixed(2)}</div>
        </div>
      </div>

      <div className="stk-stackwrap">
        <StockStack bundle={bundle} />
      </div>

      {/* 点火诊断 (ignition diagnostic, PRD §10.8) — the SECOND engine, parallel to the
          composite stack below. Bridges the price↔fundamentals chart (where the breakout /
          vol surge is visible) into 翻财报: ignition flags "刚起步在加速"; the user confirms
          with fundamentals. Verbatim from derived_daily (same block as the Discovery card, C9);
          the early⟷reliable knob does NOT touch it (PRD P7). */}
      {ign && (
        <div className="stk-ign">
          <div className="stk-ignt">
            <span className="stk-ignt-l">点火诊断 · ignition</span>
            <span className="stk-ignt-r">发现引擎（短窗口 · 不受 k 旋钮影响）</span>
          </div>

          {/* persistence timeline: 持续点火 = top-decile ign_pct sustained ≥persist_min days
              (PRD §10.8.2). This streak — not an instantaneous spike — is the real lift. */}
          <div className="stk-ignhead">
            <span
              className={ign.candidate ? 'stk-ignflag on' : 'stk-ignflag'}
              title={
                ign.candidate
                  ? '持续点火 candidate：横截面 top decile 且持续 ≥5 日'
                  : '未达持续点火门槛（top decile 且持续 ≥5 日）'
              }
            >
              {ign.candidate ? '🔥 持续点火' : '○ 未点火'}
            </span>
            <span className="stk-ignmeta" title="ignition 的每日横截面 percentile（≥90 = top decile = lit）">
              ign_pct <b>{ign.ign_pct == null ? '—' : ign.ign_pct.toFixed(0)}</b>
            </span>
            <span className="stk-ignmeta" title="连续位于 top decile（lit）的交易日数 — persistence 是精度关键">
              持续 <b>{ign.ign_persist_days ?? '—'}</b>d
            </span>
            <span className="stk-ignmeta" title="ignition 综合分 ∈ [0,100]（5 分量横截面 percentile 等权均值）">
              score <b>{ign.ignition == null ? '—' : ign.ignition.toFixed(0)}</b>
            </span>
          </div>

          {/* persistence streak as a discrete day-cell timeline (newest at right). The lit
              cells = the consecutive top-decile days the candidate gate counts. */}
          <PersistTimeline days={ign.ign_persist_days} />

          {/* 点火证据 (ignition evidence) — same fields/source as the Discovery card strip
              (reused .ec-ignev idiom, M7.3): breakout day / vol surge× / step-rate (clamped) /
              reclaimed MA50. vol_mult here is ig_vsurge (5/60 ratio), distinct from the
              valuation card's numbers. */}
          <div className="ec-ignev stk-ignev">
            <span className="ec-ignev-i" title="trailing-60d high（突破参照日）+ 距今天数">
              <em>brk</em> {fmtMonthDay(ign.evidence.breakout_day)}
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

          {/* 5 raw self-relative components (PRD §10.8) — what lit the engine, shown raw
              (NOT a 0–100% bar; only `breakout` is ∈ [0,1]). */}
          <div className="stk-igncomp">
            <div className="stk-igncompt">ignition 5 分量（原始 self-relative · 归一在横截面发生，见 ign_pct）</div>
            {IGN_COMPONENTS.map(({ key, label, what }) => {
              const cv = ign.components[key]
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

      <div className="stk-comp">
        <div className="stk-compt">composite 5 分量（原始值 ∈ [0,1] · 权重随 k）</div>
        {comps &&
          COMPONENTS.map(({ key, label }) => {
            const cv = comps[key]
            const wv = w[key]
            return (
              <div key={key} className="stk-crow">
                <span className="stk-cl">{label}</span>
                <span className="stk-cbar">
                  <span className="stk-cfill" style={{ width: `${Math.round((cv ?? 0) * 100)}%` }} />
                </span>
                <b>{cv == null ? '—' : cv.toFixed(2)}</b>
                <em>{Math.round((wv ?? 0) * 100)}%</em>
              </div>
            )
          })}
      </div>

      <div className="foot">
        Stock = evidence card 的展开态（PRD §9.6）· 核心是 price↔fundamentals 时间轴对齐 stack（四格共用 x 轴、季度网格贯穿）：价↑营收平 → P/S 扩 = 变贵无基本面；价↑营收↑ = 赚到这波。点火诊断（ignition，§10.8）是并列的第二台引擎（发现，短窗口），不受 k 旋钮影响（旋钮只属 composite）：刚起步在加速 → 翻财报终筛。来自 per-name bundle（懒加载，与 board/Discovery/Valuation 同源 C9）。最新 filing AI 摘要留 M5 之后。as_of {bundle.as_of_date}。
      </div>
    </div>
  )
}
