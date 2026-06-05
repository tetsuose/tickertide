import { describe, it, expect } from 'vitest'
import board from './__fixtures__/board.sample.json'
import { weights, composite } from './composite'
import type { BoardData } from '../types'

const data = board as unknown as BoardData

describe('C9: frontend composite port matches the engine', () => {
  it('reproduces the weight curve (verbatim port of compute/signals.py)', () => {
    for (const k of [0, 0.25, 0.5, 0.75, 1]) {
      const w = weights(k)
      expect(w.rs).toBeCloseTo(0.2 + 0.03 * k, 12)
      expect(w.high).toBeCloseTo(0.34 - 0.24 * k, 12)
      expect(w.trend).toBeCloseTo(0.22 - 0.1 * k, 12)
      expect(w.vol).toBeCloseTo(0.14 - 0.04 * k, 12)
      expect(w.accel).toBeCloseTo(0.1 + 0.35 * k, 12)
    }
  })

  it('weights sum to 1 for every k (slopes cancel)', () => {
    for (const k of [0, 0.1, 0.33, 0.5, 0.8, 1]) {
      const w = weights(k)
      expect(w.rs + w.high + w.trend + w.vol + w.accel).toBeCloseTo(1, 12)
    }
  })

  it('clamps k to [0,1]', () => {
    expect(weights(-1)).toEqual(weights(0))
    expect(weights(2)).toEqual(weights(1))
  })

  // The decisive parity: recompute at the snapshot k must reproduce the engine's
  // exported composite (same curve), within export rounding (components 4dp +
  // composite 2dp -> ~0.01). A coefficient drift here breaks data consistency.
  it('recompute at knob_default_k reproduces exported composite', () => {
    expect(data.stocks.length).toBeGreaterThan(0)
    let maxDrift = 0
    for (const s of data.stocks) {
      if (s.composite == null) continue
      const recon = composite(s.components, data.knob_default_k)
      maxDrift = Math.max(maxDrift, Math.abs(recon - s.composite))
    }
    expect(maxDrift).toBeLessThan(0.02)
  })
})
