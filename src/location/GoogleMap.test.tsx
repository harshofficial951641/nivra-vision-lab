import { afterEach, describe, expect, it } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { GoogleMap } from './GoogleMap'

const point = { latitude: 28.6139, longitude: 77.209, accuracy: 12, capturedAt: 1000 }
afterEach(cleanup)
describe('Google Maps camera location', () => {
  it('keeps external navigation available and allows an embed reload', () => {
    render(<GoogleMap point={point} label="Gate" />)
    const before = screen.getByTitle('Google Maps · Gate')
    expect(screen.getByRole('link', { name: 'Get directions ↗' }).getAttribute('href')).toContain('destination=28.6139%2C77.209')
    fireEvent.click(screen.getByText('About this location'))
    fireEvent.click(screen.getByRole('button', { name: 'Reload map' }))
    expect(screen.getByTitle('Google Maps · Gate')).not.toBe(before)
  })
  it('uses the selected camera destination when cameras change', () => {
    const { rerender } = render(<GoogleMap point={point} label="Gate" />)
    rerender(<GoogleMap point={{ ...point, latitude: 29 }} label="Courtyard" />)
    expect(screen.getByTitle('Google Maps · Courtyard').getAttribute('src')).toContain('29%2C77.209')
  })
  it('never invents a position for unpaired or sample cameras', () => {
    render(<GoogleMap label="Sample gate" sample />)
    expect(screen.getByText('This is a sample location.')).toBeTruthy()
    expect(screen.queryByRole('link', { name: 'Get directions ↗' })).toBeNull()
  })
})
