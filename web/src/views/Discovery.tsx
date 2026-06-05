import { useEffect, useState } from 'react'
import type { BoardData } from '../types'
import { loadBoard } from '../lib/data'
import EvidenceCard from '../components/EvidenceCard'

// Discovery board (PRD §9.3): 2-column evidence-card grid, composite-descending.
// M1.3 sorts by the EXPORTED composite (engine snapshot) and shows weights at the
// default k; the early⟷reliable knob re-weighting + live re-sort land in M1.4
// (composite.ts, C9). `initial` lets tests/SSR inject the board without fetching.
export default function Discovery({
  initial,
  onOpen,
}: {
  initial?: BoardData
  onOpen?: (ticker: string) => void
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

  const stocks = [...board.stocks].sort(
    (a, b) => (b.composite ?? -Infinity) - (a.composite ?? -Infinity),
  )

  return (
    <div className="disco">
      <div className="ecgrid">
        {stocks.map((s) => (
          <EvidenceCard key={s.ticker} stock={s} weights={board.weights_default} onOpen={onOpen} />
        ))}
      </div>
      <div className="foot">
        每张卡 = 一只票的原始证据（price + volume + MA 图 + 摊开的硬数字），<b>不是</b>分数榜。composite
        缩成角标（点 ▾ 看 5 个 component 原始值 + 权重，无黑箱）。点卡片任意处 → Stock（M5）。
        旋钮调权重重排 + 分量条随 k 变 = M1.4（前端按 c_* 重算，C9）。as_of {board.as_of_date} · {stocks.length}{' '}
        只 · valuation 覆盖 {board.valuation_coverage}。
      </div>
    </div>
  )
}
