import type { BoardData, OceanData, RotationData } from '../types'

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

// Load the nightly Rotation snapshot (export/rotation.py -> public/data/rotation.json).
export async function loadRotation(signal?: AbortSignal): Promise<RotationData> {
  const base = import.meta.env?.BASE_URL ?? './'
  const res = await fetch(`${base}data/rotation.json`, { signal })
  if (!res.ok) throw new Error(`rotation.json HTTP ${res.status}`)
  return (await res.json()) as RotationData
}
