import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { PoliceContact } from './PoliceContact'

const props = { incidentId: 'e1', cameraName: 'Hall & stairs', location: 'Floor 2, north / east', role: 'reviewer' as const }
const police = { at: new Date(2026, 9, 23, 14, 32).getTime(), by: 'guard:G2', method: 'call' as const, count: 1 }
const fetchMock = vi.fn()
beforeEach(() => {
  vi.stubGlobal('fetch', fetchMock)
  fetchMock.mockResolvedValue({ ok: true, status: 200, json: async () => ({ police }) })
})
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.unstubAllEnvs(); vi.clearAllMocks() })

describe('police contact confirmation', () => {
  it('requires disclosure before showing links, and Cancel restores focus without logging', () => {
    render(<PoliceContact {...props} />)
    expect(screen.getByRole('group', { name: 'Contact police' })).toBeVisible()
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
    const button = screen.getByRole('button', { name: 'Police' })
    expect(button).toHaveAttribute('aria-expanded', 'false')
    fireEvent.click(button)
    expect(button).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByRole('group', { name: 'Confirm police contact' })).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(button).toHaveFocus()
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
    expect(fetchMock).not.toHaveBeenCalled()
  })
  it('uses default hrefs and encodes the full camera/location message', () => {
    render(<PoliceContact {...props} />)
    fireEvent.click(screen.getByRole('button', { name: 'Police' }))
    expect(screen.getByRole('link', { name: 'Call 112' })).toHaveAttribute('href', 'tel:112')
    expect(screen.getByRole('link', { name: 'Text police' })).toHaveAttribute('href', `sms:112?&body=${encodeURIComponent('NIVRA alert: possible physical conflict at Hall & stairs, Floor 2, north / east. Please send police.')}`)
  })
  it.each(['+91112', '*112', '1234'])('uses the configured number %s', number => {
    vi.stubEnv('VITE_NIVRA_POLICE_NUMBER', number)
    render(<PoliceContact {...props} />)
    fireEvent.click(screen.getByRole('button', { name: 'Police' }))
    expect(screen.getByRole('link', { name: `Call ${number}` })).toHaveAttribute('href', `tel:${number}`)
    expect(screen.getByRole('link', { name: 'Text police' }).getAttribute('href')).toMatch(`sms:${number}?&body=`)
  })
  it.each(['', '+', '*', '***', '++123', '12+34', '1234567890123456', '112#', '112;ext=9', ' 112 ', 'javascript:112', '112\n', undefined, null])('falls back for invalid number %s', number => {
    vi.stubEnv('VITE_NIVRA_POLICE_NUMBER', number as string)
    render(<PoliceContact {...props} />)
    fireEvent.click(screen.getByRole('button', { name: 'Police' }))
    expect(screen.getByRole('link', { name: 'Call 112' })).toHaveAttribute('href', 'tel:112')
  })
  it.each(['call', 'text'] as const)('logs %s through the helper with keepalive without preventing navigation', async method => {
    render(<PoliceContact {...props} role="guard" />)
    fireEvent.click(screen.getByRole('button', { name: 'Police' }))
    const link = screen.getByRole('link', { name: method === 'call' ? 'Call 112' : 'Text police' })
    const click = new MouseEvent('click', { bubbles: true, cancelable: true })
    // Only the test suppresses jsdom's unsupported external navigation.
    link.addEventListener('click', event => { expect(event.defaultPrevented).toBe(false); event.preventDefault() })
    fireEvent(link, click)
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('/api/v2/guard/events/e1/police', expect.objectContaining({ method: 'POST', keepalive: true, credentials: 'same-origin', body: JSON.stringify({ method }) })))
    expect(await screen.findByText('Police contacted (call) by G2 at 14:32')).toBeVisible()
  })
  it('shows a quiet failure and can retry using the reviewer endpoint', async () => {
    fetchMock.mockRejectedValueOnce(new Error('offline'))
    render(<PoliceContact {...props} />)
    fireEvent.click(screen.getByRole('button', { name: 'Police' }))
    const call = screen.getByRole('link', { name: 'Call 112' })
    call.addEventListener('click', event => event.preventDefault())
    fireEvent.click(call)
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not record police contact')
    fireEvent.click(call)
    await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument())
    expect(fetchMock).toHaveBeenCalledWith('/api/v2/events/e1/police', expect.objectContaining({ keepalive: true }))
  })
  it('renders later snapshot contacts including reviewer identity', () => {
    const view = render(<PoliceContact {...props} police={police} />)
    expect(screen.getByText('Police contacted (call) by G2 at 14:32')).toBeVisible()
    view.rerender(<PoliceContact {...props} police={{ ...police, method: 'text', by: 'reviewer-7' }} />)
    expect(screen.getByText('Police contacted (text) by reviewer-7 at 14:32')).toBeVisible()
  })
  it('keeps sample incidents from contacting emergency services', () => {
    render(<PoliceContact {...props} sample />)
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
    expect(fetchMock).not.toHaveBeenCalled()
  })
})
