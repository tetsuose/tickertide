import type { BoardData, OceanData, RotationData, ManifestData } from '../types'

// Load the nightly Discovery snapshot (export/board.py -> public/data/board.json).
// import.meta.env.BASE_URL respects Vite's base './', so the fetch works from any
// deploy subpath; the optional `?.` keeps it safe under non-Vite runtimes (tests).
export async function loadBoard(signal?: AbortSignal): Promise<BoardData> {
  const base = import.meta.env?.BASE_URL ?? './'
  const res = await fetch(`${base}data/board.json`, { signal })
  if (!res.ok) throw new Error(`board.json HTTP ${res.status}`)
  return (await res.json()) as BoardData
}

// Load the nightly Ocean weekly snapshots (export/ocean.py -> public/data/ocean.json).
export async function loadOcean(signal?: AbortSignal): Promise<OceanData> {
  const base = import.meta.env?.BASE_URL ?? './'
  const res = await fetch(`${base}data/ocean.json`, { signal })
  if (!res.ok) throw new Error(`ocean.json HTTP ${res.status}`)
  return (await res.json()) as OceanData
}

// Load a nightly Rotation snapshot (export/rotation.py). Two files: sector ->
// rotation.json, theme -> rotation.theme.json (separate weeks axes — the theme index
// starts at its first as_of, M4.4). The web loads the one matching its GICS↔Theme toggle.
export async function loadRotation(
  signal?: AbortSignal,
  bucketType: 'sector' | 'theme' = 'sector',
): Promise<RotationData> {
  const base = import.meta.env?.BASE_URL ?? './'
  const file = bucketType === 'theme' ? 'rotation.theme.json' : 'rotation.json'
  const res = await fetch(`${base}data/${file}`, { signal })
  if (!res.ok) throw new Error(`${file} HTTP ${res.status}`)
  return (await res.json()) as RotationData
}

// Load the nightly freshness manifest (export/manifest.py -> public/data/manifest.json).
export async function loadManifest(signal?: AbortSignal): Promise<ManifestData> {
  const base = import.meta.env?.BASE_URL ?? './'
  const res = await fetch(`${base}data/manifest.json`, { signal })
  if (!res.ok) throw new Error(`manifest.json HTTP ${res.status}`)
  return (await res.json()) as ManifestData
}
