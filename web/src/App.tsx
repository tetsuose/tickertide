import { useState, useEffect } from 'react'
import type { SurfaceId, Scope, ManifestData } from './types'
import Risers from './views/Risers'
import Ocean from './views/Ocean'
import Rotation from './views/Rotation'
import Valuation from './views/Valuation'
import Stock from './views/Stock'
import { loadManifest } from './lib/data'
import { dataAgeDays, freshness, ageLabel } from './lib/freshness'

// The five lenses in the contract's fixed order (PRD §9.0). Risers（连续上涨）is the
// default tab (2026-07-02 spine pivot II — Breakouts renamed + re-cored to steady-riser).
const SURFACES: { id: SurfaceId; label: string }[] = [
  { id: 'ocean', label: 'Ocean' },
  { id: 'risers', label: 'Risers' },
  { id: 'rotation', label: 'Rotation' },
  { id: 'valuation', label: 'Valuation' },
  { id: 'stock', label: 'Stock' },
]

// Risers proper shows the top of the steady-riser board (PRD §9.3 bounded/decide) — the
// board stays a bounded shortlist, not the full universe dump.
const RISERS_LIMIT = 20

const SURFACE_INFO: Record<SurfaceId, { scale: string; milestone: string; blurb: string }> = {
  ocean: {
    scale: 'wide · explore',
    milestone: 'M8',
    blurb: '连续上涨强度 × Valuation 二维相图：y = rise_pct（10 日净涨幅横截面百分位；海平面 = 90，仅视觉参考线），x = 原始 P/S（log 轴）。candidate 只读 compute 层 flag。日期滑杆 + Play 在相邻真实 EOD 快照间平滑插值。',
  },
  risers: {
    scale: 'bounded · decide',
    milestone: 'M7（steady-riser）',
    blurb: 'evidence-first 卡流（连续上涨）：gate = 10 天里 ≥6 天上涨且 net10>0，按 10 日净涨幅排序（PRD §10.8，核心筛法，recall-first）；逐张检视入选候选价格走势（近 10 日窗口高亮），每个数字图上可数，假阳交基本面 precision，永不给 buy/target。数据来自 export/board.py 的 board.json。',
  },
  rotation: {
    scale: 'narrow · decide',
    milestone: 'M3',
    blurb: 'sector / theme 的 RS-Ratio 多线图（非散点）+ enriched league 表（含 # riser candidates）；点 bucket → N=1 单线 + 成员卡。',
  },
  valuation: {
    scale: 'wide · explore',
    milestone: 'M5 · 预览',
    blurb: '横截面 screener：as-of 新鲜度三档上色 + common-vintage percentile + scope 写入口。预览读 board.json；正式 M5 走 duckdb-wasm 全 universe + PEG/margin。',
  },
  stock: {
    scale: 'narrow · detail',
    milestone: 'M5 · 预览',
    blurb: 'per-name 面板：头部 10 日净涨幅 + 价格/MA/成交量图 + 6 估值倍数 + riser 诊断（board.json 同源）。price↔fundamentals 时间轴 stack（季度营收 + P/S over time）+ filing 摘要。',
  },
}

export default function App() {
  const [tab, setTab] = useState<SurfaceId>('risers')
  // global scope filter — single source, sticky across tabs (PRD §9.1.2, C8/C10).
  // Two writers: Ocean's lasso (M2.4) sets scope='pinned'; Rotation's league row/line
  // click (M3.4) sets scope='sector'. Discovery/Ocean/Rotation all respect it (filter /
  // drill); the chip clears it back to `all`. (Valuation respects it at M5.)
  const [scope, setScope] = useState<Scope>({ kind: 'all', key: null })
  // pinned ticker set — Ocean click pins (trail); lasso bulk-selects + focuses.
  // Lives in App so scope='pinned' can filter every surface by it.
  const [pinned, setPinned] = useState<string[]>([])
  // selected ticker for the per-name Stock surface (PRD §9.6). Lives in App so any
  // surface (a Discovery card / a Valuation row) can open a name: set ticker + switch tab.
  const [selected, setSelected] = useState<string | null>(null)
  const openStock = (t: string) => {
    setSelected(t)
    setTab('stock')
  }
  // D.4 freshness: load the tiny manifest for the header as_of badge (data age + 陈旧色),
  // so stale / failed nightly data is VISIBLE, never silently served as fresh.
  const [manifest, setManifest] = useState<ManifestData | null>(null)
  useEffect(() => {
    const ac = new AbortController()
    loadManifest(ac.signal).then(setManifest).catch(() => {})
    return () => ac.abort()
  }, [])

  const info = SURFACE_INFO[tab]
  const age = manifest ? dataAgeDays(manifest.as_of_date, new Date()) : NaN
  const fresh = freshness(age)

  return (
    <div className="app">
      <div className="shell">
        <header className="hdr">
          <div className="brand">
            <div className="logo">◈</div>
            <div>
              <div className="title">TickerTide</div>
              <div className="sub">盘后 · 美股 · momentum + valuation 监控</div>
            </div>
          </div>
          <div className="asof">
            {manifest && manifest.as_of_date ? (
              <>
                <div>
                  <span className={'dot ' + fresh} />
                  <b>EOD</b> {manifest.as_of_date}
                </div>
                <div className={'asof2 fresh-' + fresh}>{ageLabel(age)}</div>
              </>
            ) : (
              <div className="asof2">数据未就绪 — 跑 make export</div>
            )}
          </div>
        </header>

        <div className="ctrl">
          <nav className="tabs">
            {SURFACES.map((s) => (
              <button
                key={s.id}
                className={'tab' + (tab === s.id ? ' on' : '')}
                onClick={() => setTab(s.id)}
              >
                {s.label}
              </button>
            ))}
          </nav>

          <div className="enginenote">
            <span className="enginelead">STEADY-RISER</span>
            <span className="enginehint">steady-riser = 核心筛法（连续上涨：10 天里 ≥6 天上涨且 net10&gt;0，按 net10 排序，无可调参） · 证据优先：raw evidence + valuation，永不给 buy/target</span>
          </div>
        </div>

        {scope.kind !== 'all' && (
          <div className="scopebar">
            <span className="scopechip">
              Scope: <b>{scope.kind === 'pinned' ? `pinned (${pinned.length})` : scope.key}</b>
              <button className="scopex" onClick={() => setScope({ kind: 'all', key: null })}>
                ✕
              </button>
            </span>
            <span className="scopehint">filtering Risers · Valuation · Rotation · Ocean</span>
          </div>
        )}

        <section className="panel">
          <div className="ptitle">
            <span>
              {SURFACES.find((s) => s.id === tab)!.label} · {info.scale}
            </span>
            <span className="khint">{info.milestone}</span>
          </div>
          {tab === 'risers' ? (
            <Risers scope={scope} pinned={pinned} limit={RISERS_LIMIT} onOpen={openStock} />
          ) : tab === 'ocean' ? (
            <Ocean scope={scope} setScope={setScope} pinned={pinned} setPinned={setPinned} onOpen={openStock} />
          ) : tab === 'rotation' ? (
            <Rotation scope={scope} setScope={setScope} onJumpTab={setTab} />
          ) : tab === 'valuation' ? (
            <Valuation scope={scope} setScope={setScope} pinned={pinned} onOpen={openStock} />
          ) : (
            <Stock ticker={selected} setTicker={setSelected} />
          )}
        </section>
      </div>
    </div>
  )
}
