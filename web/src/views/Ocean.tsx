import { useEffect, useRef, useState } from 'react'
import type { OceanData, Scope } from '../types'
import { loadOcean } from '../lib/data'
import { drawOcean, resolvePalette, OCEAN_GEOM, type ColorMode } from '../lib/ocean-draw'

// Ocean (PRD §9.2): the wide-explore canvas scatter on a FIXED RS×Valuation plane
// (x = RS percentile weak→strong, y = Valuation percentile bottom=cheap→top=dear),
// (50,50) crosshair, a green strong+cheap quadrant = the emerging-leader corner.
// M2.2 skeleton renders the LATEST week as a static scatter with sector/theme/
// quadrant color modes and √market-cap sizing. Scrubber + hover land in M2.3;
// pin→trail + lasso→scope in M2.4. `initial` lets tests/SSR inject without fetching.
const MODES: ColorMode[] = ['sector', 'theme', 'quadrant']

export default function Ocean({ initial, scope }: { initial?: OceanData; scope: Scope }) {
  const [data, setData] = useState<OceanData | null>(initial ?? null)
  const [err, setErr] = useState<string | null>(null)
  const [colorBy, setColorBy] = useState<ColorMode>('sector')
  // theme color mode needs a selected theme; the picker arrives with M4 memberships
  // (data.themes is empty until then), so it stays null for now.
  const [activeTheme] = useState<string | null>(null)
  const cv = useRef<HTMLCanvasElement>(null)

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

  // M2.2: always the latest week (newest snapshot). The scrubber drives this in M2.3.
  const week = data ? data.n_weeks - 1 : 0

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
    drawOcean(ctx, { data, week, colorBy, activeTheme, scope, palette })
  }, [data, week, colorBy, activeTheme, scope])

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
        <span className="ocweek">
          WEEK {week + 1}/{data.n_weeks} · {data.weeks[week]}
        </span>
      </div>

      <div className="ocwrap">
        <canvas
          ref={cv}
          className="occanvas"
          style={{ aspectRatio: `${OCEAN_GEOM.w} / ${OCEAN_GEOM.h}` }}
        />
        <div className="oax-x">RS percentile → (weak · strong)</div>
        <div className="oax-y">Valuation ↑ (cheap · expensive)</div>
        <div className="oquad">cheap &amp; strengthening</div>
      </div>

      <div className="foot">
        固定轴 <b>RS percentile × Valuation percentile</b>（底 = 便宜）；右下绿象限 = 强 + 便宜 = 要找的 emerging
        leader。点大小 = √市值；颜色按 {colorBy}（sector / theme / quadrant 可切）。as_of {data.as_of_date} ·{' '}
        {data.count} 点 · metric {data.metric}。周度 scrubber + hover（M2.3）、pin→trail + lasso 框选 set scope（M2.4）随后接入。
      </div>
    </div>
  )
}
