import { describe, it, expect } from 'vitest'
import { dataAgeDays, freshness, ageLabel } from './freshness'

// D.4 freshness helpers behind the header as_of badge. Pure + UTC-normalized so the
// thresholds (fresh ≤3d covering a weekend, aging ≤7d, stale beyond) are deterministic.

describe('dataAgeDays', () => {
  it('= calendar days from as_of to today, time-of-day independent', () => {
    expect(dataAgeDays('2026-06-05', new Date('2026-06-06T10:00:00Z'))).toBe(1)
    expect(dataAgeDays('2026-06-05', new Date('2026-06-05T23:59:00Z'))).toBe(0)
    expect(dataAgeDays('2026-06-05', new Date('2026-06-12T00:00:00Z'))).toBe(7)
  })
  it('NaN on missing / unparseable as_of', () => {
    expect(dataAgeDays(null, new Date())).toBeNaN()
    expect(dataAgeDays('', new Date())).toBeNaN()
    expect(dataAgeDays('not-a-date', new Date('2026-06-06T00:00:00Z'))).toBeNaN()
  })
})

describe('freshness thresholds', () => {
  it('≤3 fresh · ≤7 aging · else stale', () => {
    expect(freshness(0)).toBe('fresh')
    expect(freshness(3)).toBe('fresh')
    expect(freshness(4)).toBe('aging')
    expect(freshness(7)).toBe('aging')
    expect(freshness(8)).toBe('stale')
  })
  it('NaN / negative (future as_of) → stale (suspect, never silently fresh)', () => {
    expect(freshness(NaN)).toBe('stale')
    expect(freshness(-1)).toBe('stale')
  })
})

describe('ageLabel', () => {
  it('today / N 天前 / stale warning / unknown', () => {
    expect(ageLabel(0)).toBe('当日数据')
    expect(ageLabel(2)).toBe('2 天前')
    expect(ageLabel(10)).toContain('数据陈旧')
    expect(ageLabel(NaN)).toBe('数据未就绪')
  })
})
