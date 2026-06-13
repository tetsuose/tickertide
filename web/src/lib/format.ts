// Shared display formatters for the board-driven views (Valuation/Stock, M5 preview).
// Kept pure + DOM-free so they're trivially unit-testable; EvidenceCard (M1) keeps its
// own local copies to avoid churning verified code — unify in a later refactor.

/** $X.XT / $X.XB / $XM market-cap, em-dash for null. */
export function fmtMktcap(v: number | null | undefined): string {
  if (v == null) return '—'
  if (v >= 1e12) return '$' + (v / 1e12).toFixed(1) + 'T'
  if (v >= 1e9) return '$' + (v / 1e9).toFixed(1) + 'B'
  if (v >= 1e6) return '$' + (v / 1e6).toFixed(0) + 'M'
  return '$' + v.toFixed(0)
}

/** Fixed-decimal number, em-dash for null (valuation multiples). */
export function num(v: number | null | undefined, d = 1): string {
  return v == null ? '—' : v.toFixed(d)
}

/** Signed percent from a ratio (0.072 -> +7%), em-dash for null. */
export function pct(v: number | null | undefined, d = 0): string {
  return v == null ? '—' : (v >= 0 ? '+' : '') + (v * 100).toFixed(d) + '%'
}

/** composite score color (PRD 附录C): >=62 hi / >=47 mid / else lo. */
export function scoreColor(score: number | null | undefined): string {
  if (score == null) return 'var(--score-lo)'
  if (score >= 62) return 'var(--score-hi)'
  if (score >= 47) return 'var(--score-mid)'
  return 'var(--score-lo)'
}

// --- ignition 点火证据 formatters (PRD §10.8, M7.3/M7.4) ---
// step-rate ratio = (ret10/10)/(ret50/50): the readable form of ig_accel. It blows up when
// ret50≈0 (M7.2 pitfall: fixture TT20=685) — faithful but useless on screen. Clamp the
// DISPLAY at ±SR_CLAMP (the engine's ranked ig_accel is untouched — display-only) and mark
// clamped values with a leading >/<. Discovery (EvidenceCard) keeps an identical local copy;
// this is the shared home so Stock's 点火诊断 reuses the SAME clamp, not a second one.
export const SR_CLAMP = 20
export function fmtStepRate(v: number | null | undefined): string {
  if (v == null) return '—'
  if (v > SR_CLAMP) return `>${SR_CLAMP}×`
  if (v < -SR_CLAMP) return `<-${SR_CLAMP}×`
  return v.toFixed(1) + '×'
}

/** ISO date -> MM-DD (point-in-time evidence labels), em-dash for null. */
export function fmtMonthDay(d: string | null | undefined): string {
  return d == null ? '—' : d.slice(5)
}
