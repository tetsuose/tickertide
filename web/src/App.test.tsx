import { describe, it, expect } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import App from './App'

// The early⟷reliable knob is gone (PRD §9.0/§16): steady-riser is the project's core
// screen and has no tunable parameter, so the global top-bar slider + the 5 weight bars +
// RELIABLE/EARLY labels were removed. composite/ignition/base→breakout are not user-visible
// concepts — the engine note reads steady-riser + evidence-first (2026-07-02 spine pivot II).
// renderToStaticMarkup runs no effects, so the surfaces render their loading
// placeholders — enough to assert the top-bar chrome.
describe('App top bar: early⟷reliable knob removed (PRD §16)', () => {
  const html = renderToStaticMarkup(<App />)

  it('renders no range slider (the knob input is gone)', () => {
    expect(html).not.toContain('type="range"')
    expect(html).not.toContain('class="knob"')
    expect(html).not.toContain('early to reliable knob')
  })

  it('renders no RELIABLE/EARLY labels and no weight bars', () => {
    expect(html).not.toContain('RELIABLE')
    expect(html).not.toContain('EARLY')
    expect(html).not.toContain('wbars')
    expect(html).not.toContain('wbfill')
  })

  it('shows the STEADY-RISER engine note in its place (core screen, no tunable parameter)', () => {
    expect(html).toContain('enginenote')
    expect(html).toContain('STEADY-RISER')
    expect(html).toContain('无可调参')
    expect(html).not.toContain('BASE→BREAKOUT')   // retired engine note removed
  })

  it('still renders the 5-lens tab bar and the default Risers surface', () => {
    for (const label of ['Ocean', 'Risers', 'Rotation', 'Valuation', 'Stock'])
      expect(html).toContain(label)
    expect(html).not.toContain('Breakouts')       // renamed tab (2026-07-02 pivot II)
  })
})
