// Pure data-freshness helpers for the as_of badge (D.4; no DOM, SSR-testable).
// EOD data: as_of is the latest trading day. Age = calendar days from as_of to today;
// thresholds tolerate weekends (a Fri close seen on Mon = 3 days = still fresh).

export type DataFreshness = 'fresh' | 'aging' | 'stale'

const FRESH_MAX = 3 // ≤3 calendar days (covers a weekend + Mon) = fresh
const AGING_MAX = 7 // ≤7 = aging (a warning); >7 = stale

/** Calendar days from as_of (YYYY-MM-DD) to `today`, UTC-normalized so time-of-day / DST
 *  never shift the count. NaN if as_of is unparseable. */
export function dataAgeDays(asOf: string | null | undefined, today: Date): number {
  if (!asOf) return NaN
  const a = Date.parse(asOf + 'T00:00:00Z')
  const t = Date.parse(today.toISOString().slice(0, 10) + 'T00:00:00Z')
  if (isNaN(a) || isNaN(t)) return NaN
  return Math.round((t - a) / 86_400_000)
}

/** fresh ≤3d · aging ≤7d · stale >7d (or unknown/future). */
export function freshness(ageDays: number): DataFreshness {
  if (isNaN(ageDays) || ageDays < 0) return 'stale'
  if (ageDays <= FRESH_MAX) return 'fresh'
  if (ageDays <= AGING_MAX) return 'aging'
  return 'stale'
}

/** Short human label for the badge sub-line. */
export function ageLabel(ageDays: number): string {
  if (isNaN(ageDays)) return '数据未就绪'
  if (ageDays <= 0) return '当日数据'
  const base = `${ageDays} 天前`
  return ageDays > AGING_MAX ? `${base} · 数据陈旧` : base
}
