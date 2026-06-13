import { useEffect, useState } from 'react'
import type { RotationData, RotationBucket, RotationState, Scope, SurfaceId } from '../types'
import { loadRotation } from '../lib/data'
import {
  MULTI, SOLO, multiScale, soloScale, linePath, soloSegments, endLabels, gridTicks,
  bucketColorVar,
} from '../lib/rotation-draw'
import {
  viewBoxXFromClient, viewBoxYFromClient, pointIndexAt, nearestSeriesAt, axisTickIndices, tickDate,
} from '../lib/chart-hover'
import CursorReadout from '../components/ChartCursor'
import Discovery from './Discovery'

// Rotation (PRD §9.4): the narrow-decide surface. Overview = every bucket's RS-Ratio on
// one SVG multi-line chart (height=level >100 outperforms SPY, slope=momentum) + an
// enriched league. The GICS↔Theme toggle switches the bucket set: sectors (rotation.json,
// M3) or concept themes (rotation.theme.json — point-in-time, non-market-cap theme index,
// M4.4), reusing the same chart/league/drill with THEME_VAR colors. Click a line/row → set
// the global scope to that bucket (Rotation is the SECOND scope writer — C10) and expand an
// INLINE drill drawer (N=1 line whose color is the slope + summary + member preview), NO
// auto-jump (§9.1.2: changing scope and changing view are decoupled). RS-Ratio constants
// are a transparent reconstruction (PRD §10.4) — NOT a StockCharts replica. `initial`
// injects data for SSR/tests; its bucket_type picks the starting view.
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
 *  hover dims the rest, right-edge labels stacked by last value. A week time-cursor reads
 *  the line nearest the pointer at the cursored week; a resident MM/DD axis sits below. */
function RSRatioLines({
  buckets, weeks, hover, setHover, onPick,
}: {
  buckets: RotationBucket[]
  weeks: string[]
  hover: string | null
  setHover: (k: string | null) => void
  onPick: (bucket: string) => void
}) {
  const { W, H, padL, padR, padT, padB } = MULTI
  const sc = multiScale(buckets.map((b) => b.rs_ratio))
  const n = buckets[0]?.rs_ratio.length ?? 0
  const lines = buckets.map((b) => ({
    key: b.bucket, name: b.bucket, colorVar: bucketColorVar(b.bucket), series: b.rs_ratio,
  }))
  const ends = endLabels(lines, sc)
  const ticks = gridTicks(sc)
  const y100 = sc.Y(100)
  const [hi, setHi] = useState<number | null>(null)

  // svg-level move drives BOTH the highlight (line nearest the pointer) and the week cursor,
  // so reading a value no longer needs pixel-hunting the thin path. Outside the plot (e.g.
  // the right-edge label gutter) the end-label hover takes over; the cursor just hides.
  const onMove = (e: React.MouseEvent) => {
    const r = e.currentTarget.getBoundingClientRect()
    const idx = pointIndexAt(viewBoxXFromClient(e.clientX, r.left, r.width, W), padL, padR, W, n)
    setHi(idx)
    if (idx == null) return
    const vy = viewBoxYFromClient(e.clientY, r.top, r.height, H)
    const s = nearestSeriesAt(buckets.map((b) => b.rs_ratio), idx, vy, sc.Y)
    setHover(s >= 0 ? buckets[s].bucket : null)
  }
  const onLeave = () => {
    setHi(null)
    setHover(null)
  }

  // the highlighted line's value at the cursored week → the readout
  const hb = hover != null ? buckets.find((b) => b.bucket === hover) : undefined
  const hv = hi != null && hb ? hb.rs_ratio[hi] : null

  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" className="rrgsvg" role="img" aria-label="sector RS-Ratio lines"
      onMouseMove={onMove} onMouseLeave={onLeave} onClick={() => hover && onPick(hover)} style={{ cursor: 'pointer' }}>
      <rect x={padL} y={padT} width={W - padL - padR} height={H - padT - padB} fill="transparent" />
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
            strokeWidth={hover === l.key ? 2.6 : 1.5} strokeOpacity={on ? 1 : 0.1} />
        )
      })}
      {ends.map((e) => {
        const on = hover === null || hover === e.key
        return (
          <g key={e.key} opacity={on ? 1 : 0.18} onMouseEnter={() => setHover(e.key)}
            onMouseLeave={() => setHover(null)} style={{ cursor: 'pointer' }}>
            <line x1={sc.X(n - 1, n)} y1={sc.Y(e.v)} x2={W - padR + 7} y2={e.y}
              stroke={`var(${e.colorVar})`} strokeWidth={0.7} strokeOpacity={0.5} />
            <text x={W - padR + 10} y={e.y + 3} style={{ fill: `var(${e.colorVar})`, fontSize: '9.5px', fontFamily: 'var(--mono)' }}>
              {e.name} {e.v.toFixed(1)}
            </text>
          </g>
        )
      })}
      {/* resident date axis: MM/DD week ticks */}
      {axisTickIndices(n, 6).map((i, k, arr) => (
        <text key={'ax' + i} className="chax" x={sc.X(i, n)} y={H - 7}
          textAnchor={k === 0 ? 'start' : k === arr.length - 1 ? 'end' : 'middle'}>
          {tickDate(weeks[i])}
        </text>
      ))}
      {/* week time-cursor: vertical line + nearest-line marker + bucket·date·RS readout */}
      {hi != null && (
        <>
          <line className="chcur-line" x1={sc.X(hi, n)} y1={padT} x2={sc.X(hi, n)} y2={H - padB} />
          {hv != null && hb && (
            <circle className="chcur-dot" cx={sc.X(hi, n)} cy={sc.Y(hv)} r={3} fill={`var(${bucketColorVar(hb.bucket)})`} />
          )}
          {hv != null && hb && (
            <CursorReadout x={sc.X(hi, n)} y={padT + 1} viewW={W} color={`var(${bucketColorVar(hb.bucket)})`}
              text={`${hb.bucket} ${tickDate(weeks[hi])} ${hv.toFixed(1)}`} />
          )}
        </>
      )}
    </svg>
  )
}

/** N=1 single line (jsx SoloRSLine): color = short-window slope (↑green/↓red = momentum),
 *  since with one line the color channel is free for the slope. A time-cursor reads the
 *  RS-Ratio at the cursored week; a resident MM/DD axis sits below. */
function SoloRSLine({ bucket, weeks }: { bucket: RotationBucket; weeks: string[] }) {
  const { W, H, padL, padR, padT, padB } = SOLO
  // keep each non-null point's ORIGINAL week index so the date axis + cursor stay aligned
  // (soloScale/soloSegments still see the compact, gap-free value series, as before).
  const pts = bucket.rs_ratio
    .map((v, wk) => ({ v, wk }))
    .filter((q): q is { v: number; wk: number } => q.v != null)
  const series = pts.map((q) => q.v)
  const sc = soloScale(series)
  const n = series.length
  const segs = soloSegments(series, sc)
  const ticks = gridTicks(sc)
  const lvl = n ? series[n - 1] : 100
  const slope4 = bucket.slope_4w ?? 0
  const y100 = sc.Y(100)
  const [hi, setHi] = useState<number | null>(null)

  const onMove = (e: React.MouseEvent) => {
    const r = e.currentTarget.getBoundingClientRect()
    setHi(pointIndexAt(viewBoxXFromClient(e.clientX, r.left, r.width, W), padL, padR, W, n))
  }

  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" className="rrgsvg" role="img" aria-label={`${bucket.bucket} RS-Ratio`}
      onMouseMove={onMove} onMouseLeave={() => setHi(null)}>
      <rect x={padL} y={padT} width={W - padL - padR} height={H - padT - padB} fill="transparent" />
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
      {/* resident date axis: MM/DD week ticks (mapped back to original weeks) */}
      {axisTickIndices(n, 6).map((i, k, arr) => (
        <text key={'ax' + i} className="chax" x={sc.X(i, n)} y={H - 8}
          textAnchor={k === 0 ? 'start' : k === arr.length - 1 ? 'end' : 'middle'}>
          {tickDate(weeks[pts[i].wk])}
        </text>
      ))}
      {/* time-cursor: vertical line + RS marker + date·RS readout */}
      {hi != null && n > 0 && (
        <>
          <line className="chcur-line" x1={sc.X(hi, n)} y1={padT} x2={sc.X(hi, n)} y2={H - padB} />
          <circle className="chcur-dot" cx={sc.X(hi, n)} cy={sc.Y(series[hi])} r={3} fill={`var(${bucketColorVar(bucket.bucket)})`} />
          <CursorReadout x={sc.X(hi, n)} y={padT + 1} viewW={W} color={`var(${bucketColorVar(bucket.bucket)})`}
            text={`${tickDate(weeks[pts[hi].wk])} ${series[hi].toFixed(1)}`} />
        </>
      )}
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
  // `initial` (SSR/tests) drives the starting view by its bucket_type, so a theme fixture
  // renders theme mode directly. The live app passes no initial → loads sector, lazy-loads
  // theme on first toggle.
  const initTheme = initial?.bucket_type === 'theme'
  const [bucketType, setBucketType] = useState<'sector' | 'theme'>(initTheme ? 'theme' : 'sector')
  const [data, setData] = useState<RotationData | null>(initial && !initTheme ? initial : null)
  const [themeData, setThemeData] = useState<RotationData | null>(initTheme ? initial! : null)
  const [err, setErr] = useState<string | null>(null)
  const [themeErr, setThemeErr] = useState<string | null>(null)
  const [hover, setHover] = useState<string | null>(null)

  // Sector loads on mount; theme lazy-loads the first time the toggle hits Themes. Two
  // files because the theme index starts at its first as_of, so its weeks axis differs
  // (M4.4). Effects are browser-only — SSR tests inject `initial` and never fetch.
  useEffect(() => {
    if (data) return
    const ac = new AbortController()
    loadRotation(ac.signal, 'sector').then(setData).catch((e) => { if (!ac.signal.aborted) setErr(String(e)) })
    return () => ac.abort()
  }, [data])

  useEffect(() => {
    if (bucketType !== 'theme' || themeData || themeErr) return
    const ac = new AbortController()
    loadRotation(ac.signal, 'theme').then(setThemeData).catch((e) => { if (!ac.signal.aborted) setThemeErr(String(e)) })
    return () => ac.abort()
  }, [bucketType, themeData, themeErr])

  const isTheme = bucketType === 'theme'
  const active = isTheme ? themeData : data
  const activeErr = isTheme ? themeErr : err
  const noun = isTheme ? 'theme' : 'sector'

  const toggle = (
    <span className="orow" role="group" aria-label="bucket type">
      <button className={'seg' + (!isTheme ? ' on' : '')} onClick={() => setBucketType('sector')}>GICS Sectors</button>
      <button className={'seg' + (isTheme ? ' on' : '')} onClick={() => setBucketType('theme')}>Themes</button>
    </span>
  )

  if (activeErr) {
    const file = isTheme ? 'rotation.theme.json' : 'rotation.json'
    return (
      <div className="rot">
        <div className="rot-head"><span>ROTATION</span>{toggle}</div>
        <div className="placeholder">
          <div className="ph-tag">NO DATA</div>
          <div className="ph-msg">
            {file} 未就绪（{activeErr}）。先跑 <code>make fixture-pipeline</code>
            {isTheme ? <> + <code>python compute/theme_index.py</code></> : null}，再{' '}
            <code>python export/rotation.py --bucket-type {noun}</code> 生成 web/public/data/{file}。
          </div>
        </div>
      </div>
    )
  }
  if (!active) {
    return (
      <div className="rot">
        <div className="rot-head"><span>ROTATION</span>{toggle}</div>
        <div className="placeholder"><div className="ph-tag">LOADING</div><div className="ph-msg">读取 {noun} RS-Ratio…</div></div>
      </div>
    )
  }

  // Drill when the global scope narrows to a bucket of the ACTIVE type (set by a row/line
  // click here — Rotation is the 2nd scope writer, C10 — or sticky from another tab).
  // Changing scope and changing view are decoupled (§9.1.2): no auto-jump.
  const drilled = scope.kind === bucketType ? active.buckets.find((b) => b.bucket === scope.key) ?? null : null

  if (drilled) {
    return (
      <div className="rot">
        <div className="rot-head">
          <span>
            ROTATION — <b style={{ color: `var(${bucketColorVar(drilled.bucket)})` }}>{drilled.bucket}</b>{' '}
            <span className="dim">{drilled.etf ?? ''}</span> · 单条放大 + 成员
          </span>
          <button className="seg" onClick={() => setScope?.({ kind: 'all', key: null })}>← all {noun}s</button>
        </div>
        <SoloRSLine bucket={drilled} weeks={active.weeks} />
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
          <span>成员 · top by composite <em className="tag">scope 收窄到该 {noun}</em></span>
          <button className="seg" onClick={() => onJumpTab?.('discovery')}>在 Discovery 看全部成员 →</button>
        </div>
        <Discovery scope={scope} k={k} limit={6} />
        <div className="foot">
          单条 RS-Ratio 放大：<b>高度=level、线色=斜率(↑绿/↓红)=momentum</b>（N=1 时 color 空出来给斜率）。下面是该 {noun}
          成员证据卡（复用 board.json，按 scope filter — C9/DRY）。点「← all {noun}s」或顶部 scope ✕ 清 scope 回总览。
        </div>
      </div>
    )
  }

  const league = [...active.buckets].sort((a, b) => (b.level ?? 0) - (a.level ?? 0))
  const colName = isTheme ? 'Theme' : 'Sector'

  return (
    <div className="rot">
      <div className="rot-head">
        <span>ROTATION — {noun} RS-Ratio vs SPY · 高度=level，斜率=momentum</span>
        {toggle}
      </div>
      <RSRatioLines buckets={active.buckets} weeks={active.weeks} hover={hover} setHover={setHover} onPick={(b) => setScope?.({ kind: bucketType, key: b })} />
      <div className="rleague">
        <div className="rlhead">
          <div className="r">#</div><div>{colName}</div><div className="r">RS-Ratio</div><div className="r">Δ4w</div>
          <div>state</div><div className="r">brdth50</div><div className="r">EV/S</div>
        </div>
        {league.map((b, i) => (
          <div key={b.bucket}
            className={'rlrow' + (hover === b.bucket ? ' hov' : '')}
            onClick={() => setScope?.({ kind: bucketType, key: b.bucket })}
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
        所有 {noun} 的 RS-Ratio（相对 SPY）叠一张图：<b>高度=level</b>（&gt;100 跑赢自身近期趋势）、<b>斜率=momentum</b>、线交叉=leadership
        换手。hover 高亮一条其余变淡、右缘按末值排序贴标签；<b>点一行/线 → 钻进该 {noun}</b>（set 全局 scope，跨 tab 粘滞、可一键清）。
        {isTheme ? ' theme 成员取自 point-in-time membership，指数非市值加权（exposure-weighted + cap，绝不让单票主导）。' : ''}
        下表按 level 排序，<b>Δ4w=斜率</b>。as_of {active.as_of_date} · {active.count} {noun} · params n1={active.params.n1_ema}/n2=
        {active.params.n2_window}/k={active.params.k}（透明 reconstruction，不复刻 StockCharts/de Kempenaer 数值）。
      </div>
    </div>
  )
}
