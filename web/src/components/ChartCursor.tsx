// Shared SVG readout chip for the hover time-cursor (Discovery MiniChart / Rotation /
// Stock stack). It sits to the right of the cursor, flipping to the left near the right
// edge so it never clips. Rendered only when a chart has a live hoverIndex, so it never
// appears under SSR (renderToStaticMarkup) — the existing markup assertions are untouched.

const CHAR_W = 5.4 // IBM Plex Mono advance ≈ 0.6em at 9px
const PAD = 4
const BOX_H = 13

/** A value readout near (x, y); `viewW` is the svg viewBox width used to decide the flip. */
export default function CursorReadout({
  x, y, text, viewW, color = 'var(--txt)',
}: {
  x: number
  y: number
  text: string
  viewW: number
  color?: string
}) {
  const w = text.length * CHAR_W + PAD * 2
  const flip = x + w + 3 > viewW
  const bx = flip ? x - w - 3 : x + 3
  return (
    <g className="chcur">
      <rect className="chcur-bg" x={bx} y={y} width={w} height={BOX_H} rx={3} />
      <text className="chcur-txt" x={bx + PAD} y={y + 9.5} style={{ fill: color }}>
        {text}
      </text>
    </g>
  )
}
