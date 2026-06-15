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

// Sustained-ignition sort key (PRD §10.8.2, M7.3): Discovery is the 持续点火 board,
// NOT a composite ranking. Candidates (top-decile AND persistent) float first, then
// by persistence streak, then by cross-sectional ignition percentile. Instantaneous
// ignition has no lift — only sustained ignition does — so persistence dominates pct.
// ignition is the project's core engine and has no tunable parameter — there is no
// knob to perturb this order (the former early⟷reliable knob is gone, PRD §16).
function ignKey(s: Stock): [number, number, number] {
  const ig = s.ignition
  return [ig?.candidate ? 1 : 0, ig?.ign_persist_days ?? 0, ig?.ign_pct ?? 0]
}
function byIgnition(a: Stock, b: Stock): number {
  const ka = ignKey(a)
  const kb = ignKey(b)
  for (let i = 0; i < 3; i++) if (kb[i] !== ka[i]) return kb[i] - ka[i]
  return 0
}

// Discovery board (PRD §9.3 + §10.8): 2-column evidence-card grid, sorted by
// 持续点火 (sustained ignition) — candidate first, then ign_persist_days desc, then
// ign_pct desc. ignition is the core engine and has no tunable parameter (the former
// early⟷reliable knob is gone, PRD §16); composite is no longer a user-visible concept
// (M8). Each card is evidence-first (raw numbers + 点火证据 + mini-chart). `initial` lets
// tests/SSR inject the board without fetching. `scope`/`pinned` (App's single source)
// filter BEFORE sort (C10).
export default function Discovery({
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
        <div className="ph-msg">读取 Discovery 快照…</div>
      </div>
    )
  }

  // respect global scope: filter BEFORE sorting (PRD §9.3), then rank by 持续点火 (M7.3).
  // ignition is the order key; there is no composite and no knob (PRD §16).
  const shown0 = board.stocks
    .filter((s) => inScope(s, scope, pinned))
    .sort(byIgnition)
  // Callers bound the board to a top-N: Discovery proper caps at App's DISCOVERY_LIMIT
  // (PRD §9.3 bounded/decide); Rotation's drill drawer previews fewer still (PRD §9.4).
  const shown = limit != null ? shown0.slice(0, limit) : shown0
  const nCand = shown.filter((s) => s.ignition?.candidate).length

  return (
    <div className="disco">
      <div className="ecgrid">
        {shown.map((s) => (
          <EvidenceCard key={s.ticker} stock={s} onOpen={onOpen} />
        ))}
      </div>
      <div className="foot">
        <b>持续点火榜</b>（PRD §10.8，发现核心引擎）：按 <b>持续点火</b> 排序 —— candidate（top-decile 且持续 ≥
        {board.ignition_persist_min ?? 5} 日）置顶 → 点火持续天数 → 点火百分位（瞬时点火无 lift）。ignition 无可调参（5 分量
        等权 + 阈值离线定，刻意=买 robustness 不买 alpha）。每张卡 = 证据优先（6 个原始数字 + 点火证据：突破日 / 放量× /
        步速比 / 是否收复 MA50），永不给 buy/target；点卡片任意处 → Stock。 as_of {board.as_of_date} ·{' '}
        {shown.length} 只（点火候选 {nCand}）
        {scope && scope.kind !== 'all' ? `（scope=${scope.kind === 'pinned' ? 'pinned' : scope.key} 过滤后）` : ''} · valuation
        覆盖 {board.valuation_coverage}。
      </div>
    </div>
  )
}
