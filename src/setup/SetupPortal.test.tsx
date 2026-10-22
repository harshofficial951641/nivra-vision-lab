import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import SetupPortal from './SetupPortal'
import type { CameraLocation, Snapshot } from '../classroom/contracts'
import type { GuardRecord } from '../command/types'

const { api, liveState, session } = vi.hoisted(() => ({
  api: vi.fn(),
  liveState: { snapshot: null as Snapshot | null, connection: 'connected', error: '', previews: {}, analysisPreviews: {}, apiAvailable: true },
  session: { mode: 'dev', me: { name: 'Owner', role: 'admin', workspace: { ownerVerification: 'unverified' } }, signOut: vi.fn() },
}))
vi.mock('../classroom/contracts', async importOriginal => ({ ...await importOriginal<typeof import('../classroom/contracts')>(), api }))
vi.mock('../classroom/useClassroom', () => ({ useClassroom: () => liveState }))
vi.mock('../auth/context', () => ({ useSession: () => session }))
const camera: CameraLocation = {
  id: 'c1', name: 'Main entrance', building: 'Workshop', floor: 'Ground', enabled: true,
  feed: 'waiting', analysis: 'waiting', generation: null, framesReceived: 0, framesAnalyzed: 0, framesReplaced: 0,
  gps: { latitude: 28.6, longitude: 77.2, accuracy: 10, capturedAt: 1000 },
}
const guard: GuardRecord = { id: 'g1', callsign: 'G1', name: 'Asha', floorName: 'Floor 2', userId: null, email: null, floorId: null, post: null, shift: 'off', presence: { online: false, lastSeen: null }, push: false }
const snapshot = (): Snapshot => ({ version: 3, type: 'snapshot', cameras: [camera], events: [], guards: [guard], floors: [], site: { id: 's', name: 'Workshop' }, analytics: { total: 0, pending: 0, resolved: 0 }, service: 'ready', publicOrigin: 'https://nivra.tanishq.work', retention: 'event-records-only', experimental: true, runtime: null })
const pairing = { url: 'https://nivra.tanishq.work/camera#pair=abcdefghijklmnopqrstuv0123456789', expiresInSeconds: 300, remoteReady: true }
const fill = (name: string, value: string) => fireEvent.change(screen.getByRole('textbox', { name }), { target: { value } })
const row = () => screen.getByRole('heading', { name: camera.name }).closest('article')!
const openDetails = () => {
  const summary = within(row()).getByText('Details', { selector: 'summary' })
  fireEvent.click(summary)
  expect(summary.closest('details')).toHaveAttribute('open')
}

beforeEach(() => {
  history.replaceState(null, '', '/setup#cameras')
  liveState.snapshot = snapshot()
  api.mockImplementation(async (path: string) => path === '/members' ? [] : path.endsWith('/pair') ? pairing : {})
  vi.spyOn(window, 'scrollTo').mockImplementation(() => {})
})
afterEach(() => { cleanup(); vi.resetAllMocks(); vi.restoreAllMocks(); history.replaceState(null, '', '/') })

describe('simple device management', () => {
  it('uses the same camera list for legacy onboarding links and skips naming an already-named site', () => {
    history.replaceState(null, '', '/setup?onboarding=1')
    render(<SetupPortal />)
    expect(screen.getByRole('heading', { level: 1, name: 'Cameras' })).toBeVisible()
    expect(screen.getByRole('navigation', { name: 'Setup steps' })).toBeVisible()
    expect(screen.queryByRole('navigation', { name: 'First-run setup' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Guided setup' })).not.toBeInTheDocument()
    expect(api).not.toHaveBeenCalled()
  })

  it('respects an explicit site hash while keeping only one setup system', () => {
    history.replaceState(null, '', '/setup?onboarding=1#site')
    render(<SetupPortal />)
    expect(screen.getByRole('heading', { level: 1, name: 'Site' })).toBeVisible()
    expect(api).not.toHaveBeenCalled()
  })

  it('opens cameras when a named site finishes loading without another setup entrypoint', () => {
    history.replaceState(null, '', '/setup?onboarding=1')
    liveState.snapshot=null
    const view=render(<SetupPortal />)
    liveState.snapshot=snapshot()
    view.rerender(<SetupPortal />)
    expect(screen.getByRole('heading',{level:1,name:'Cameras'})).toBeVisible()
    expect(api).not.toHaveBeenCalled()
  })
  it('opens existing cameras without loading a map, editing inline, or making API calls', () => {
    const view = render(<SetupPortal />)
    expect(screen.getByRole('heading', { level: 1, name: 'Cameras' })).toBeVisible()
    expect(screen.getByRole('heading', { name: camera.name })).toBeVisible()
    expect(within(row()).getByRole('button', { name: /Connect phone/i })).toBeEnabled()
    expect(view.container.querySelector('iframe')).toBeNull()
    for (const input of row().querySelectorAll('input')) expect(input.closest('details:not([open])')).not.toBeNull()
    expect(api).not.toHaveBeenCalled()
  })

  it('keeps editing and pausing behind Details and loads Google Maps only when asked', async () => {
    const view = render(<SetupPortal />)
    openDetails()
    const record = within(row())
    expect(record.getByRole('textbox', { name: 'Camera name' })).toHaveValue(camera.name)
    expect(view.container.querySelector('iframe')).toBeNull()
    await act(async () => fireEvent.click(record.getByRole('button', { name: /View location/i })))
    expect(screen.getByTitle(`Google Maps · ${camera.name}`)).toBeInTheDocument()
    fireEvent.change(record.getByRole('textbox', { name: 'Camera name' }), { target: { value: 'Front door' } })
    await act(async () => fireEvent.click(record.getByRole('button', { name: /Save camera details/i })))
    expect(api).toHaveBeenCalledWith('/cameras/c1', 'PATCH', { name: 'Front door', building: 'Workshop', floor: 'Ground' })
    await act(async () => fireEvent.click(record.getByRole('button', { name: /^Pause(?: camera)?$/i })))
    expect(api).toHaveBeenCalledWith('/cameras/c1', 'PATCH', { enabled: false })
  })

  it('creates a scoped pairing code only after Connect phone is pressed', async () => {
    render(<SetupPortal />)
    expect(api).not.toHaveBeenCalled()
    await act(async () => fireEvent.click(within(row()).getByRole('button', { name: /Connect phone/i })))
    expect(api).toHaveBeenCalledExactlyOnceWith('/cameras/c1/pair', 'POST')
    expect(screen.getByTitle(`Pairing code for ${camera.name}`)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Done, watch cameras' })).toHaveAttribute('href', '/wall')
  })

  it('offers removal on the row and keeps cancellation free of side effects', () => {
    const confirm=vi.spyOn(window,'confirm').mockReturnValue(false)
    render(<SetupPortal />)
    const remove=within(row()).getByRole('button',{name:'Remove Main entrance'})
    expect(remove).toBeVisible()
    fireEvent.click(remove)
    expect(confirm).toHaveBeenCalledWith('Remove Main entrance? Its phone will disconnect.')
    expect(api).not.toHaveBeenCalled()
    expect(screen.getByRole('heading',{name:camera.name})).toBeVisible()
  })

  it('removes only the confirmed camera and immediately hides it while the snapshot catches up', async () => {
    vi.spyOn(window,'confirm').mockReturnValue(true)
    liveState.snapshot={...snapshot(),cameras:[camera,{...camera,id:'c2',name:'Back door'}]}
    render(<SetupPortal />)
    await act(async()=>fireEvent.click(within(row()).getByRole('button',{name:'Remove Main entrance'})))
    expect(api).toHaveBeenCalledExactlyOnceWith('/cameras/c1','DELETE')
    expect(screen.queryByRole('heading',{name:camera.name})).not.toBeInTheDocument()
    expect(screen.getByRole('heading',{name:'Back door'})).toBeVisible()
    expect(screen.getByRole('button',{name:'Add camera'})).toBeVisible()
  })

  it('keeps the row and offers a retry when removal fails', async () => {
    vi.spyOn(window,'confirm').mockReturnValue(true)
    api.mockRejectedValueOnce(new Error('Could not remove camera'))
    render(<SetupPortal />)
    await act(async()=>fireEvent.click(within(row()).getByRole('button',{name:'Remove Main entrance'})))
    expect(screen.getByRole('alert')).toHaveTextContent('Could not remove camera')
    expect(within(row()).getByRole('button',{name:'Remove Main entrance'})).toBeEnabled()
    expect(api).toHaveBeenCalledExactlyOnceWith('/cameras/c1','DELETE')
  })

  it('prevents repeated deletion while the first removal is pending', async () => {
    const confirm=vi.spyOn(window,'confirm').mockReturnValue(true)
    let finish!:()=>void
    api.mockImplementation(()=>new Promise(resolve=>{finish=()=>resolve({})}))
    render(<SetupPortal />)
    const remove=within(row()).getByRole('button',{name:'Remove Main entrance'})
    await act(async()=>fireEvent.click(remove))
    expect(remove).toBeDisabled()
    fireEvent.click(remove)
    expect(confirm).toHaveBeenCalledTimes(1)
    expect(api).toHaveBeenCalledTimes(1)
    await act(async()=>finish())
    expect(screen.queryByRole('heading',{name:camera.name})).not.toBeInTheDocument()
  })

  it('closes pairing if its camera is removed or revoked in a newer snapshot', async () => {
    const view=render(<SetupPortal />)
    await act(async()=>fireEvent.click(within(row()).getByRole('button',{name:'Connect phone'})))
    expect(screen.getByTitle(`Pairing code for ${camera.name}`)).toBeInTheDocument()
    liveState.snapshot={...snapshot(),cameras:[]}
    view.rerender(<SetupPortal />)
    expect(screen.queryByTitle(`Pairing code for ${camera.name}`)).not.toBeInTheDocument()
    expect(screen.getByRole('button',{name:'Add camera'})).toBeVisible()
    expect(api).toHaveBeenCalledExactlyOnceWith('/cameras/c1/pair','POST')
  })

  it('adds an automatically named camera with one click and immediately shows its browser QR', async () => {
    const created = { ...camera, id: 'c2', name: 'Camera 1', floor: 'Not set', gps: null }
    api.mockImplementation(async (path: string) => path === '/cameras' ? created : pairing)
    render(<SetupPortal />)
    for (const input of row().querySelectorAll('input')) expect(input.closest('details:not([open])')).not.toBeNull()
    expect(api).not.toHaveBeenCalled()
    await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Add camera' })))
    expect(api).toHaveBeenCalledWith('/cameras', 'POST', { name: 'Camera 1', building: 'Workshop', floor: 'Not set' })
    expect(api).toHaveBeenCalledWith('/cameras/c2/pair', 'POST')
    expect(screen.getByTitle('Pairing code for Camera 1')).toBeInTheDocument()
    expect(screen.getByText(/It opens NIVRA in your browser/)).toBeVisible()
    expect(screen.queryByRole('heading', { name: camera.name })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Close' }))
    expect(screen.getByRole('heading', { name: 'Camera 1' })).toBeVisible()
    expect(screen.getByRole('heading', { name: camera.name })).toBeVisible()
    expect(api.mock.calls.filter(([path]) => path === '/cameras')).toHaveLength(1)
  })

  it('does not reuse an existing automatic camera name', async () => {
    liveState.snapshot={...snapshot(), cameras:[{...camera,name:'Camera 1'},{...camera,id:'c2',name:'Camera 2'}]}
    api.mockImplementation(async (path:string)=>path === '/cameras' ? {...camera,id:'c3',name:'Camera 3'} : pairing)
    render(<SetupPortal />)
    await act(async()=>fireEvent.click(screen.getByRole('button',{name:'Add camera'})))
    expect(api).toHaveBeenCalledWith('/cameras','POST',{name:'Camera 3',building:'Workshop',floor:'Not set'})
  })

  it('keeps an empty camera list side-effect free and lets a failed Add be retried', async () => {
    liveState.snapshot={...snapshot(), cameras:[]}
    api.mockRejectedValueOnce(new Error('Connection interrupted'))
    render(<SetupPortal />)
    expect(api).not.toHaveBeenCalled()
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
    await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Add camera' })))
    expect(screen.getByRole('alert')).toHaveTextContent('Connection interrupted')
    expect(screen.getByRole('button',{name:'Add camera'})).toBeEnabled()
    expect(api.mock.calls.some(([path]) => path.endsWith('/pair'))).toBe(false)
    api.mockImplementation(async (path: string) => path === '/cameras' ? {...camera,id:'c2',name:'Camera 1'} : pairing)
    await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Add camera' })))
    expect(screen.getByTitle('Pairing code for Camera 1')).toBeInTheDocument()
  })

  it('shows a linked phone separately from live and preserves its session when opened', async () => {
    liveState.snapshot={...snapshot(),cameras:[{...camera,paired:true}]}
    render(<SetupPortal />)
    expect(within(row()).getByText(/Phone linked/)).toBeVisible()
    expect(within(row()).queryByRole('link',{name:'Watch'})).not.toBeInTheDocument()
    await act(async()=>fireEvent.click(within(row()).getByRole('button',{name:'Connect phone'})))
    expect(screen.getByText('Phone linked')).toBeVisible()
    expect(api).not.toHaveBeenCalled()
  })

  it('offers Watch only for a live feed, rather than treating an invitation as connected', () => {
    liveState.snapshot={...snapshot(), cameras:[{...camera,feed:'live',generation:'live-generation'}]}
    render(<SetupPortal />)
    expect(within(row()).getByRole('link',{name:'Watch'})).toHaveAttribute('href','/wall')
    expect(within(row()).getByText(/Live camera/)).toBeVisible()
    expect(within(row()).queryByRole('button',{name:'Connect phone'})).not.toBeInTheDocument()
    expect(api).not.toHaveBeenCalled()
  })
  it('keeps guard editing and team-access tools closed until requested, with no API calls on arrival', async () => {
    history.replaceState(null, '', '/setup#guards')
    render(<SetupPortal />)
    const record = screen.getByRole('heading', { name: guard.name }).closest('article')!
    expect(within(record).getByText('Floor 2 · Phone offline')).toBeVisible()
    for (const input of record.querySelectorAll('input')) expect(input.closest('details:not([open])')).not.toBeNull()
    expect(api).not.toHaveBeenCalled()
    fireEvent.click(within(record).getByText('Details', { selector: 'summary' }))
    expect(within(record).getByRole('textbox', { name: 'Guard name' })).toHaveValue('Asha')
    expect(api).not.toHaveBeenCalled()
    await act(async () => fireEvent.click(within(record).getByRole('button', { name: 'Connect phone' })))
    expect(api).toHaveBeenCalledExactlyOnceWith('/guards/G1/pair', 'POST')
    expect(screen.getByTitle('Pairing code for Asha')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: guard.name })).not.toBeInTheDocument()
  })

  it('keeps guard removal visible and hides a confirmed removal while the snapshot catches up', async () => {
    history.replaceState(null, '', '/setup#guards')
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    render(<SetupPortal />)
    const record = screen.getByRole('heading', { name: guard.name }).closest('article')!
    fireEvent.click(within(record).getByText('Details', { selector: 'summary' }))
    fireEvent.change(within(record).getByRole('textbox', { name: 'Guard name' }), { target: { value: 'Asha Sharma' } })
    await act(async () => fireEvent.click(within(record).getByRole('button', { name: 'Save guard details' })))
    expect(api).toHaveBeenCalledWith('/guards/g1', 'PATCH', { name: 'Asha Sharma', floorName: 'Floor 2' })
    const remove = within(record).getByRole('button', { name: 'Remove Asha' })
    expect(remove.closest('details')).toBeNull()
    fireEvent.click(remove)
    expect(confirm).toHaveBeenCalledOnce()
    expect(api.mock.calls.some(([, method]) => method === 'DELETE')).toBe(false)
    confirm.mockReturnValueOnce(true)
    await act(async () => fireEvent.click(remove))
    expect(api).toHaveBeenCalledWith('/guards/g1', 'DELETE')
    expect(screen.queryByRole('heading', { name: guard.name })).not.toBeInTheDocument()
  })

  it('adds a guard with only their name, assigns the next reference, and immediately opens their QR', async () => {
    history.replaceState(null, '', '/setup#guards')
    const created = { ...guard, id: 'g2', callsign: 'G2', name: 'Ravi', floorName: null }
    api.mockImplementation(async (path: string) => path === '/guards' ? created : { ...pairing, url: pairing.url.replace('/camera#', '/guard#') })
    render(<SetupPortal />)
    fireEvent.click(screen.getByRole('button', { name: 'Add guard' }))
    expect(screen.getByRole('textbox', { name: 'Guard name' })).toBeRequired()
    const floor = screen.getByLabelText('Floor / area (optional)')
    expect(floor).not.toBeRequired()
    expect(floor.closest('details')).not.toHaveAttribute('open')
    fill('Guard name', 'Ravi')
    await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Show phone QR' })))
    expect(api).toHaveBeenCalledWith('/guards', 'POST', { callsign: 'G2', name: 'Ravi', floorName: null })
    expect(api).toHaveBeenCalledWith('/guards/G2/pair', 'POST')
    expect(screen.getByTitle('Pairing code for Ravi')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Close' }))
    expect(screen.getByRole('heading', { name: 'Ravi' })).toBeVisible()
  })

  it('keeps a guard available for retry if removal fails', async () => {
    history.replaceState(null, '', '/setup#guards')
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    api.mockRejectedValueOnce(new Error('Could not remove guard'))
    render(<SetupPortal />)
    await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Remove Asha' })))
    expect(screen.getByRole('alert')).toHaveTextContent('Could not remove guard')
    expect(screen.getByRole('heading', { name: 'Asha' })).toBeVisible()
    expect(screen.getByRole('button', { name: 'Remove Asha' })).toBeEnabled()
  })

  it('opens guard setup directly without expanding site settings', () => {
    render(<SetupPortal />)
    fireEvent.click(screen.getByRole('button', { name: 'Guards' }))
    expect(screen.getByRole('heading', { level: 1, name: 'Guards' })).toBeVisible()
    expect(screen.getByText('More options', { selector: 'summary' }).closest('details')).not.toHaveAttribute('open')
    expect(api).not.toHaveBeenCalled()
  })

  it('does not create a replacement QR when viewing a connected guard phone', async () => {
    history.replaceState(null, '', '/setup#guards')
    liveState.snapshot={...snapshot(),guards:[{...guard,shift:'on_shift',presence:{online:true,lastSeen:Date.now()}}]}
    render(<SetupPortal />)
    await act(async()=>fireEvent.click(screen.getByRole('button',{name:'View phone'})))
    expect(screen.getByRole('heading',{name:'Phone connected'})).toBeVisible()
    expect(screen.getByText('Asha is on shift and ready for alerts.')).toBeVisible()
    expect(api).not.toHaveBeenCalled()
    expect(screen.queryByTitle('Pairing code for Asha')).not.toBeInTheDocument()
  })

  it('distinguishes connecting a guard phone from starting its shift', async () => {
    history.replaceState(null, '', '/setup#guards')
    const view=render(<SetupPortal />)
    await act(async()=>fireEvent.click(screen.getByRole('button',{name:'Connect phone'})))
    expect(screen.getByTitle('Pairing code for Asha')).toBeInTheDocument()
    liveState.snapshot={...snapshot(),guards:[{...guard,presence:{online:true,lastSeen:Date.now()}}]}
    view.rerender(<SetupPortal />)
    expect(screen.getByRole('heading',{name:'Phone connected'})).toBeVisible()
    expect(screen.getByText('On the guard’s phone, start or resume the shift to receive alerts.')).toBeVisible()
    expect(screen.queryByText('Asha is on shift and ready for alerts.')).not.toBeInTheDocument()
    liveState.snapshot={...snapshot(),guards:[{...guard,shift:'on_shift',presence:{online:true,lastSeen:Date.now()}}]}
    view.rerender(<SetupPortal />)
    expect(screen.getByText('Asha is on shift and ready for alerts.')).toBeVisible()
    expect(api).toHaveBeenCalledExactlyOnceWith('/guards/G1/pair','POST')
  })

})
