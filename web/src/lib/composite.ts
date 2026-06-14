import type { Components } from '../types'

// Fixed composite weights — the FORMER early⟷reliable knob is gone (the project's
// core is ignition, the discovery engine; composite is the confirmation side-read
// at a single fixed weighting, PRD §9.0/§16). These coefficients are weights(k=0.5)
// of compute/signals.py — the engine snapshot the nightly pipeline exports (compute/
// run.py defaults --k 0.5, export/board.py build_board(k=0.5)). They sum to 1.
//
// The engine already carries the resulting composite per stock (board.json `composite`,
// stock bundle `meta.composite`), so the client no longer re-weights anything; WEIGHTS
// exists only so the expandable badge can show each component's weight % (informed
// consent — composite = Σ wᵢ·cᵢ, no black box) and so `composite()` can fill a value
// when the engine emitted components but no composite. Parity with the engine's
// weights(0.5) is locked by composite.test.ts (the board no longer ships a
// weights_default field — the early⟷reliable knob is gone, PRD §16).
export const WEIGHTS: Components = {
  rs: 0.215,
  high: 0.22,
  trend: 0.17,
  vol: 0.12,
  accel: 0.275,
}

// composite = 100 · Σ wᵢ·cᵢ at the fixed weighting (PRD §10.6, compute/run.py). c_*
// are the engine's clamped [0,1] components carried in board.json; this never
// re-derives them. Prefer the engine's exported composite; use this only as a
// fallback when a surface has components but no precomputed composite.
export function composite(c: Components): number {
  return (
    100 *
    (WEIGHTS.rs * c.rs +
      WEIGHTS.high * c.high +
      WEIGHTS.trend * c.trend +
      WEIGHTS.vol * c.vol +
      WEIGHTS.accel * c.accel)
  )
}
