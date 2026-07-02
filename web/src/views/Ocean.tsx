import { useEffect, useRef, useState } from 'react'
import type { OceanData, OceanStock, OceanDrawPt, OceanDetail, Scope } from '../types'
import { loadOcean, loadOceanDetail } from '../lib/data'
import { num, pct } from '../lib/format'
import {
  drawOcean, drawPtAt, nearestPoint, pointsInRect, resolvePalette, interpolateOceanPoint, clamp,
  OCEAN_GEOM, type ColorMode, type DrawnPoint, type Rect, type Palette,
} from '../lib/ocean-draw'

// Ocean (PRD §9.2, 2026-07-02 spine pivot II): the wide-explore canvas as a steady-riser ×
// Valuation SEA-LEVEL map. y = rise_net10_pct (0-100, 10 日净涨幅横截面百分位) with a fixed
// sea level at 90 — a VISUAL reference line only (candidate ≠ y>=90: the gate has an up10
// condition + top-N cut; the flag is read from the export's `cand` column, C9); x = raw
// trailing P/S TTM on a LOG axis (NOT a valuation percentile). A date slider scrubs EOD
// snapshots; Play tweens positions smoothly between adjacent REAL snapshots (interpolation
// is visual only — tooltip/state read the real snapshot). Dragging the slider pauses +
// resets the tween (phase=0); the surface opens on the latest EOD. Click→pin, lasso→set
// global scope (Ocean is the first scope writer — C10).
const MODES: ColorMode[] = ['sector', 'theme']
const CLICK_SLOP2 = 16   // (4px)^2 — drags shorter than this count as a click (pin)
const STEP_MS = 1000     // ms per EOD transition during play (PRD §9.2: 900–1200ms)

function fmtCap(v: number | null): string {
  if (v == null) return '—'
  if (v >= 1e12) return '$' + (v / 1e12).toFixed(1) + 'T'
  if (v >= 1e9) return '$' + (v / 1e9).toFixed(1) + 'B'
  return '$' + (v / 1e6).toFixed(0) + 'M'
}

/** Hover tip (PRD §9.2): ticker / sector / riser evidence (rise_pct, net5/10/20, up-days,
 *  in-window drawdown, streak, candidate) / valuation evidence (P/S, EV/S, P/E, EV/EBITDA,
 *  freshness). The three DRAW fields (rise_pct / P/S / candidate) come from the bulk and show
 *  instantly; the other evidence fields live in the lazy per-stock OceanDetail (payload
 *  split). While that fetch is in flight `detail` is null and those rows show a `…` skeleton.
 *  All values are the REAL snapshot at date index `di` — never the interpolated play position. */
const LOADING = '…'
export function Tip({
  stock, draw, detail, di,
}: { stock: OceanStock; draw: OceanDrawPt; detail: OceanDetail | null; di: number }) {
  const loading = detail == null
  const net5 = detail?.net5[di] ?? null
  const net10 = detail?.net10[di] ?? null
  const net20 = detail?.net20[di] ?? null
  const up10 = detail?.up10[di] ?? null
  const ddw10 = detail?.ddw10[di] ?? null
  const streak = detail?.streak_days[di] ?? null
  const evs = detail?.evs[di] ?? null
  const pe = detail?.pe[di] ?? null
  const evEbitda = detail?.ev_ebitda[di] ?? null
  const fresh = detail?.freshness[di] ?? null
  // formal-filing PIT (PRD §10.5): the per-day availability date, honest as the slider scrubs.
  const effEod = detail?.as_of_effective_eod?.[di] ?? null
  const basis = detail?.valuation_basis
  return (
    <div className="otip">
      <div className="otip-h">
        <b>{stock.ticker}</b> <span className="dim">{stock.sector ?? '—'}</span>
      </div>
      <div className="otrow">
        <span>rise_pct</span>
        {/* color keys on the SEA LEVEL (visual reference); candidate comes ONLY from `cand` */}
        <b style={{ color: draw.rise_pct >= 90 ? 'var(--grn)' : 'var(--txt)' }}>
          {draw.rise_pct.toFixed(0)}{draw.candidate ? ' · 📈candidate' : ''}
        </b>
      </div>
      <div className="otrow"><span>net 5d/10d/20d</span><b>{loading ? LOADING : `${pct(net5)} / ${pct(net10)} / ${pct(net20)}`}</b></div>
      <div className="otrow">
        <span>上涨天数</span>
        <b>{loading ? LOADING : up10 != null ? `${Math.round(up10 * 10)}/10` : '—'}</b>
      </div>
      <div className="otrow"><span>窗口回撤</span><b>{loading ? LOADING : ddw10 != null ? (ddw10 * 100).toFixed(1) + '%' : '—'}</b></div>
      <div className="otrow"><span>连续在榜</span><b>{loading ? LOADING : streak != null ? `${streak}d` : '—'}</b></div>
      <div className="otrow"><span>P/S</span><b>{draw.ps != null ? draw.ps.toFixed(1) : 'n.m.'}</b></div>
      <div className="otrow"><span>EV/S</span><b>{loading ? LOADING : num(evs)}</b></div>
      <div className="otrow"><span>P/E</span><b>{loading ? LOADING : pe != null ? pe.toFixed(1) : 'n.m.'}</b></div>
      <div className="otrow"><span>EV/EBITDA</span><b>{loading ? LOADING : num(evEbitda)}</b></div>
      <div className="otrow"><span>val freshness</span><b>{loading ? LOADING : fresh ?? '—'}</b></div>
      {effEod != null && <div className="otrow"><span>formal filed</span><b>{effEod}</b></div>}
      <div className="otrow"><span>mkt cap</span><b>{fmtCap(stock.mktcap)}</b></div>
      {stock.themes.length > 0 && (
        <div className="otags">{stock.themes.map((t) => <span key={t.theme}>{t.theme}</span>)}</div>
      )}
      <div className="ohint">{basis === 'formal_filing_pit' ? 'formal-filing PIT · ' : ''}click to pin · drag to lasso · right-click → Stock</div>
    </div>
  )
}

export default function Ocean({
  initial,
  scope,
  setScope,
  pinned = [],
  setPinned,
  onOpen,
}: {
  initial?: OceanData
  scope: Scope
  setScope?: (s: Scope) => void
  pinned?: string[]
  setPinned?: (p: string[]) => void
  onOpen?: (t: string) => void
}) {
  const [data, setData] = useState<OceanData | null>(initial ?? null)
  const [err, setErr] = useState<string | null>(null)
  const [colorBy, setColorBy] = useState<ColorMode>('sector')
  // theme color mode needs a selected theme; the picker arrives with a later milestone.
  const [activeTheme] = useState<string | null>(null)
  const [dateIndex, setDateIndex] = useState<number | null>(null) // null = follow latest
  const [playing, setPlaying] = useState(false)
  const [hover, setHover] = useState<DrawnPoint | null>(null)
  const [detail, setDetail] = useState<OceanDetail | null>(null) // hovered stock's lazy hover detail (null = loading/absent)
  const detailCache = useRef<Map<string, OceanDetail>>(new Map())
  const [lasso, setLasso] = useState<Rect | null>(null)

  const cv = useRef<HTMLCanvasElement>(null)
  const pos = useRef<DrawnPoint[]>([])          // last-drawn (interpolated) positions, for hit-testing
  const down = useRef<{ x: number; y: number } | null>(null)
  const paletteRef = useRef<Palette>({})
  // animation refs (the rAF loop owns phase + the live date index; React state mirrors them
  // so the slider/label re-render, but per-frame tweening never re-renders React — NFR-8).
  const phaseRef = useRef(0)
  const diRef = useRef(0)
  const playingRef = useRef(false)
  const rafRef = useRef<number | null>(null)
  const lastTsRef = useRef<number | null>(null)
  // the rAF loop calls the LATEST draw closure (refreshed every render) so it sees current
  // colorBy / scope / hover / pinned without being re-created.
  const drawRef = useRef<() => void>(() => {})

  useEffect(() => {
    if (initial) return
    const ac = new AbortController()
    loadOcean(ac.signal)
      .then(setData)
      .catch((e) => {
        if (!ac.signal.aborted) setErr(String(e))
      })
    return () => ac.abort()
  }, [initial])

  // Lazily fetch the hovered stock's per-stock hover detail (v3 split): the bulk carries only
  // the 3 draw fields, so the tooltip's 9 evidence fields load on demand, per name. Cached per
  // ticker; the effect's cleanup aborts an in-flight fetch when the hover moves, so a stale
  // ticker's detail never lands. Applied only when it aligns to the bulk window (n===dates).
  useEffect(() => {
    const tk = hover?.ticker ?? null
    if (!tk) {
      setDetail(null)
      return
    }
    const cached = detailCache.current.get(tk)
    if (cached) {
      setDetail(cached)
      return
    }
    setDetail(null) // show the `…` skeleton until it arrives
    const ac = new AbortController()
    loadOceanDetail(tk, ac.signal)
      .then((d) => {
        if (!data || d.n !== data.dates.length) return // misaligned (transient partial deploy) — ignore
        detailCache.current.set(tk, d)
        setDetail(d)
      })
      .catch(() => {
        /* aborted or missing — tooltip keeps the 3 draw fields, `…` for the rest */
      })
    return () => ac.abort()
  }, [hover?.ticker, data])

  // ocean.json must be schema v5 (steady-riser columns: ps/rise_pct/cand). A frontend-only
  // deploy can transiently serve an OLD v1–v4 payload until a nightly re-export lands —
  // guard so the surface degrades to a notice instead of crashing on the columns.
  const okSchema = !!data && data.schema_version === 5 && Array.isArray(data.dates) && !!data.axis
  // Effective date index: scrubbed value, else the latest snapshot.
  const di = okSchema ? dateIndex ?? data!.dates.length - 1 : 0
  useEffect(() => {
    diRef.current = di
  }, [di])

  // draw closure — refreshed every render (sees current state); called by the redraw effect
  // and by the rAF play loop. Reads diRef/phaseRef so the loop can advance without re-render.
  drawRef.current = () => {
    const c = cv.current
    if (!c || !data || !okSchema) return
    const ctx = c.getContext('2d')
    if (!ctx) return
    const g = OCEAN_GEOM
    if (c.width !== g.w * 2) {
      c.width = g.w * 2
      c.height = g.h * 2
    }
    ctx.setTransform(2, 0, 0, 2, 0, 0)
    pos.current = drawOcean(ctx, {
      data, dateIndex: diRef.current, phase: phaseRef.current,
      colorBy, activeTheme, scope, palette: paletteRef.current,
      hover: hover?.ticker ?? null, pinned, lassoRect: lasso,
    })
  }

  // resolve the palette once in the browser (theme.css owns the hex), then redraw.
  useEffect(() => {
    paletteRef.current = resolvePalette(document.documentElement)
    drawRef.current()
  }, [data])

  // declarative redraw after every commit (data load / colorBy / scope / hover / pin / lasso /
  // a scrubbed dateIndex). The play loop draws its own frames imperatively.
  useEffect(() => {
    drawRef.current()
  })

  const pause = () => {
    playingRef.current = false
    setPlaying(false)
    if (rafRef.current != null) cancelAnimationFrame(rafRef.current)
    rafRef.current = null
    lastTsRef.current = null
  }

  const tick = (ts: number) => {
    if (!playingRef.current || !data) return
    if (lastTsRef.current == null) lastTsRef.current = ts
    const dt = Math.min(ts - lastTsRef.current, STEP_MS) // cap dt so a tab refocus doesn't jump
    lastTsRef.current = ts
    let ph = phaseRef.current + dt / STEP_MS
    let idx = diRef.current
    const last = data.dates.length - 1
    while (ph >= 1) {
      ph -= 1
      idx += 1
      if (idx >= last) {
        idx = last
        ph = 0
        pause() // reached the latest EOD → auto-stop (PRD §9.2)
        break
      }
    }
    phaseRef.current = ph
    if (idx !== diRef.current) {
      diRef.current = idx
      setDateIndex(idx)
    }
    drawRef.current()
    if (playingRef.current) rafRef.current = requestAnimationFrame(tick)
  }

  const play = () => {
    if (!data) return
    const last = data.dates.length - 1
    if (diRef.current >= last) {
      // at the end → replay from the oldest snapshot.
      diRef.current = 0
      setDateIndex(0)
    }
    phaseRef.current = 0
    lastTsRef.current = null
    playingRef.current = true
    setPlaying(true)
    rafRef.current = requestAnimationFrame(tick)
  }

  // cleanup the loop on unmount.
  useEffect(() => () => {
    playingRef.current = false
    if (rafRef.current != null) cancelAnimationFrame(rafRef.current)
  }, [])

  const goto = (i: number) => {
    pause()
    phaseRef.current = 0
    const idx = data ? clamp(i, 0, data.dates.length - 1) : 0
    diRef.current = idx
    setDateIndex(idx)
  }

  const toLogical = (e: React.MouseEvent): [number, number] => {
    const c = cv.current!
    const r = c.getBoundingClientRect()
    return [(e.clientX - r.left) * (OCEAN_GEOM.w / r.width), (e.clientY - r.top) * (OCEAN_GEOM.h / r.height)]
  }
  const togglePin = (id: string) => {
    setPinned?.(pinned.includes(id) ? pinned.filter((t) => t !== id) : [...pinned, id])
  }
  const onDown = (e: React.MouseEvent) => {
    if (e.button !== 0) return // left-drag/pin only; right-click is handled by onContextMenu
    pause() // interacting → stop the tween so hit-tests hit a stable frame
    const [lx, ly] = toLogical(e)
    down.current = { x: lx, y: ly }
    setLasso({ x0: lx, y0: ly, x1: lx, y1: ly })
    setHover(null)
  }
  const onMove = (e: React.MouseEvent) => {
    const [lx, ly] = toLogical(e)
    if (down.current) {
      setLasso((r) => (r ? { ...r, x1: lx, y1: ly } : r))
      return
    }
    const id = nearestPoint(pos.current, lx, ly)
    setHover(id != null ? pos.current.find((p) => p.ticker === id) ?? null : null)
  }
  const onUp = (e: React.MouseEvent) => {
    const [lx, ly] = toLogical(e)
    const d = down.current
    const rect = lasso
    down.current = null
    setLasso(null)
    if (!d) return
    const moved = (lx - d.x) ** 2 + (ly - d.y) ** 2 > CLICK_SLOP2
    if (!moved) {
      const id = nearestPoint(pos.current, lx, ly) // click → toggle pin
      if (id) togglePin(id)
    } else if (rect) {
      const sel = pointsInRect(pos.current, rect) // drag → lasso sets the global scope
      setPinned?.(sel)
      setScope?.({ kind: 'pinned', key: null })
    }
  }
  const onLeave = () => {
    setHover(null)
    down.current = null
    setLasso(null)
  }
  // right-click a dot → load that ticker into the Stock surface + jump there (reuses App.openStock,
  // the same path a Discovery card / Valuation row takes). preventDefault only on a HIT, so a
  // right-click on empty canvas still yields the browser's native menu.
  const onContextMenu = (e: React.MouseEvent) => {
    const [lx, ly] = toLogical(e)
    const id = nearestPoint(pos.current, lx, ly)
    if (!id) return
    e.preventDefault()
    pause()
    onOpen?.(id)
  }

  if (err) {
    return (
      <div className="placeholder">
        <div className="ph-tag">NO DATA</div>
        <div className="ph-msg">
          ocean.json 未就绪（{err}）。先跑 <code>make fixture-pipeline</code> 或真实 <code>make pipeline</code>，再{' '}
          <code>python export/ocean.py</code> 生成 web/public/data/ocean.json。
        </div>
      </div>
    )
  }
  if (!data) {
    return (
      <div className="placeholder">
        <div className="ph-tag">LOADING</div>
        <div className="ph-msg">读取 Ocean 日度快照…</div>
      </div>
    )
  }
  if (!okSchema) {
    // 旧 schema（v1）—— 仅前端部署时数据 artifact 还是旧的（M8 数据契约错配）。
    return (
      <div className="placeholder">
        <div className="ph-tag">数据升级中</div>
        <div className="ph-msg">
          ocean.json 为旧 schema（v{data.schema_version ?? '?'}）。Ocean 需要 schema v5（steady-riser 列）—— 触发一次{' '}
          <code>nightly.yml</code> 重算生产数据（仅 push web 不更新数据，见 PROJECT-STATUS §6）。
        </div>
      </div>
    )
  }

  const isLatest = di === data.dates.length - 1
  // tooltip reads a REAL snapshot at the resting frame (phase 0 → the current date's draw pt).
  // hoverDi = the date index that snapshot maps to (di, or di+1 when di is a gap that fades in),
  // so the lazy detail is read at the SAME index the draw fields came from.
  const hoverStock = hover ? data.stocks.find((s) => s.ticker === hover.ticker) : undefined
  const hPrev = hoverStock ? drawPtAt(hoverStock, di) : null
  const hNext = hoverStock ? (isLatest ? hPrev : drawPtAt(hoverStock, di + 1)) : null
  const hoverDraw = hoverStock ? interpolateOceanPoint(hPrev, hNext, 0)?.snap ?? null : null
  const hoverDi = hPrev ? di : Math.min(di + 1, data.dates.length - 1)

  return (
    <div className="ocean">
      <div className="oc-ctrl">
        <div className="ocmodes" role="group" aria-label="color mode">
          {MODES.map((m) => (
            <button
              key={m}
              className={'ocmode' + (colorBy === m ? ' on' : '')}
              onClick={() => setColorBy(m)}
            >
              {m}
            </button>
          ))}
        </div>
        <div className="ocscrub">
          {pinned.length > 0 && <span className="ocpins">📌 {pinned.length} pinned</span>}
          <span className="ocdate">
            {data.dates[di]}
            {isLatest ? ' · latest EOD' : ''}
          </span>
        </div>
      </div>

      <div className="ocwrap">
        <canvas
          ref={cv}
          className="occanvas"
          style={{ aspectRatio: `${OCEAN_GEOM.w} / ${OCEAN_GEOM.h}` }}
          onMouseDown={onDown}
          onMouseMove={onMove}
          onMouseUp={onUp}
          onMouseLeave={onLeave}
          onContextMenu={onContextMenu}
        />
        <div className="oax-x">P/S (log) → (便宜 · 贵)</div>
        <div className="oax-y">rise_pct ↑ (连续上涨强度 · 10 日净涨幅百分位)</div>
        <div className="oquad">↑ 海平面 = 90（视觉参考线，candidate 由 compute 判定）</div>
        {hover && hoverStock && hoverDraw && (
          <div
            className="otipwrap"
            style={{ left: `${(hover.px / OCEAN_GEOM.w) * 100}%`, top: `${(hover.py / OCEAN_GEOM.h) * 100}%` }}
          >
            <Tip
              stock={hoverStock}
              draw={hoverDraw}
              detail={detail?.ticker === hoverStock.ticker ? detail : null}
              di={hoverDi}
            />
          </div>
        )}
      </div>

      <div className="octimeline">
        <button className="octl-btn" onClick={() => (playing ? pause() : play())} aria-label={playing ? 'pause' : 'play'}>
          {playing ? '⏸' : '▶'}
        </button>
        <button className="octl-btn" onClick={() => goto(di - 1)} disabled={di <= 0} aria-label="prev day">
          ◀
        </button>
        <input
          className="ocrange"
          type="range"
          min={0}
          max={data.dates.length - 1}
          step={1}
          value={di}
          onChange={(e) => goto(parseInt(e.target.value, 10))}
          aria-label="date slider"
        />
        <button className="octl-btn" onClick={() => goto(di + 1)} disabled={isLatest} aria-label="next day">
          ▶
        </button>
        <span className="ocdaten">
          {di + 1}/{data.dates.length}
        </span>
      </div>

      <div className="foot">
        <b>连续上涨强度 × Valuation 二维相图</b>：纵轴 = rise_pct（<b>10 日净涨幅横截面百分位</b>，PRD §10.8），<b>海平面 = 90</b>
        （top decile，<b>仅视觉参考线</b>——「过去两周涨幅进全市场前 10%」）；candidate（📈 光晕 + 亮环）= Risers 榜同一道 gate + top-N，
        flag 由 compute 层单一真源写出、前端只读<b>绝不重算</b>（candidate ≠ y≥90，gate 含 up10 条件且 top-N 截断），与 Risers 候选逐票可追溯（C9）。横轴 =
        <b> 原始 trailing P/S（log 轴）</b>，不是估值百分位、无综合估值分。点大小 = √市值；颜色按 {colorBy}。拖<b>日期滑杆</b>切 EOD；
        <b>▶ Play</b> 在相邻真实快照间平滑插值移动（仅视觉，tooltip/状态取真实快照，不伪造交易日）；
        <b>点击 pin</b>、<b>框选 lasso</b> → set 全局 scope（跨 tab 同步、可一键清）；<b>右键点 dot</b> → 在 Stock tab 打开该票。as_of {data.as_of_date} · {data.count} 点 ·
        P/S 域 [{data.x_domain[0]}, {data.x_domain[1]}]。
      </div>
    </div>
  )
}
