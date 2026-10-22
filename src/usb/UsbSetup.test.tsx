import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import UsbSetup from './UsbSetup'
const { scan } = vi.hoisted(() => ({ scan: vi.fn() }))
vi.mock('../pairing/qrScanner', () => ({ startQRScanner: scan }))
const device = { id: 'opaque-phone-id', name: 'Camera phone', connected: true, state: 'waiting', cameraId: null as string | null }
const response = (data: unknown, status = 200) => ({ ok: status >= 200 && status < 300, status, json: async () => data })
const devices = (cameraId: string | null = null) => ({ devices: [{ ...device, cameraId, linked: !!cameraId }], analysis: { status: 'ready' } })
const openHelp = () => {
  const help=screen.getByText('Troubleshooting',{selector:'summary'})
  if (!help.closest('details')?.open) fireEvent.click(help)
}
const openCode = () => { openHelp(); fireEvent.click(screen.getByRole('button',{name:'Use phone code'})) }
const openScanner = async () => {
  const help = screen.getByText('Troubleshooting', { selector: 'summary' })
  if (!help.closest('details')?.open) fireEvent.click(help)
  await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Scan phone QR' })))
}
afterEach(() => { cleanup(); scan.mockReset(); vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers() })
describe('offline Wi-Fi camera setup', () => {
  it('shows Mac-only guidance on a public host without calling any local APIs', () => {
    vi.stubGlobal('location', { hostname: 'nivra.tanishq.work' })
    const fetch = vi.fn(); vi.stubGlobal('fetch', fetch)
    render(<UsbSetup />)
    expect(screen.getByRole('heading', { name: 'Open NIVRA on your Mac.' })).toBeVisible()
    expect(fetch).not.toHaveBeenCalled()
  })
  it('explains the iPhone app steps when no camera is found and separates Mac detection readiness', async () => {
    vi.stubGlobal('fetch', vi.fn(async (url: string) => response(url.endsWith('/config') ? { enabled: true } : { devices: [], analysis: { status: 'ready' } })))
    await act(async () => { render(<UsbSetup />) })
    expect(screen.getByRole('button',{name:'Add camera'})).toBeVisible()
    expect(screen.queryByText(/Your phone will appear here/)).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Scan phone QR' }).closest('details')).not.toHaveAttribute('open')
    expect(screen.getByText('Detection runs on your camera phone')).toBeVisible()
    expect(screen.queryByText(/appear here automatically/i)).not.toBeInTheDocument()
    expect(screen.queryByText('Camera on')).not.toBeInTheDocument()
  })
  it('lists attached phones read-only, then connects only with the phone code and chosen metadata', async () => {
    let attached = false
    const fetch = vi.fn(async (url: string, _init: RequestInit) => {
      if (url.endsWith('/config')) return response({ enabled: true })
      if (url.endsWith('/connect')) { attached = true; return response({}) }
      return response(devices(attached ? 'camera-1' : null))
    })
    vi.stubGlobal('fetch', fetch)
    await act(async () => { render(<UsbSetup />) })
    expect(screen.getByRole('heading', { name: 'Add a camera.' })).toBeVisible()
    expect(screen.getByText(/No internet or cable needed/)).toBeVisible()
    expect(fetch.mock.calls.every(([, init]) => init.method === 'GET')).toBe(true)
    openCode()
    fireEvent.change(screen.getByRole('textbox', { name: 'Phone code' }), { target: { value: 'abcd-2345' } })
    fireEvent.change(screen.getByLabelText('Camera name'), { target: { value: ' Main entrance ' } })
    fireEvent.change(screen.getByLabelText('Floor / area'), { target: { value: ' Ground ' } })
    await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Connect camera' })))
    const write = fetch.mock.calls.find(([url]) => url.endsWith('/connect'))!
    expect(write[1]).toMatchObject({ method: 'POST', credentials: 'same-origin' })
    expect(JSON.parse(String(write[1].body))).toEqual({ deviceId: device.id, code: 'ABCD2345', name: 'Main entrance', floor: 'Ground' })
    expect(screen.getByRole('link', { name: 'Watch cameras' })).toHaveAttribute('href', '/wall')
    expect(screen.queryByRole('textbox', { name: 'Phone code' })).not.toBeInTheDocument()
  })
  it('requires confirmation to remove a camera and refreshes the list after removal', async () => {
    let attached = true
    const fetch = vi.fn(async (url: string, init: RequestInit) => {
      if (url.endsWith('/config')) return response({ enabled: true })
      if (init.method === 'DELETE') { attached = false; return response(null, 204) }
      return response(devices(attached ? 'camera-1' : null))
    })
    vi.stubGlobal('fetch', fetch)
    const confirm = vi.spyOn(window, 'confirm').mockReturnValueOnce(false).mockReturnValueOnce(true)
    await act(async () => { render(<UsbSetup />) })
    fireEvent.click(screen.getByRole('button', { name: 'Remove' }))
    expect(confirm).toHaveBeenCalledOnce()
    expect(fetch.mock.calls.some(([, init]) => init.method === 'DELETE')).toBe(false)
    await act(async () => fireEvent.click(screen.getByRole('button', { name: 'Remove' })))
    expect(fetch.mock.calls.find(([, init]) => init.method === 'DELETE')?.[0]).toBe('/api/local/devices/opaque-phone-id')
    openHelp()
    expect(screen.getByRole('button', { name: 'Use phone code' })).toBeVisible()
  })
  it('refreshes connection state promptly and stops polling after unmount', async () => {
    vi.useFakeTimers()
    const fetch = vi.fn(async (url: string) => response(url.endsWith('/config') ? { enabled: true } : devices()))
    vi.stubGlobal('fetch', fetch)
    const view = render(<UsbSetup />)
    await act(async () => {})
    expect(fetch).toHaveBeenCalledTimes(2)
    await act(async () => { await vi.advanceTimersByTimeAsync(1500) })
    expect(fetch).toHaveBeenCalledTimes(3)
    view.unmount()
    await act(async () => { await vi.advanceTimersByTimeAsync(9000) })
    expect(fetch).toHaveBeenCalledTimes(3)
  })
  it('lets a saved camera reconnect after restart without creating a second camera', async () => {
    const fetch = vi.fn(async (url: string) => response(url.endsWith('/config') ? { enabled: true } : { devices: [{ ...device, cameraId: 'saved-camera', linked: false }], analysis: { status: 'ready' } }))
    vi.stubGlobal('fetch', fetch)
    await act(async () => { render(<UsbSetup />) })
    openHelp()
    expect(screen.getByRole('button', { name: 'Use phone code' })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Remove' })).toBeEnabled()
    expect(screen.queryByRole('link', { name: 'Watch cameras' })).not.toBeInTheDocument()
  })
  it('scans a phone QR only after a click, rejects other QR types, and sends one private connection to the local server', async () => {
    let decoded!: (text: string) => void
    let signal!: AbortSignal
    scan.mockImplementation(async (_video, callback, nextSignal) => { decoded = callback; signal = nextSignal })
    const fetch = vi.fn(async (url: string, _init: RequestInit) => response(url.endsWith('/config') ? { enabled: true } : url.endsWith('/connect') ? {} : devices()))
    vi.stubGlobal('fetch', fetch)
    await act(async () => { render(<UsbSetup />) })
    expect(scan).not.toHaveBeenCalled()
    await openScanner()
    act(() => decoded('https://example.com/camera#pair=anything'))
    expect(screen.getByRole('alert')).toHaveTextContent('Use the QR shown in NIVRA')
    expect(fetch.mock.calls.some(([url]) => url.endsWith('/connect'))).toBe(false)
    await act(async () => { decoded('nivra-local://camera?host=172.20.10.1&hosts=172.20.10.1,192.168.1.2&port=8940#key=ABCD2345') })
    expect(signal.aborted).toBe(true)
    const writes = fetch.mock.calls.filter(([url]) => url.endsWith('/connect'))
    expect(writes).toHaveLength(1)
    expect(writes[0][0]).toBe('/api/local/connect')
    expect(JSON.parse(String(writes[0][1].body))).toEqual({ host: '172.20.10.1', hosts: ['172.20.10.1', '192.168.1.2'], code: 'ABCD2345', name: '', floor: '' })
  })
  it('stops scanner permission work on cancel or unmount, ignores late QR results, and keeps one connection form visible', async () => {
    let decoded!: (text: string) => void
    let signal!: AbortSignal
    scan.mockImplementation(async (_video, callback, nextSignal) => { decoded = callback; signal = nextSignal })
    const fetch = vi.fn(async (url: string, _init: RequestInit) => response(url.endsWith('/config') ? { enabled: true } : devices()))
    vi.stubGlobal('fetch', fetch)
    const view = render(<UsbSetup />)
    await act(async () => {})
    await openScanner()
    expect(screen.queryByRole('button', { name: 'Use phone code' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Cancel scanner' }))
    expect(signal.aborted).toBe(true)
    act(() => decoded('nivra-local://camera?host=172.20.10.1&port=8940#key=ABCD2345'))
    expect(fetch.mock.calls.some(([url]) => url.endsWith('/connect'))).toBe(false)
    openCode()
    expect(screen.getByRole('textbox', { name: 'Phone code' })).toBeVisible()
    expect(screen.queryByRole('button', { name: 'Scan phone QR' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    await openScanner()
    view.unmount()
    expect(signal.aborted).toBe(true)
  })
  it('does not continue startup if the configuration reply arrives after unmount', async () => {
    let finish!: (value: unknown) => void
    let signal!: AbortSignal
    const fetch = vi.fn((_url, init) => { signal = init.signal; return new Promise(resolve => { finish = resolve }) })
    vi.stubGlobal('fetch', fetch)
    const view = render(<UsbSetup />)
    view.unmount()
    expect(signal.aborted).toBe(true)
    await act(async () => finish(response({ enabled: true })))
    expect(fetch).toHaveBeenCalledOnce()
  })
  it('creates a Mac QR only on Add camera, then completes only for a newly linked phone', async () => {
    vi.useFakeTimers()
    let linked=false
    const fetch=vi.fn(async(url:string)=>response(url.endsWith('/config')?{enabled:true}:url.endsWith('/invite')?{url:`nivra://local-camera?host=192.168.1.2&port=8871#pair=${'a'.repeat(43)}`,expiresInSeconds:300}:{devices:[{...device,id:'existing',cameraId:'old',linked:true},...(linked?[{...device,id:'new',cameraId:'new-camera',linked:true,state:'waiting'}]:[])],analysis:{status:'ready'}}))
    vi.stubGlobal('fetch',fetch)
    render(<UsbSetup/>);await act(async()=>{})
    expect(fetch.mock.calls.every(([url])=>!url.endsWith('/invite'))).toBe(true)
    expect(scan).not.toHaveBeenCalled()
    await act(async()=>fireEvent.click(screen.getByRole('button',{name:'Add another camera'})))
    expect(fetch.mock.calls.filter(([url])=>url.endsWith('/invite'))).toHaveLength(1)
    expect(screen.getByTitle('Connect camera QR')).toBeInTheDocument()
    expect(screen.getByText('Tap Scan to connect, then scan this QR.')).toBeVisible()
    expect(screen.queryByText('Phone linked')).not.toBeInTheDocument()
    linked=true
    await act(async()=>{await vi.advanceTimersByTimeAsync(1500)})
    expect(screen.queryByTitle('Connect camera QR')).not.toBeInTheDocument()
    expect(screen.getByRole('heading',{name:'Phone linked'})).toBeVisible()
    expect(screen.queryByRole('heading',{name:'Camera on'})).not.toBeInTheDocument()
    expect(fetch.mock.calls.filter(([url])=>url.endsWith('/invite'))).toHaveLength(1)
    expect(scan).not.toHaveBeenCalled()
  })
  it('expires the invitation without rotating it until New QR is clicked',async()=>{
    vi.useFakeTimers()
    const fetch=vi.fn(async(url:string)=>response(url.endsWith('/config')?{enabled:true}:url.endsWith('/invite')?{url:`nivra://local-camera?host=192.168.1.2&port=8871#pair=${'b'.repeat(43)}`,expiresInSeconds:2}:{devices:[],analysis:{status:'ready'}}))
    vi.stubGlobal('fetch',fetch)
    render(<UsbSetup/>);await act(async()=>{})
    await act(async()=>fireEvent.click(screen.getByRole('button',{name:'Add camera'})))
    await act(async()=>{await vi.advanceTimersByTimeAsync(3000)})
    expect(screen.queryByTitle('Connect camera QR')).not.toBeInTheDocument()
    expect(screen.getByText(/This QR has expired/)).toBeVisible()
    expect(fetch.mock.calls.filter(([url])=>url.endsWith('/invite'))).toHaveLength(1)
    await act(async()=>fireEvent.click(screen.getByRole('button',{name:'New QR'})))
    expect(fetch.mock.calls.filter(([url])=>url.endsWith('/invite'))).toHaveLength(2)
  })
  it('prevents duplicate invite requests, aborts on unmount, and ignores a late response',async()=>{
    let finish!:(value:unknown)=>void
    let signal!:AbortSignal
    const fetch=vi.fn(async(url:string,init:RequestInit)=>{
      if(url.endsWith('/invite')) {signal=init.signal!;return new Promise(resolve=>{finish=resolve})}
      return response(url.endsWith('/config')?{enabled:true}:{devices:[],analysis:{status:'ready'}})
    })
    vi.stubGlobal('fetch',fetch)
    const view=render(<UsbSetup/>);await act(async()=>{})
    const add=screen.getByRole('button',{name:'Add camera'})
    fireEvent.click(add);fireEvent.click(add)
    expect(fetch.mock.calls.filter(([url])=>url.endsWith('/invite'))).toHaveLength(1)
    view.unmount();expect(signal.aborted).toBe(true)
    await act(async()=>finish(response({url:`nivra://local-camera?host=192.168.1.2&port=8871#pair=${'c'.repeat(43)}`,expiresInSeconds:300})))
    expect(screen.queryByTitle('Connect camera QR')).not.toBeInTheDocument()
  })
  it('shows invite errors and permits an explicit retry without claiming a live camera',async()=>{
    let failed=true
    const fetch=vi.fn(async(url:string)=>url.endsWith('/invite')?failed?response({detail:'Connection listener is unavailable'},503):response({url:`nivra://local-camera?host=192.168.1.2&port=8871#pair=${'d'.repeat(43)}`,expiresInSeconds:300}):response(url.endsWith('/config')?{enabled:true}:{devices:[],analysis:{status:'ready'}}))
    vi.stubGlobal('fetch',fetch)
    render(<UsbSetup/>);await act(async()=>{})
    await act(async()=>fireEvent.click(screen.getByRole('button',{name:'Add camera'})))
    expect(screen.getByRole('alert')).toHaveTextContent('Connection listener is unavailable')
    expect(screen.queryByTitle('Connect camera QR')).not.toBeInTheDocument()
    failed=false
    await act(async()=>fireEvent.click(screen.getByRole('button',{name:'Add camera'})))
    expect(screen.getByTitle('Connect camera QR')).toBeInTheDocument()
    expect(screen.queryByText('Camera on')).not.toBeInTheDocument()
  })

  it('bounds a stalled invite request and enables an explicit retry',async()=>{
    vi.useFakeTimers()
    const fetch=vi.fn((url:string,init:RequestInit)=>{
      if(url.endsWith('/invite')) return new Promise((_resolve,reject)=>init.signal!.addEventListener('abort',()=>reject(new DOMException('Aborted','AbortError')),{once:true}))
      return Promise.resolve(response(url.endsWith('/config')?{enabled:true}:{devices:[],analysis:{status:'ready'}}))
    })
    vi.stubGlobal('fetch',fetch)
    render(<UsbSetup/>);await act(async()=>{})
    fireEvent.click(screen.getByRole('button',{name:'Add camera'}))
    await act(async()=>{await vi.advanceTimersByTimeAsync(8001)})
    expect(screen.getByRole('alert')).toHaveTextContent('took too long')
    expect(screen.getByRole('button',{name:'Add camera'})).toBeEnabled()
    expect(fetch.mock.calls.filter(([url])=>url.endsWith('/invite'))).toHaveLength(1)
  })

  it('waits for the initial device list before creating an invite baseline',async()=>{
    let finish!:(value:unknown)=>void
    const fetch=vi.fn((url:string)=>url.endsWith('/config')?Promise.resolve(response({enabled:true})):new Promise(resolve=>{finish=resolve}))
    vi.stubGlobal('fetch',fetch)
    render(<UsbSetup/>);await act(async()=>{})
    expect(screen.getByRole('button',{name:'Add camera'})).toBeDisabled()
    await act(async()=>finish(response({devices:[],analysis:{status:'ready'}})))
    expect(screen.getByRole('button',{name:'Add camera'})).toBeEnabled()
    expect(fetch.mock.calls.some(([url])=>url.endsWith('/invite'))).toBe(false)
  })

})
