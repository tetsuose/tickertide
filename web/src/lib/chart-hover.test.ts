import { describe, it, expect } from 'vitest'
import {
  viewBoxXFromClient, bandIndexAt, pointIndexAt, nearestSeriesAt, axisTickIndices, tickDate,
} from './chart-hover'

// Pure geometry for the hover time-cursor. These run with no DOM (the components feed
// getBoundingClientRect numbers in), so the index math is fully assertable here.

describe('viewBoxXFromClient', () => {
  it('scales a client pixel into viewBox units (render width ≠ viewBox width)', () => {
    // svg viewBox W=880 rendered 440px wide at left=100 → 2 viewBox units per pixel
    expect(viewBoxXFromClient(100, 100, 440, 880)).toBe(0)
    expect(viewBoxXFromClient(320, 100, 440, 880)).toBe(440)
    expect(viewBoxXFromClient(540, 100, 440, 880)).toBe(880)
  })
  it('is defensive on zero width', () => {
    expect(viewBoxXFromClient(50, 0, 0, 880)).toBe(0)
  })
})

describe('bandIndexAt (MiniChart / StockStack)', () => {
  // W=100, PL=0, PR=0, n=10 → bw=10, centers at 5,15,...,95
  it('floors the cursor into its band', () => {
    expect(bandIndexAt(5, 0, 0, 100, 10)).toBe(0)
    expect(bandIndexAt(12, 0, 0, 100, 10)).toBe(1)
    expect(bandIndexAt(99, 0, 0, 100, 10)).toBe(9)
  })
  it('clamps within a half-cell tolerance, null beyond it', () => {
    expect(bandIndexAt(-2, 0, 0, 100, 10)).toBe(0) // within half cell (5) left of PL
    expect(bandIndexAt(104, 0, 0, 100, 10)).toBe(9) // within half cell right of plot
    expect(bandIndexAt(-9, 0, 0, 100, 10)).toBeNull()
    expect(bandIndexAt(120, 0, 0, 100, 10)).toBeNull()
  })
  it('returns null for empty / degenerate geometry', () => {
    expect(bandIndexAt(5, 0, 0, 100, 0)).toBeNull()
    expect(bandIndexAt(5, 60, 60, 100, 10)).toBeNull() // PL+PR ≥ W
  })
})

describe('pointIndexAt (Rotation RS-Ratio)', () => {
  // W=100, padL=0, padR=0, n=11 → step=10, points at 0,10,...,100
  it('rounds the cursor to the nearest point', () => {
    expect(pointIndexAt(0, 0, 0, 100, 11)).toBe(0)
    expect(pointIndexAt(14, 0, 0, 100, 11)).toBe(1) // 14 rounds to 10 → idx 1
    expect(pointIndexAt(16, 0, 0, 100, 11)).toBe(2) // 16 rounds to 20 → idx 2
    expect(pointIndexAt(100, 0, 0, 100, 11)).toBe(10)
  })
  it('handles n==1 and degenerate cases', () => {
    expect(pointIndexAt(50, 0, 0, 100, 1)).toBe(0)
    expect(pointIndexAt(50, 0, 0, 100, 0)).toBeNull()
  })
})

describe('nearestSeriesAt (which line the cursor reads)', () => {
  const yOf = (v: number) => 100 - v // higher value = smaller y
  it('picks the series closest to the cursor y, skipping nulls', () => {
    const series = [
      [10, 20, 30], // yOf at idx1 = 80
      [40, 50, 60], // yOf at idx1 = 50
      [null, null, null],
    ]
    // cursor near y=52 at column 1 → series 1 (y=50) wins
    expect(nearestSeriesAt(series, 1, 52, yOf)).toBe(1)
    expect(nearestSeriesAt(series, 1, 79, yOf)).toBe(0)
  })
  it('returns -1 when no series renders at the column', () => {
    expect(nearestSeriesAt([[null], [null]], 0, 10, yOf)).toBe(-1)
  })
})

describe('axisTickIndices', () => {
  it('spreads count ticks across both ends', () => {
    expect(axisTickIndices(101, 5)).toEqual([0, 25, 50, 75, 100])
  })
  it('degrades gracefully for tiny n', () => {
    expect(axisTickIndices(0)).toEqual([])
    expect(axisTickIndices(1)).toEqual([0])
    expect(axisTickIndices(2, 5)).toEqual([0, 1]) // capped at n, deduped
  })
})

describe('tickDate', () => {
  it('compacts ISO to MM/DD', () => {
    expect(tickDate('2026-06-13')).toBe('06/13')
  })
  it('passes through non-ISO defensively', () => {
    expect(tickDate(null)).toBe('')
    expect(tickDate('2026')).toBe('2026')
  })
})
