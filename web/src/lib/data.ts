import type { BoardData } from '../types'

// Load the nightly Discovery snapshot (export/board.py -> public/data/board.json).
// import.meta.env.BASE_URL respects Vite's base './', so the fetch works from any
// deploy subpath; the optional `?.` keeps it safe under non-Vite runtimes (tests).
export async function loadBoard(signal?: AbortSignal): Promise<BoardData> {
  const base = import.meta.env?.BASE_URL ?? './'
  const res = await fetch(`${base}data/board.json`, { signal })
  if (!res.ok) throw new Error(`board.json HTTP ${res.status}`)
  return (await res.json()) as BoardData
}
