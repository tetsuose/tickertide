import { describe, it, expect } from 'vitest'
import board from './__fixtures__/board.sample.json'
import { WEIGHTS, composite } from './composite'
import type { BoardData } from '../types'

const data = board as unknown as BoardData

describe('C9: frontend composite port matches the engine (fixed weighting, no knob)', () => {
  it('WEIGHTS = the engine snapshot weights (weights(k=0.5), PRD §16)', () => {
    // verbatim weights(0.5) of compute/signals.py — the curve the nightly pipeline
    // exports (compute/run.py --k 0.5 default). The early⟷reliable knob is gone.
    expect(WEIGHTS.rs).toBeCloseTo(0.2 + 0.03 * 0.5, 12)
    expect(WEIGHTS.high).toBeCloseTo(0.34 - 0.24 * 0.5, 12)
    expect(WEIGHTS.trend).toBeCloseTo(0.22 - 0.1 * 0.5, 12)
    expect(WEIGHTS.vol).toBeCloseTo(0.14 - 0.04 * 0.5, 12)
    expect(WEIGHTS.accel).toBeCloseTo(0.1 + 0.35 * 0.5, 12)
  })

  it('WEIGHTS sum to 1', () => {
    expect(WEIGHTS.rs + WEIGHTS.high + WEIGHTS.trend + WEIGHTS.vol + WEIGHTS.accel).toBeCloseTo(1, 12)
  })

  it('matches the engine snapshot weights round(weights(0.5),4) (knob gone, board no longer ships weights_default)', () => {
    // With the early⟷reliable knob removed (PRD §16) the board snapshot is fixed at
    // k=0.5 and no longer exports weights_default; WEIGHTS must equal the engine's
    // round(weights(0.5),4) — the per-component parity the export field used to lock.
    const engineK05 = { rs: 0.215, high: 0.22, trend: 0.17, vol: 0.12, accel: 0.275 }
    for (const key of ['rs', 'high', 'trend', 'vol', 'accel'] as const) {
      expect(WEIGHTS[key]).toBeCloseTo(engineK05[key], 4)
    }
  })

  // The decisive parity: composite() at the fixed weighting must reproduce the engine's
  // exported composite (same curve), within export rounding (components 4dp + composite
  // 2dp -> ~0.01). A coefficient drift here breaks data consistency. (The app reads the
  // engine's exported composite directly; this fallback path must still agree with it.)
  it('composite() reproduces the engine-exported composite', () => {
    expect(data.stocks.length).toBeGreaterThan(0)
    let maxDrift = 0
    for (const s of data.stocks) {
      if (s.composite == null) continue
      const recon = composite(s.components)
      maxDrift = Math.max(maxDrift, Math.abs(recon - s.composite))
    }
    expect(maxDrift).toBeLessThan(0.02)
  })
})
