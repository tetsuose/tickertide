import { useEffect, useState } from 'react'
import type { BoardData, Scope, Stock } from '../types'
import { loadBoard } from '../lib/data'
import EvidenceCard from '../components/EvidenceCard'

// Whether a board stock is in the global scope (PRD §9.1.2/§9.3 — filter BEFORE sort).
function inScope(s: Stock, scope: Scope | undefined, pinned: string[]): boolean {
  if (!scope || scope.kind === 'all') return true
  if (scope.kind === 'sector') return s.sector === scope.key
  if (scope.kind === 'theme') return s.themes.some((t) => t.theme === scope.key)
  if (scope.kind === 'pinned') return pinned.includes(s.ticker)
  return true
}

// steady-riser sort key (PRD §10.8.2, 2026-07-02 spine pivot II): Risers is the 连续上涨
// board, NOT a breakout/composite/ignition ranking (all retired, §16). Candidates (the
// compute-layer gate `up10>=0.6 AND net10>0` + net10 top-N — read-only flag, never
// re-derived here, C9) float first, then by net10 (10-day net return) desc. recall-first —
// false positives are expected; fundamentals are the downstream precision stage. Mirrors
// compute/check_ac_m7.py::_riser_key (the AC gate verifies this exact order).
function riserKey(s: Stock): [number, number] {
  const r = s.riser
  return [r?.candidate ? 1 : 0, r?.net10 ?? -Infinity]
}
function byRiser(a: Stock, b: Stock): number {
  const ka = riserKey(a)
  const kb = riserKey(b)
  for (let i = 0; i < 2; i++) if (kb[i] !== ka[i]) return kb[i] - ka[i]
  return 0
}

// Risers（连续上涨）board (PRD §9.3 + §10.8): 2-column evidence-card grid, gate = 10 天里
// ≥6 天上涨且 net10>0, sorted candidate first → net10 desc. This surface is where you
// inspect the SELECTED candidates' price action — equivalent to manually scanning thousands
// of daily charts, with the math doing the pre-screen. Every number on a card is
// chart-verifiable (net5/net10/net20, up-days, in-window drawdown). steady-riser has no
// tunable parameter (PRD §16); smoothness (ker/ddw) is evidence only, never a filter.
// `initial` lets tests/SSR inject the board without fetching. `scope`/`pinned` (App's
// single source) filter BEFORE sort (C10).
export default function Risers({
  initial,
  onOpen,
  scope,
  pinned = [],
  limit,
}: {
  initial?: BoardData
  onOpen?: (ticker: string) => void
  scope?: Scope
  pinned?: string[]
  limit?: number
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

  if (err) {
    return (
      <div className="placeholder">
        <div className="ph-tag">NO DATA</div>
        <div className="ph-msg">
          board.json 未就绪（{err}）。先跑 <code>make fixture-pipeline</code> 或真实 <code>make pipeline</code>，再{' '}
          <code>python export/board.py</code> 生成 web/public/data/board.json。
        </div>
      </div>
    )
  }
  if (!board) {
    return (
      <div className="placeholder">
        <div className="ph-tag">LOADING</div>
        <div className="ph-msg">读取 Risers 快照…</div>
      </div>
    )
  }

  // respect global scope: filter BEFORE sorting (PRD §9.3), then rank candidate → net10
  // desc (recall-first). The flag comes from compute; there is no knob and no re-derivation.
  const shown0 = board.stocks
    .filter((s) => inScope(s, scope, pinned))
    .sort(byRiser)
  // Callers bound the board to a top-N: Risers proper caps at App's RISERS_LIMIT
  // (PRD §9.3 bounded/decide); Rotation's drill drawer previews fewer still (PRD §9.4).
  const shown = limit != null ? shown0.slice(0, limit) : shown0
  const nCand = shown.filter((s) => s.riser?.candidate).length

  return (
    <div className="disco">
      <div className="ecgrid">
        {shown.map((s) => (
          <EvidenceCard key={s.ticker} stock={s} onOpen={onOpen} />
        ))}
      </div>
      <div className="foot">
        <b>连续上涨榜（Risers）</b>（PRD §10.8，核心筛法）：gate = <b>10 天里 ≥6 天上涨且 net10&gt;0</b>，按 <b>10 日净涨幅（net10）</b>
        降序 —— candidate（compute 单一真源 flag，recall-first）置顶。逐张<b>检视入选候选的价格走势</b>，每个数字（net5/net10/net20、
        上涨天数、窗口回撤）都能在 mini-chart 上人工数出来。无可调参（刻意=买 robustness 不买 alpha），平滑度（ker/ddw）只做证据不做过滤，
        <b>假阳交由基本面/财务下游 precision</b>，永不给 buy/target；点卡片任意处 → Stock。 as_of {board.as_of_date} · {shown.length}{' '}
        只（riser 候选 {nCand}）
        {scope && scope.kind !== 'all' ? `（scope=${scope.kind === 'pinned' ? 'pinned' : scope.key} 过滤后）` : ''} · valuation
        覆盖 {board.valuation_coverage}。
      </div>
    </div>
  )
}
