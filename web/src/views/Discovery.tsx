import { useEffect, useState } from 'react'
import type { BoardData, Scope, Stock } from '../types'
import { loadBoard } from '../lib/data'
import { weights, composite } from '../lib/composite'
import EvidenceCard from '../components/EvidenceCard'

// Whether a board stock is in the global scope (PRD §9.1.2/§9.3 — filter BEFORE sort).
function inScope(s: Stock, scope: Scope | undefined, pinned: string[]): boolean {
  if (!scope || scope.kind === 'all') return true
  if (scope.kind === 'sector') return s.sector === scope.key
  if (scope.kind === 'theme') return s.themes.some((t) => t.theme === scope.key)
  if (scope.kind === 'pinned') return pinned.includes(s.ticker)
  return true
}

// Discovery board (PRD §9.3): 2-column evidence-card grid, composite-descending.
// The early⟷reliable knob k re-weights the exported components c_* via composite.ts
// (a verbatim port of compute/signals.py — C9, the engine is never recomputed),
// so changing k re-sorts the grid and moves every badge live. `initial` lets
// tests/SSR inject the board without fetching; `k` defaults to the snapshot's
// knob_default_k. `scope`/`pinned` (App's single source) filter BEFORE sorting (C10).
export default function Discovery({
  initial,
  onOpen,
  k,
  scope,
  pinned = [],
  limit,
}: {
  initial?: BoardData
  onOpen?: (ticker: string) => void
  k?: number
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

  const kEff = k ?? board.knob_default_k
  const w = weights(kEff)
  // respect global scope: filter BEFORE sorting (PRD §9.3), then composite-rank.
  const scored = board.stocks
    .filter((s) => inScope(s, scope, pinned))
    .map((s) => ({ s, score: composite(s.components, kEff) }))
    .sort((a, b) => b.score - a.score)
  // Rotation's drill drawer reuses Discovery as the member preview (scope=sector) and
  // caps it to a top-N (PRD §9.4); the full set is one click away in Discovery proper.
  const shown = limit != null ? scored.slice(0, limit) : scored

  return (
    <div className="disco">
      <div className="ecgrid">
        {shown.map(({ s, score }) => (
          <EvidenceCard key={s.ticker} stock={s} weights={w} score={score} onOpen={onOpen} />
        ))}
      </div>
      <div className="foot">
        每张卡 = 一只票的原始证据（price + volume + MA 图 + 摊开的硬数字），<b>不是</b>分数榜。角标 = 按当前权重
        （k = {kEff.toFixed(2)}）重算的 composite —— 拨旋钮即实时重排、分量条权重随之变（前端按 c_* 重算，不碰引擎，C9）。
        点 ▾ 看 5 个 component 原始值 + 权重（无黑箱）；▲▼ = 引擎默认权重下的 d/d。点卡片任意处 → Stock（M5）。
        as_of {board.as_of_date} · {shown.length} 只
        {scope && scope.kind !== 'all' ? `（scope=${scope.kind === 'pinned' ? 'pinned' : scope.key} 过滤后）` : ''} · valuation
        覆盖 {board.valuation_coverage}。
      </div>
    </div>
  )
}
