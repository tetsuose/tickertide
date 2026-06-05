import { useState } from 'react'
import type { SurfaceId, Scope, Components } from './types'
import Discovery from './views/Discovery'
import { weights } from './lib/composite'

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

const SURFACE_INFO: Record<SurfaceId, { scale: string; milestone: string; blurb: string }> = {
  ocean: {
    scale: 'wide · explore',
    milestone: 'M2',
    blurb: 'canvas 散点：x = RS percentile，y = Valuation percentile（底 = 便宜）；周度 scrubber + pin→trail，轴固定 RS×估值。',
  },
  discovery: {
    scale: 'bounded · decide',
    milestone: 'M1.3 – M1.4',
    blurb: 'evidence-first 卡流：每张卡 6 个原始数字 + 可展开的 composite 角标。卡片组件 M1.3；composite 排序 + early⟷reliable 旋钮（前端按 c_* 重算，C9）M1.4。数据来自 export/board.py 的 board.json。',
  },
  rotation: {
    scale: 'narrow · decide',
    milestone: 'M3',
    blurb: 'sector / theme 的 RS-Ratio 多线图（非散点）+ enriched league 表；点 bucket → N=1 单线 + 成员卡。',
  },
  valuation: {
    scale: 'wide · explore',
    milestone: 'M5',
    blurb: 'duckdb-wasm 浏览器横截面 screener；as-of 新鲜度三档上色 + common-vintage percentile。',
  },
  stock: {
    scale: 'narrow · detail',
    milestone: 'M5',
    blurb: 'price ↔ fundamentals 时间轴对齐 stack（K线 + MA + 成交量 + 季度营收 bars + P/S over time）。',
  },
}

export default function App() {
  const [tab, setTab] = useState<SurfaceId>('discovery')
  const [k, setK] = useState(0.5)
  // global scope filter — single source, sticky across tabs (PRD §9.1.2, C8/C10).
  // M1.2 has no writers yet (Rotation/Valuation/Ocean clicks land later), so it
  // stays `all` and the chip is hidden; the clear handler is wired for M1.4+.
  const [scope, setScope] = useState<Scope>({ kind: 'all', key: null })

  const info = SURFACE_INFO[tab]

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
            <div>
              <span className="dot" />
              <b>EOD</b> snapshot
            </div>
            <div className="asof2">M1.2 scaffold · 数据接入 M1.4</div>
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

          <div className="knobwrap">
            <div className="knoblabels">
              <span className={k < 0.5 ? 'kactive' : ''}>RELIABLE</span>
              <span className="khint">confirmation ⟷ acceleration</span>
              <span className={k >= 0.5 ? 'kactive' : ''}>EARLY</span>
            </div>
            <input
              className="knob"
              type="range"
              min={0}
              max={1}
              step={0.01}
              value={k}
              onChange={(e) => setK(parseFloat(e.target.value))}
              aria-label="early to reliable knob"
            />
            <div className="wbars">
              {(
                [
                  ['rs', 'RS'],
                  ['high', '52WH'],
                  ['trend', 'TREND'],
                  ['vol', 'VOL'],
                  ['accel', 'ACCEL'],
                ] as [keyof Components, string][]
              ).map(([key, label]) => (
                <div key={key} className="wb" title={`${label} ${(weights(k)[key] * 100).toFixed(0)}%`}>
                  <div className="wbtrack">
                    <div className="wbfill" style={{ height: `${Math.round((weights(k)[key] / 0.45) * 100)}%` }} />
                  </div>
                  <div className="wbl">{label}</div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {scope.kind !== 'all' && (
          <div className="scopebar">
            <span className="scopechip">
              Scope: <b>{scope.key ?? scope.kind}</b>
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
            <Discovery k={k} />
          ) : (
            <>
              <div className="placeholder">
                <div className="ph-tag">{info.milestone} · SCAFFOLD</div>
                <div className="ph-msg">{info.blurb}</div>
              </div>
              <div className="foot">
                脊柱骨架：单一 composite 引擎 → 5 个 lens，两个尺度（wide explore / bounded decide），零常驻
                backend。旋钮 k = {k.toFixed(2)} 已驱动 Discovery 实时重排（权重条见上）；此 surface 待后续 milestone。
              </div>
            </>
          )}
        </section>
      </div>
    </div>
  )
}
