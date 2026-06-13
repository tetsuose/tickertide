import { useEffect, useState } from 'react'
import type { BoardData, Components, Stock as StockT } from '../types'
import { loadBoard } from '../lib/data'
import { weights, composite } from '../lib/composite'
import MiniChart from '../components/MiniChart'
import { fmtMktcap, num, pct, scoreColor } from '../lib/format'

// Stock detail (PRD §9.6, M5 preview) — the expanded state of an evidence card, per-name
// and NOT scope-filtered (§9.1.2: Stock is per-name). board.json carries everything this
// preview needs (header identity + theme chips with exposure, the price/MA/volume mini
// chart, the 6 valuation multiples, the 5 composite components), so it ships now and stays
// C9-consistent with every other surface. The full §9.6 contract — the time-aligned
// price↔fundamentals stack (quarterly revenue bars + daily P/S-over-time, sharing one x
// axis) and the filing AI summary — needs new per-name export data and lands with M5.

const COMPONENTS: { key: keyof Components; label: string }[] = [
  { key: 'rs', label: 'RS' },
  { key: 'high', label: '52WH' },
  { key: 'trend', label: 'TREND' },
  { key: 'vol', label: 'VOL' },
  { key: 'accel', label: 'ACCEL' },
]

const VAL_CARDS: { key: keyof NonNullable<StockT['valuation']>; label: string; kind: 'num' | 'pct' }[] = [
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
  initial?: BoardData
  ticker?: string | null
  setTicker?: (t: string) => void
  k?: number
}) {
  const [board, setBoard] = useState<BoardData | null>(initial ?? null)
  const [err, setErr] = useState<string | null>(null)

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
        <div className="ph-msg">读取 Stock…</div>
      </div>
    )

  // per-name: the requested ticker, else the top-composite name as a sensible default.
  const s = board.stocks.find((t) => t.ticker === ticker) ?? board.stocks[0]
  if (!s)
    return (
      <div className="placeholder">
        <div className="ph-tag">EMPTY</div>
        <div className="ph-msg">board.json 无个股。</div>
      </div>
    )

  const kEff = k ?? board.knob_default_k
  const w = weights(kEff)
  const score = composite(s.components, kEff)
  const v = s.valuation
  const tickers = [...board.stocks].map((t) => t.ticker).sort()

  return (
    <div className="stk">
      <div className="stk-top">
        <label>
          ticker{' '}
          <select value={s.ticker} onChange={(e) => setTicker?.(e.target.value)}>
            {tickers.map((t) => (
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
          <div className="stk-tk">{s.ticker}</div>
          <div className="stk-sec">
            {s.sector ?? '—'} · {fmtMktcap(s.mktcap)}
          </div>
          {s.themes.length > 0 && (
            <div className="stk-themes">
              {s.themes.map((t) => (
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

      <div className="stk-chart">
        <MiniChart chart={s.chart} />
      </div>

      <div className="stk-vals">
        {VAL_CARDS.map(({ key, label, kind }) => (
          <div key={key} className="stk-vcard">
            <span className="stk-vl">{label}</span>
            <b className="stk-vv">{v == null ? '—' : kind === 'pct' ? pct(v[key] as number | null) : num(v[key] as number | null)}</b>
          </div>
        ))}
      </div>

      <div className="stk-comp">
        <div className="stk-compt">composite 5 分量（原始值 ∈ [0,1] · 权重随 k）</div>
        {COMPONENTS.map(({ key, label }) => {
          const cv = s.components[key]
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
        Stock = evidence card 的展开态（PRD §9.6）· 头部 + 价格/MA/成交量图 + 6 估值倍数 + 5 分量，全部来自 board.json（与
        Discovery/Ocean/Valuation 同源 C9）。
        <br />
        正式 M5 补：price↔fundamentals 时间轴对齐 stack（季度营收 bars + 每日 P/S over time，共用 x 轴）+ 最新 filing AI
        摘要——需 per-name 导出新数据。as_of {board.as_of_date}。
      </div>
    </div>
  )
}
