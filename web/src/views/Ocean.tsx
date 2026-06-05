import { useEffect, useRef, useState } from 'react'
import type { OceanData, OceanStock, OceanPt, Scope } from '../types'
import { loadOcean } from '../lib/data'
import {
  drawOcean, nearestPoint, resolvePalette, OCEAN_GEOM,
  type ColorMode, type DrawnPoint,
} from '../lib/ocean-draw'

// Ocean (PRD §9.2): the wide-explore canvas scatter on a FIXED RS×Valuation plane
// (x = RS percentile weak→strong, y = Valuation percentile bottom=cheap→top=dear),
// (50,50) crosshair, a green strong+cheap quadrant = the emerging-leader corner.
// M2.2 rendered the latest week statically; M2.3 adds the manual WEEK scrubber (no
// autoplay — C2) and a hover nearest-neighbor tip. Pin→trail + lasso→scope: M2.4.
// `initial` lets tests/SSR inject without fetching.
const MODES: ColorMode[] = ['sector', 'theme', 'quadrant']

function fmtCap(v: number | null): string {
  if (v == null) return '—'
  if (v >= 1e12) return '$' + (v / 1e12).toFixed(1) + 'T'
  if (v >= 1e9) return '$' + (v / 1e9).toFixed(1) + 'B'
  return '$' + (v / 1e6).toFixed(0) + 'M'
}

/** Hover tip (PRD §9.2): ticker / sector / RS pct / Val pct / P/S / mkt cap / themes. */
export function Tip({ stock, pt }: { stock: OceanStock; pt: OceanPt }) {
  return (
    <div className="otip">
      <div className="otip-h">
        <b>{stock.ticker}</b> <span className="dim">{stock.sector ?? '—'}</span>
      </div>
      <div className="otrow"><span>RS pct</span><b>{pt.rs.toFixed(0)}</b></div>
      <div className="otrow"><span>Val pct</span><b>{pt.val.toFixed(0)}</b></div>
      <div className="otrow"><span>P/S</span><b>{pt.ps != null ? pt.ps.toFixed(1) : 'n.m.'}</b></div>
      <div className="otrow"><span>Mkt cap</span><b>{fmtCap(stock.mktcap)}</b></div>
      {stock.themes.length > 0 && (
        <div className="otags">
          {stock.themes.map((t) => (
            <span key={t.theme}>{t.theme}</span>
          ))}
        </div>
      )}
      <div className="ohint">click to pin / track (M2.4)</div>
    </div>
  )
}

export default function Ocean({ initial, scope }: { initial?: OceanData; scope: Scope }) {
  const [data, setData] = useState<OceanData | null>(initial ?? null)
  const [err, setErr] = useState<string | null>(null)
  const [colorBy, setColorBy] = useState<ColorMode>('sector')
  // theme color mode needs a selected theme; the picker arrives with M4 memberships.
  const [activeTheme] = useState<string | null>(null)
  const [week, setWeek] = useState<number | null>(null) // null = follow latest until scrubbed
  const [hover, setHover] = useState<DrawnPoint | null>(null)
  const cv = useRef<HTMLCanvasElement>(null)
  const pos = useRef<DrawnPoint[]>([]) // last-drawn point positions, for hit-testing

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

  // Effective week: scrubbed value, else the latest snapshot.
  const wk = data ? week ?? data.n_weeks - 1 : 0

  useEffect(() => {
    const c = cv.current
    if (!c || !data) return
    const ctx = c.getContext('2d')
    if (!ctx) return
    const g = OCEAN_GEOM
    c.width = g.w * 2
    c.height = g.h * 2
    ctx.setTransform(2, 0, 0, 2, 0, 0)
    const palette = resolvePalette(document.documentElement)
    pos.current = drawOcean(ctx, {
      data, week: wk, colorBy, activeTheme, scope, palette, hover: hover?.ticker ?? null,
    })
  }, [data, wk, colorBy, activeTheme, scope, hover])

  const toLogical = (e: React.MouseEvent): [number, number] => {
    const c = cv.current!
    const r = c.getBoundingClientRect()
    return [(e.clientX - r.left) * (OCEAN_GEOM.w / r.width), (e.clientY - r.top) * (OCEAN_GEOM.h / r.height)]
  }
  const onMove = (e: React.MouseEvent) => {
    const [lx, ly] = toLogical(e)
    const id = nearestPoint(pos.current, lx, ly)
    setHover(id != null ? pos.current.find((p) => p.ticker === id) ?? null : null)
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
        <div className="ph-msg">读取 Ocean 周度快照…</div>
      </div>
    )
  }

  const hoverStock = hover ? data.stocks.find((s) => s.ticker === hover.ticker) : undefined
  const hoverPt = hoverStock ? hoverStock.pts[wk] : null

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
          <span className="ocweek">
            WEEK {wk + 1}/{data.n_weeks} · {data.weeks[wk]}
          </span>
          <input
            className="ocrange"
            type="range"
            min={0}
            max={data.n_weeks - 1}
            step={1}
            value={wk}
            onChange={(e) => setWeek(parseInt(e.target.value, 10))}
            aria-label="week scrubber"
          />
        </div>
      </div>

      <div className="ocwrap">
        <canvas
          ref={cv}
          className="occanvas"
          style={{ aspectRatio: `${OCEAN_GEOM.w} / ${OCEAN_GEOM.h}` }}
          onMouseMove={onMove}
          onMouseLeave={() => setHover(null)}
        />
        <div className="oax-x">RS percentile → (weak · strong)</div>
        <div className="oax-y">Valuation ↑ (cheap · expensive)</div>
        <div className="oquad">cheap &amp; strengthening</div>
        {hover && hoverStock && hoverPt && (
          <div
            className="otipwrap"
            style={{ left: `${(hover.px / OCEAN_GEOM.w) * 100}%`, top: `${(hover.py / OCEAN_GEOM.h) * 100}%` }}
          >
            <Tip stock={hoverStock} pt={hoverPt} />
          </div>
        )}
      </div>

      <div className="foot">
        固定轴 <b>RS percentile × Valuation percentile</b>（底 = 便宜）；右下绿象限 = 强 + 便宜 = 要找的 emerging
        leader。拖 WEEK 滑杆切周（手动，无 autoplay）；悬停出最近点 tip。点大小 = √市值；颜色按 {colorBy}。as_of{' '}
        {data.as_of_date} · {data.count} 点 · metric {data.metric}。pin→trail + lasso 框选 set scope（M2.4）随后接入。
      </div>
    </div>
  )
}
