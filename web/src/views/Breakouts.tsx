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

// base→breakout sort key (PRD §10.8, 2026-06-16 spine pivot): Breakouts is the
// base→breakout board, NOT a composite/ignition ranking. Candidates (top-decile strength)
// float first, then by cross-sectional strength percentile. recall-first — no persistence
// gate (ignition retired); false positives are expected and fundamentals are the downstream
// precision stage. base→breakout is the core engine and has no tunable parameter (PRD §16).
function brkKey(s: Stock): [number, number] {
  const b = s.breakout
  return [b?.candidate ? 1 : 0, b?.brk_strength_pct ?? 0]
}
function byBreakout(a: Stock, b: Stock): number {
  const ka = brkKey(a)
  const kb = brkKey(b)
  for (let i = 0; i < 2; i++) if (kb[i] !== ka[i]) return kb[i] - ka[i]
  return 0
}

// Breakouts board (renamed Discovery, PRD §9.3 + §10.8): 2-column evidence-card grid, sorted
// by base→breakout STRENGTH — candidate first, then brk_strength_pct desc. This surface is
// where you inspect the SELECTED candidates' price action, each card annotated base/τ/breakout
// on its mini-chart. base→breakout is the core engine, no tunable parameter (PRD §16);
// composite/ignition are no longer user-visible concepts. Each card is evidence-first (raw
// numbers + base/τ/breakout 证据 + mini-chart). `initial` lets tests/SSR inject the board
// without fetching. `scope`/`pinned` (App's single source) filter BEFORE sort (C10).
export default function Breakouts({
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
        <div className="ph-msg">读取 Breakouts 快照…</div>
      </div>
    )
  }

  // respect global scope: filter BEFORE sorting (PRD §9.3), then rank by base→breakout
  // strength (recall-first). strength is the order key; there is no composite and no knob.
  const shown0 = board.stocks
    .filter((s) => inScope(s, scope, pinned))
    .sort(byBreakout)
  // Callers bound the board to a top-N: Breakouts proper caps at App's BREAKOUTS_LIMIT
  // (PRD §9.3 bounded/decide); Rotation's drill drawer previews fewer still (PRD §9.4).
  const shown = limit != null ? shown0.slice(0, limit) : shown0
  const nCand = shown.filter((s) => s.breakout?.candidate).length

  return (
    <div className="disco">
      <div className="ecgrid">
        {shown.map((s) => (
          <EvidenceCard key={s.ticker} stock={s} onOpen={onOpen} />
        ))}
      </div>
      <div className="foot">
        <b>突破榜（Breakouts）</b>（PRD §10.8，发现核心引擎）：按 <b>base→breakout 强度</b> 排序 —— candidate（强度 top-decile，
        recall-first）置顶 → 强度百分位。逐张<b>检视入选候选的价格走势</b>，mini-chart 上标注 base / τ / breakout（长平台 → 拐点 →
        陡突破）。base→breakout 无可调参（变点 τ 估计 + 无量纲特征，刻意=买 robustness 不买 alpha），<b>假阳交由基本面/财务下游
        precision</b>，永不给 buy/target；点卡片任意处 → Stock。 as_of {board.as_of_date} · {shown.length} 只（突破候选 {nCand}）
        {scope && scope.kind !== 'all' ? `（scope=${scope.kind === 'pinned' ? 'pinned' : scope.key} 过滤后）` : ''} · valuation
        覆盖 {board.valuation_coverage}。
      </div>
    </div>
  )
}
