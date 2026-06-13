import { describe, it, expect } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import App from './App'

// The early⟷reliable knob is gone (PRD §9.0/§16): ignition is the project's core
// discovery engine and has no tunable parameter, so the global top-bar slider + the 5
// weight bars + RELIABLE/EARLY labels were removed. composite stays as a fixed-weight
// confirmation side-read. renderToStaticMarkup runs no effects, so the surfaces render
// their loading placeholders — enough to assert the top-bar chrome.
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

  it('shows the IGNITION engine note in its place (core engine, no tunable parameter)', () => {
    expect(html).toContain('enginenote')
    expect(html).toContain('IGNITION')
    expect(html).toContain('无可调参')
  })

  it('still renders the 5-lens tab bar and the default Discovery surface', () => {
    for (const label of ['Ocean', 'Discovery', 'Rotation', 'Valuation', 'Stock'])
      expect(html).toContain(label)
  })
})
