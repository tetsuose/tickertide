import { describe, it, expect } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import Rotation from './Rotation'
import sample from '../lib/__fixtures__/rotation.sample.json'
import themeSample from '../lib/__fixtures__/rotation.theme.sample.json'
import type { RotationData, Scope } from '../types'
import { multiScale, linePath, soloScale, soloSegments, endLabels } from '../lib/rotation-draw'

// SSR-render the Rotation surface from the committed export fixture (rotation.sample.json,
// export/rotation.py's real output on the offline fixture). SVG charts render fully under
// renderToStaticMarkup (unlike canvas), so we can assert the multi-line + drill markup +
// the pure-geometry helpers without a browser. AC-M3: ≥11 lines, 4 states, N=1 drill.
const data = sample as unknown as RotationData
const ALL: Scope = { kind: 'all', key: null }

describe('Rotation overview (scope=all)', () => {
  const html = renderToStaticMarkup(<Rotation initial={data} scope={ALL} />)

  it('draws one RS-Ratio line per bucket (≥11 sectors on one chart)', () => {
    const paths = html.match(/<path /g) ?? []
    expect(paths.length).toBe(data.count)
    expect(paths.length).toBeGreaterThanOrEqual(11)
  })

  it('shows every rotation state that exists in the data', () => {
    const states = new Set(data.buckets.map((b) => b.state))
    expect(states.size).toBeGreaterThanOrEqual(2)
    for (const s of states) expect(html).toContain(s)
  })

  it('lists every sector in the league + the y=100 SPY baseline', () => {
    for (const b of data.buckets) expect(html).toContain(b.bucket)
    expect(html).toContain('= SPY (100)')
  })

  it('surfaces the transparent-reconstruction params (audit, not a StockCharts replica)', () => {
    expect(html).toContain('n1=' + data.params.n1_ema)
    expect(html).toContain('不复刻 StockCharts')
  })
})

describe('Rotation drill (scope=sector)', () => {
  const sec = data.buckets[0].bucket
  const html = renderToStaticMarkup(<Rotation initial={data} scope={{ kind: 'sector', key: sec }} />)

  it('drills to the N=1 solo line + sector summary', () => {
    expect(html).toContain(sec)
    expect(html).toContain('单条放大')
    expect(html).toContain('momentum') // SoloRSLine axis label = slope color
  })

  it('offers the "see all members in Discovery" scope+jump action', () => {
    expect(html).toContain('在 Discovery 看全部成员')
  })
})

describe('Rotation theme mode (M4.4)', () => {
  const themeData = themeSample as unknown as RotationData
  const overview = renderToStaticMarkup(<Rotation initial={themeData} scope={ALL} />)

  it('renders one RS-Ratio line per theme — not the old M4 placeholder', () => {
    const paths = overview.match(/<path /g) ?? []
    expect(paths.length).toBe(themeData.count)
    expect(themeData.bucket_type).toBe('theme')
    expect(overview).not.toContain('待 M4')
  })

  it('colors theme lines with THEME_VAR (--th-*) and lists each theme', () => {
    expect(overview).toContain('--th-') // theme color vars, not sector --dim2 fallback
    for (const b of themeData.buckets) expect(overview).toContain(b.bucket)
  })

  it('flags the point-in-time / non-market-cap basis (C3/C4)', () => {
    expect(overview).toContain('非市值加权')
  })

  it('drills a theme (scope.kind=theme) → N=1 solo line + member preview', () => {
    const th = themeData.buckets[0].bucket
    const html = renderToStaticMarkup(<Rotation initial={themeData} scope={{ kind: 'theme', key: th }} />)
    expect(html).toContain(th)
    expect(html).toContain('单条放大')
    expect(html).toContain('在 Discovery 看全部成员')
  })
})

describe('rotation-draw geometry (pure)', () => {
  it('multiScale brackets the 100 baseline', () => {
    const sc = multiScale(data.buckets.map((b) => b.rs_ratio))
    expect(sc.lo).toBeLessThan(100)
    expect(sc.hi).toBeGreaterThan(100)
  })

  it('linePath breaks the line on nulls (no fabricated segments)', () => {
    const sc = multiScale([[100, 102]])
    const p = linePath([100, null, 102], sc)
    expect((p.match(/M/g) ?? []).length).toBe(2) // null splits into two move-tos
  })

  it('soloSegments colors each step by the short-window slope', () => {
    const s = [100, 101, 102, 103]
    const segs = soloSegments(s, soloScale(s))
    expect(segs.length).toBe(s.length - 1)
    expect(segs.every((g) => g.up)).toBe(true) // monotonic rise → all green
  })

  it('endLabels stack the right-edge labels without overlap', () => {
    const sc = multiScale(data.buckets.map((b) => b.rs_ratio))
    const ends = endLabels(
      data.buckets.map((b) => ({ key: b.bucket, name: b.bucket, colorVar: '--x', series: b.rs_ratio })),
      sc,
    )
    for (let i = 1; i < ends.length; i++) {
      expect(ends[i].y - ends[i - 1].y).toBeGreaterThanOrEqual(13 - 1e-6)
    }
  })
})
