import { useState, useEffect } from 'react'
import type { SurfaceId, Scope, ManifestData } from './types'
import Discovery from './views/Discovery'
import Ocean from './views/Ocean'
import Rotation from './views/Rotation'
import Valuation from './views/Valuation'
import Stock from './views/Stock'
import { loadManifest } from './lib/data'
import { dataAgeDays, freshness, ageLabel } from './lib/freshness'

// The five lenses in the contract's fixed order (PRD §9.0). Discovery is the
// M1 surface and the default tab; the others are scaffolded stubs that land in
// later milestones.
const SURFACES: { id: SurfaceId; label: string }[] = [
  { id: 'ocean', label: 'Ocean' },
  { id: 'discovery', label: 'Discovery' },
  { id: 'rotation', label: 'Rotation' },
  { id: 'valuation', label: 'Valuation' },
  { id: 'stock', label: 'Stock' },
]

// Discovery proper shows the top-N composite candidates (PRD §9.3 bounded/decide) —
// the board stays a bounded shortlist, not the full universe dump.
const DISCOVERY_LIMIT = 20

const SURFACE_INFO: Record<SurfaceId, { scale: string; milestone: string; blurb: string }> = {
  ocean: {
    scale: 'wide · explore',
    milestone: 'M2',
    blurb: 'canvas 散点：x = RS percentile，y = Valuation percentile（底 = 便宜）；周度 scrubber + pin→trail，轴固定 RS×估值。',
  },
  discovery: {
    scale: 'bounded · decide',
    milestone: 'M1.3 – M7',
    blurb: 'evidence-first 卡流：按 ignition 持续点火排序（PRD §10.8，核心引擎）；每张卡 6 个原始数字 + 点火证据 + 可展开的 composite 角标（确认副读，固定权重，无旋钮）。数据来自 export/board.py 的 board.json。',
  },
  rotation: {
    scale: 'narrow · decide',
    milestone: 'M3',
    blurb: 'sector / theme 的 RS-Ratio 多线图（非散点）+ enriched league 表；点 bucket → N=1 单线 + 成员卡。',
  },
  valuation: {
    scale: 'wide · explore',
    milestone: 'M5 · 预览',
    blurb: '横截面 screener：as-of 新鲜度三档上色 + common-vintage percentile + scope 写入口。预览读 board.json；正式 M5 走 duckdb-wasm 全 universe + PEG/margin。',
  },
  stock: {
    scale: 'narrow · detail',
    milestone: 'M5 · 预览',
    blurb: 'per-name 面板：头部 + 价格/MA/成交量图 + 6 估值倍数 + 5 分量（board.json 同源）。正式 M5 补 price↔fundamentals 时间轴 stack（季度营收 + P/S over time）+ filing 摘要。',
  },
}

export default function App() {
  const [tab, setTab] = useState<SurfaceId>('discovery')
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
            <span className="enginelead">IGNITION</span>
            <span className="enginehint">持续点火 = 发现核心引擎（无可调参） · composite = 确认副读（固定权重）</span>
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
            <span className="scopehint">filtering Discovery · Valuation · Rotation · Ocean</span>
          </div>
        )}

        <section className="panel">
          <div className="ptitle">
            <span>
              {SURFACES.find((s) => s.id === tab)!.label} · {info.scale}
            </span>
            <span className="khint">{info.milestone}</span>
          </div>
          {tab === 'discovery' ? (
            <Discovery scope={scope} pinned={pinned} limit={DISCOVERY_LIMIT} onOpen={openStock} />
          ) : tab === 'ocean' ? (
            <Ocean scope={scope} setScope={setScope} pinned={pinned} setPinned={setPinned} />
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
