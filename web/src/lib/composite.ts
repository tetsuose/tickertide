import type { Components } from '../types'

// C9 — frontend composite recompute. These coefficients are a VERBATIM port of
// compute/signals.py `weights()` (PRD §10.6). The client re-weights the exported
// components c_* by the early⟷reliable knob k and NEVER recomputes the engine.
// Parity is locked by composite.test.ts: recompute at the snapshot k reproduces
// board.json's exported composite (the engine used this same curve).
//
// curve (k clamped to [0,1]); the slopes (+.03 −.24 −.10 −.04 +.35) sum to 0, so
// Σ weights = 1 for every k — no renormalization:
//   rs    = 0.20 + 0.03·k
//   high  = 0.34 − 0.24·k
//   trend = 0.22 − 0.10·k
//   vol   = 0.14 − 0.04·k
//   accel = 0.10 + 0.35·k
export function weights(k: number): Components {
  const kk = Math.max(0, Math.min(1, k))
  return {
    rs: 0.2 + 0.03 * kk,
    high: 0.34 - 0.24 * kk,
    trend: 0.22 - 0.1 * kk,
    vol: 0.14 - 0.04 * kk,
    accel: 0.1 + 0.35 * kk,
  }
}

// composite = 100 · Σ wᵢ·cᵢ (PRD §10.6, compute/run.py). c_* are the engine's
// clamped [0,1] components carried in board.json; this never re-derives them.
export function composite(c: Components, k: number): number {
  const w = weights(k)
  return 100 * (w.rs * c.rs + w.high * c.high + w.trend * c.trend + w.vol * c.vol + w.accel * c.accel)
}
