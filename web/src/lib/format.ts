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

/** ISO date -> MM-DD (point-in-time evidence labels), em-dash for null. */
export function fmtMonthDay(d: string | null | undefined): string {
  return d == null ? '—' : d.slice(5)
}
