import { useEffect, useState } from 'react'
import type { RotationData, RotationBucket, RotationState, Scope, SurfaceId } from '../types'
import { loadRotation } from '../lib/data'
import {
  MULTI, SOLO, multiScale, soloScale, linePath, soloSegments, endLabels, gridTicks,
  bucketColorVar,
} from '../lib/rotation-draw'
import Discovery from './Discovery'

// Rotation (PRD §9.4): the narrow-decide surface. Overview = every sector's RS-Ratio on
// one SVG multi-line chart (height=level >100 outperforms SPY, slope=momentum) + an
// enriched league. Click a line/row → set the global scope to that sector (Rotation is
// the SECOND scope writer — C10) and expand an INLINE drill drawer (N=1 line whose color
// is the slope + sector summary + member preview), NO auto-jump (§9.1.2: changing scope
// and changing view are decoupled). RS-Ratio constants are a transparent reconstruction
// (PRD §10.4) — NOT a StockCharts replica. `initial` injects data for SSR/tests.
// UX contract: docs/equity-monitor-v2.jsx RSRatioLines / SoloRSLine / rotation tab.

const STATE_META: Record<RotationState, { label: string; cssVar: string }> = {
  LEADING: { label: 'LEADING', cssVar: '--q-lead' },
  WEAKENING: { label: 'WEAKENING', cssVar: '--q-weak' },
  IMPROVING: { label: 'IMPROVING', cssVar: '--q-impr' },
  LAGGING: { label: 'LAGGING', cssVar: '--dim2' },
}

function fmtPct(v: number | null): string {
  if (v == null) return '—'
  return (v >= 0 ? '+' : '') + (v * 100).toFixed(1) + '%'
}

/** Overview multi-line chart (jsx RSRatioLines): all sectors' RS-Ratio, y=100 baseline,
 *  hover dims the rest, right-edge labels stacked by last value. */
function RSRatioLines({
  buckets, hover, setHover, onPick,
}: {
  buckets: RotationBucket[]
  hover: string | null
  setHover: (k: string | null) => void
  onPick: (bucket: string) => void
}) {
  const { W, H, padL, padR } = MULTI
  const sc = multiScale(buckets.map((b) => b.rs_ratio))
  const n = buckets[0]?.rs_ratio.length ?? 0
  const lines = buckets.map((b) => ({
    key: b.bucket, name: b.bucket, colorVar: bucketColorVar(b.bucket), series: b.rs_ratio,
  }))
  const ends = endLabels(lines, sc)
  const ticks = gridTicks(sc)
  const y100 = sc.Y(100)
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" className="rrgsvg" role="img" aria-label="sector RS-Ratio lines">
      {ticks.map((t) => (
        <g key={t}>
          <line x1={padL} y1={sc.Y(t)} x2={W - padR} y2={sc.Y(t)}
            stroke={t === 100 ? 'var(--line2)' : 'var(--line)'} strokeDasharray={t === 100 ? 'none' : '2 4'} />
          <text x={padL - 6} y={sc.Y(t) + 3} className="axt" textAnchor="end">{t}</text>
        </g>
      ))}
      <text x={W - padR - 3} y={y100 - 4} className="axt" textAnchor="end" style={{ fill: 'var(--dim)' }}>= SPY (100)</text>
      {lines.map((l) => {
        const on = hover === null || hover === l.key
        return (
          <path key={l.key} d={linePath(l.series, sc)} fill="none" stroke={`var(${l.colorVar})`}
            strokeWidth={hover === l.key ? 2.6 : 1.5} strokeOpacity={on ? 1 : 0.1}
            onMouseEnter={() => setHover(l.key)} onMouseLeave={() => setHover(null)}
            onClick={() => onPick(l.key)} style={{ cursor: 'pointer' }} />
        )
      })}
      {ends.map((e) => {
        const on = hover === null || hover === e.key
        return (
          <g key={e.key} opacity={on ? 1 : 0.18} onMouseEnter={() => setHover(e.key)}
            onMouseLeave={() => setHover(null)} onClick={() => onPick(e.key)} style={{ cursor: 'pointer' }}>
            <line x1={sc.X(n - 1, n)} y1={sc.Y(e.v)} x2={W - padR + 7} y2={e.y}
              stroke={`var(${e.colorVar})`} strokeWidth={0.7} strokeOpacity={0.5} />
            <text x={W - padR + 10} y={e.y + 3} style={{ fill: `var(${e.colorVar})`, fontSize: '9.5px', fontFamily: 'var(--mono)' }}>
              {e.name} {e.v.toFixed(1)}
            </text>
          </g>
        )
      })}
      <text x={padL} y={H - 7} className="axt" textAnchor="start">← {n} weeks</text>
      <text x={W - padR} y={H - 7} className="axt" textAnchor="end">now</text>
    </svg>
  )
}

/** N=1 single line (jsx SoloRSLine): color = short-window slope (↑green/↓red = momentum),
 *  since with one line the color channel is free for the slope. */
function SoloRSLine({ bucket }: { bucket: RotationBucket }) {
  const { W, H, padL, padR } = SOLO
  const series = bucket.rs_ratio.filter((v): v is number => v != null)
  const sc = soloScale(series)
  const n = series.length
  const segs = soloSegments(series, sc)
  const ticks = gridTicks(sc)
  const lvl = n ? series[n - 1] : 100
  const slope4 = bucket.slope_4w ?? 0
  const y100 = sc.Y(100)
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" className="rrgsvg" role="img" aria-label={`${bucket.bucket} RS-Ratio`}>
      {ticks.map((t) => (
        <g key={t}>
          <line x1={padL} y1={sc.Y(t)} x2={W - padR} y2={sc.Y(t)}
            stroke={t === 100 ? 'var(--line2)' : 'var(--line)'} strokeDasharray={t === 100 ? 'none' : '2 4'} />
          <text x={padL - 7} y={sc.Y(t) + 3} className="axt" textAnchor="end">{t}</text>
        </g>
      ))}
      <text x={W - padR - 3} y={y100 - 4} className="axt" textAnchor="end" style={{ fill: 'var(--dim)' }}>= SPY (100)</text>
      <text x={padL} y={14} className="axl" textAnchor="start">RS-RATIO vs SPY · 线色 = 斜率(↑绿/↓红) = momentum</text>
      {segs.map((s, i) => (
        <line key={i} x1={s.x1} y1={s.y1} x2={s.x2} y2={s.y2}
          stroke={s.up ? 'var(--grn)' : 'var(--red)'} strokeWidth={2.6} strokeLinecap="round" />
      ))}
      <circle cx={sc.X(n - 1, n)} cy={sc.Y(lvl)} r={4} fill={slope4 >= 0 ? 'var(--grn)' : 'var(--red)'} />
      <text x={W - padR + 4} y={sc.Y(lvl) + 3} style={{ fill: `var(${bucketColorVar(bucket.bucket)})`, fontSize: '11px', fontFamily: 'var(--mono)' }}>
        {lvl.toFixed(1)}
      </text>
      <text x={padL} y={H - 8} className="axt" textAnchor="start">← {n} weeks</text>
      <text x={W - padR} y={H - 8} className="axt" textAnchor="end">now</text>
    </svg>
  )
}

export default function Rotation({
  initial,
  scope,
  setScope,
  onJumpTab,
  k,
}: {
  initial?: RotationData
  scope: Scope
  setScope?: (s: Scope) => void
  onJumpTab?: (t: SurfaceId) => void
  k?: number
}) {
  const [data, setData] = useState<RotationData | null>(initial ?? null)
  const [err, setErr] = useState<string | null>(null)
  const [hover, setHover] = useState<string | null>(null)
  const [bucketType, setBucketType] = useState<'sector' | 'theme'>('sector')

  useEffect(() => {
    if (initial) return
    const ac = new AbortController()
    loadRotation(ac.signal)
      .then(setData)
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
          rotation.json 未就绪（{err}）。先跑 <code>make fixture-pipeline</code> 或真实 <code>make pipeline</code>，再{' '}
          <code>python export/rotation.py</code> 生成 web/public/data/rotation.json。
        </div>
      </div>
    )
  }
  if (!data) {
    return (
      <div className="placeholder">
        <div className="ph-tag">LOADING</div>
        <div className="ph-msg">读取 Rotation 周度 RS-Ratio…</div>
      </div>
    )
  }

  // Drill drawer when the scope is narrowed to one sector (C10 — set by a row/line click
  // here, or sticky from another tab). Otherwise (all / pinned / theme) → the overview.
  const drilled = scope.kind === 'sector' ? data.buckets.find((b) => b.bucket === scope.key) ?? null : null

  if (drilled) {
    return (
      <div className="rot">
        <div className="rot-head">
          <span>
            ROTATION — <b style={{ color: `var(${bucketColorVar(drilled.bucket)})` }}>{drilled.bucket}</b>{' '}
            <span className="dim">{drilled.etf ?? ''}</span> · 单条放大 + 成员
          </span>
          <button className="seg" onClick={() => setScope?.({ kind: 'all', key: null })}>← all sectors</button>
        </div>
        <SoloRSLine bucket={drilled} />
        <div className="rot-summary">
          <div><span className="dim">RS-Ratio</span><b>{drilled.level?.toFixed(1) ?? '—'}</b></div>
          <div><span className="dim">Δ4w</span><b style={{ color: (drilled.slope_4w ?? 0) >= 0 ? 'var(--grn)' : 'var(--red)' }}>{(drilled.slope_4w ?? 0) >= 0 ? '▲' : '▼'}{Math.abs(drilled.slope_4w ?? 0).toFixed(1)}</b></div>
          <div><span className="dim">state</span><b style={{ color: `var(${STATE_META[drilled.state].cssVar})` }}>{STATE_META[drilled.state].label}</b></div>
          <div><span className="dim">breadth &gt;MA50</span><b>{drilled.breadth_ma50?.toFixed(0) ?? '—'}%</b></div>
          <div><span className="dim">breadth &gt;MA200</span><b>{drilled.breadth_ma200?.toFixed(0) ?? '—'}%</b></div>
          <div><span className="dim"># at 52w high</span><b>{drilled.at_high ?? '—'}</b></div>
          <div><span className="dim">composite 中位</span><b>{drilled.composite_median?.toFixed(1) ?? '—'}</b></div>
          <div><span className="dim">agg EV/S</span><b>{drilled.agg_evs?.toFixed(1) ?? '—'}</b></div>
          <div><span className="dim">rel ret 1m/3m/6m</span><b>{fmtPct(drilled.rel_ret_1m)} / {fmtPct(drilled.rel_ret_3m)} / {fmtPct(drilled.rel_ret_6m)}</b></div>
          <div><span className="dim">members</span><b>{drilled.member_count ?? '—'}</b></div>
        </div>
        <div className="rot-memhead">
          <span>成员 · top by composite <em className="tag">scope 收窄到该 sector</em></span>
          <button className="seg" onClick={() => onJumpTab?.('discovery')}>在 Discovery 看全部成员 →</button>
        </div>
        <Discovery scope={scope} k={k} limit={6} />
        <div className="foot">
          单条 RS-Ratio 放大：<b>高度=level、线色=斜率(↑绿/↓红)=momentum</b>（N=1 时 color 空出来给斜率）。下面是该 sector
          成员证据卡（复用 board.json，按 scope filter — C9/DRY）。点「← all sectors」或顶部 scope ✕ 清 scope 回总览。
        </div>
      </div>
    )
  }

  const league = [...data.buckets].sort((a, b) => (b.level ?? 0) - (a.level ?? 0))

  return (
    <div className="rot">
      <div className="rot-head">
        <span>ROTATION — sector RS-Ratio vs SPY · 高度=level，斜率=momentum</span>
        <span className="orow" role="group" aria-label="bucket type">
          <button className={'seg' + (bucketType === 'sector' ? ' on' : '')} onClick={() => setBucketType('sector')}>GICS Sectors</button>
          <button className={'seg' + (bucketType === 'theme' ? ' on' : '')} onClick={() => setBucketType('theme')}>Themes</button>
        </span>
      </div>
      {bucketType === 'theme' ? (
        <div className="placeholder">
          <div className="ph-tag">M4</div>
          <div className="ph-msg">Theme RS-Ratio 待 M4（theme_membership point-in-time + 非市值加权 theme index）。GICS↔Theme 切换 UI 已就位。</div>
        </div>
      ) : (
        <>
          <RSRatioLines buckets={data.buckets} hover={hover} setHover={setHover} onPick={(b) => setScope?.({ kind: 'sector', key: b })} />
          <div className="rleague">
            <div className="rlhead">
              <div className="r">#</div><div>Sector</div><div className="r">RS-Ratio</div><div className="r">Δ4w</div>
              <div>state</div><div className="r">brdth50</div><div className="r">EV/S</div>
            </div>
            {league.map((b, i) => (
              <div key={b.bucket}
                className={'rlrow' + (hover === b.bucket ? ' hov' : '')}
                onClick={() => setScope?.({ kind: 'sector', key: b.bucket })}
                onMouseEnter={() => setHover(b.bucket)} onMouseLeave={() => setHover(null)}
                style={{ cursor: 'pointer' }}>
                <div className="r mono dim">{i + 1}</div>
                <div className="tk" style={{ color: `var(${bucketColorVar(b.bucket)})` }}>{b.bucket}</div>
                <div className="r mono">{b.level?.toFixed(1) ?? '—'}</div>
                <div className="r mono" style={{ color: (b.slope_4w ?? 0) >= 0 ? 'var(--grn)' : 'var(--red)' }}>
                  {(b.slope_4w ?? 0) >= 0 ? '▲' : '▼'}{Math.abs(b.slope_4w ?? 0).toFixed(1)}
                </div>
                <div>
                  <span className="qchip" style={{ color: `var(${STATE_META[b.state].cssVar})`, borderColor: `var(${STATE_META[b.state].cssVar})` }}>
                    {STATE_META[b.state].label}
                  </span>
                </div>
                <div className="r mono dim">{b.breadth_ma50?.toFixed(0) ?? '—'}%</div>
                <div className="r mono dim">{b.agg_evs?.toFixed(1) ?? '—'}</div>
              </div>
            ))}
          </div>
          <div className="foot">
            所有 sector 的 RS-Ratio（相对 SPY）叠一张图：<b>高度=level</b>（&gt;100 跑赢自身近期趋势）、<b>斜率=momentum</b>、线交叉=leadership
            换手。hover 高亮一条其余变淡、右缘按末值排序贴标签；<b>点一行/线 → 钻进该 sector</b>（set 全局 scope，跨 tab 粘滞、可一键清）。
            下表按 level 排序，<b>Δ4w=斜率</b>。as_of {data.as_of_date} · {data.count} sector · params n1={data.params.n1_ema}/n2=
            {data.params.n2_window}/k={data.params.k}（透明 reconstruction，不复刻 StockCharts/de Kempenaer 数值）。
          </div>
        </>
      )}
    </div>
  )
}
