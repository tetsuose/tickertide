import { useEffect, useState } from 'react'
import type { StockBundle, Components } from '../types'
import { loadStockBundle, loadStockIndex } from '../lib/data'
import { weights, composite } from '../lib/composite'
import StockStack from '../components/StockStack'
import { fmtMktcap, num, pct, scoreColor } from '../lib/format'

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
        Stock = evidence card 的展开态（PRD §9.6）· 核心是 price↔fundamentals 时间轴对齐 stack（四格共用 x 轴、季度网格贯穿）：价↑营收平 → P/S 扩 = 变贵无基本面；价↑营收↑ = 赚到这波。来自 per-name bundle（懒加载，与 board/Valuation 同源 C9）。最新 filing AI 摘要留 M5 之后。as_of {bundle.as_of_date}。
      </div>
    </div>
  )
}
