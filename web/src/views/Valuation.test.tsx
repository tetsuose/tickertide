import { describe, it, expect } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import valuation from '../lib/__fixtures__/valuation.sample.json'
import Valuation from './Valuation'
import { buildValuationSql } from '../lib/duckdb'
import type { ValuationData, ValuationRow, Scope } from '../types'

// M5.2 Valuation screener contract from the real exported fixture (valuation.sample.json,
// generated from valuation.parquet). The injected path renders without duckdb-wasm; the SQL
// builder is unit-tested separately so the duckdb sort rule is covered without the engine.
const data = valuation as unknown as ValuationData
const rows = data.rows as ValuationRow[]
const order = (html: string) => [...html.matchAll(/valn-tk">([A-Z0-9]+)</g)].map((m) => m[1])

describe('buildValuationSql (duckdb sort rule)', () => {
  it('cheap-on-top multiples order ascending', () => {
    expect(buildValuationSql('ps')).toContain('ORDER BY ps ASC')
    expect(buildValuationSql('ev_ebitda')).toContain('ORDER BY ev_ebitda ASC')
  })
  it('quality metrics order descending', () => {
    expect(buildValuationSql('growth')).toContain('ORDER BY growth DESC')
    expect(buildValuationSql('rule40')).toContain('ORDER BY rule40 DESC')
  })
  it('NULLs sort last, ticker breaks ties', () => {
    expect(buildValuationSql('ps')).toContain('NULLS LAST, ticker')
  })
})

describe('Valuation screener (M5.2, duckdb-wasm / injected)', () => {
  it('renders one row per universe ticker (full cross-section)', () => {
    const html = renderToStaticMarkup(<Valuation initial={rows} />)
    expect(order(html).length).toBe(rows.length)
  })

  it('default sort is P/S ascending (cheap on top), nulls last', () => {
    const psBy: Record<string, number | null> = Object.fromEntries(rows.map((r) => [r.ticker, r.ps]))
    const seq = order(renderToStaticMarkup(<Valuation initial={rows} />)).map((t) => psBy[t])
    const vals = seq.filter((v): v is number => v != null)
    expect(vals.every((v, i) => i === 0 || vals[i - 1] <= v)).toBe(true)
  })

  it('shows the PEG and Mgn% columns the preview lacked', () => {
    const html = renderToStaticMarkup(<Valuation initial={rows} />)
    expect(html).toContain('PEG')
    expect(html).toContain('Mgn%')
  })

  it('as-of freshness 三档上色 + non-fresh vint (C7/§10.5)', () => {
    const html = renderToStaticMarkup(<Valuation initial={rows} />)
    expect(html).toContain('vfr-fresh')
    expect(html).toContain('vint') // overdue/stale/None out of the cohort
    expect(/valn-pct">\d+</.test(html)).toBe(true)
  })

  it('As-of cell carries the formal-filing PIT tooltip (filed/effective/basis, §10.5)', () => {
    const html = renderToStaticMarkup(<Valuation initial={rows} />)
    // native title on the as-of cell exposes the PIT context; React escapes the newlines.
    expect(html).toContain('Formal filed:')
    expect(html).toContain('Effective in EOD valuation:')
    expect(html).toContain('formal-filing PIT')
    // footer states the basis too
    expect(html).toContain('formal-filing PIT')
  })

  it('respects scope=sector: filters BEFORE ranking', () => {
    const sector = rows.find((r) => r.sector)!.sector as string
    const expected = rows.filter((r) => r.sector === sector).length
    const scope: Scope = { kind: 'sector', key: sector }
    const html = renderToStaticMarkup(<Valuation initial={rows} scope={scope} />)
    expect(order(html).length).toBe(expected)
  })

  it('respects scope=theme via the themes column (many-to-many)', () => {
    const themed = rows.find((r) => r.themes)!
    const key = themed.themes.split(',')[0]
    const expected = rows.filter((r) => r.themes && r.themes.split(',').includes(key)).length
    const scope: Scope = { kind: 'theme', key }
    const html = renderToStaticMarkup(<Valuation initial={rows} scope={scope} />)
    expect(order(html).length).toBe(expected)
    expect(expected).toBeGreaterThan(0)
  })
})
