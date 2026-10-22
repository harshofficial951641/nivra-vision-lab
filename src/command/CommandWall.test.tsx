import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import CommandWall from './CommandWall'
import type { CommandData } from './useCommand'
import type { Incident } from '../classroom/contracts'
import type { WallCamera } from './model'

const { state, ping, apiMock } = vi.hoisted(() => ({ apiMock:vi.fn(), state:{data:null as unknown as CommandData,session:null as null | {me:{role:string}}}, ping:{prime:vi.fn(),play:vi.fn(),stop:vi.fn(),dispose:vi.fn()} }))
vi.mock('./useCommand',()=>({useCommand:()=>state.data}))
vi.mock('../auth/context',()=>({useOptionalSession:()=>state.session}))
vi.mock('../classroom/contracts',async original=>({...await original<typeof import('../classroom/contracts')>(),api:apiMock}))
vi.mock('./AlertPing',()=>({AlertPing:class {prime=ping.prime;play=ping.play;stop=ping.stop;dispose=ping.dispose}}))
vi.mock('./ReviewWindow',()=>({ReviewWindow:({event,close}:{event:Incident;close:()=>void})=><div role="dialog" aria-label={`Review ${event.id}`}><button onClick={close}>Close review</button></div>}))
vi.mock('../location/GoogleMap',()=>({GoogleMap:()=>null}))
vi.mock('./ResponseClock',()=>({ResponseClock:()=>null}))
const cameras:WallCamera[]=['Entrance','Hall'].map((name,index)=>({id:`c${index+1}`,label:`CAM-${index+1}`,name,floorId:null,slot:null,status:'offline',sample:false,image:null,people:null,fps:null}))
const alert=(id='e1',camera_id='c2'):Incident=>({id,camera_id,camera_name:'Hall',location:'',received_at:Date.now(),source_ms:1000,evidence_ms:1000,model:'test',detail:'Observed motion',status:'open',revision:0,updated_at:Date.now()})
const cameraButtons=()=>within(screen.getByRole('main')).getAllByRole('button').filter(button=>button.classList.contains('cm-tile'))
const originalShow = Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, 'showModal')
const originalClose = Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, 'close')
beforeAll(()=>{
  Object.defineProperty(HTMLDialogElement.prototype,'showModal',{configurable:true,value(){this.open=true}})
  Object.defineProperty(HTMLDialogElement.prototype,'close',{configurable:true,value(){this.open=false}})
})
afterAll(()=>{
  if(originalShow) Object.defineProperty(HTMLDialogElement.prototype,'showModal',originalShow);else Reflect.deleteProperty(HTMLDialogElement.prototype,'showModal')
  if(originalClose) Object.defineProperty(HTMLDialogElement.prototype,'close',originalClose);else Reflect.deleteProperty(HTMLDialogElement.prototype,'close')
})
beforeEach(()=>{
  history.replaceState(null,'','/wall');localStorage.clear();vi.clearAllMocks();ping.prime.mockResolvedValue(true);state.session=null;apiMock.mockReset().mockResolvedValue(null);vi.spyOn(window,'confirm').mockReturnValue(true)
  state.data={sample:false,connection:'connected',error:'',service:'ready',runtime:null,siteName:'Workshop',floors:[],cameras,guards:[],events:[],clips:null,review:vi.fn(),runSample:vi.fn(),resetSample:vi.fn()}
})
afterEach(()=>{cleanup();vi.restoreAllMocks()})

describe('calm wall alerts',()=>{
  it('shows the latest police contact on the wall camera incident status', () => {
    state.data = { ...state.data, events: [{ ...alert(), police: { at: new Date(2026, 9, 23, 14, 32).getTime(), by: 'guard:G2', method: 'call', count: 1 } }] }
    render(<CommandWall />)
    expect(screen.getByText('Police contacted (call) by G2 at 14:32')).toBeVisible()
  })
  it('does not label a new incident with police contact from an older closed incident', () => {
    state.data = { ...state.data, events: [alert(), { ...alert('old'), status: 'resolved', police: { at: Date.now(), by: 'guard:G2', method: 'call', count: 1 } }] }
    render(<CommandWall />)
    expect(screen.queryByText(/Police contacted/)).not.toBeInTheDocument()
  })
  it('keeps arriving alerts on their camera without moving tiles, opening review, or taking focus',()=>{
    const view=render(<CommandWall />)
    const first=cameraButtons()[0]
    first.focus()
    state.data={...state.data,cameras:[{...cameras[0],people:1},{...cameras[1],people:32}],events:[alert()]}
    view.rerender(<CommandWall />)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(document.activeElement).toBe(first)
    expect(cameraButtons().map(button=>button.textContent?.includes('Entrance'))).toEqual([true,false])
    expect(cameraButtons()[1]).toHaveAttribute('data-alert','review')
    expect(screen.getByRole('button',{name:'1 open alert'})).toBeVisible()
    expect(ping.play).not.toHaveBeenCalled()
    fireEvent.click(cameraButtons()[1])
    expect(screen.getByRole('dialog',{name:'Review e1'})).toBeVisible()
    fireEvent.click(screen.getByRole('button',{name:'Close review'}))
    view.rerender(<CommandWall />)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('opens normal footage only on click and leaves it open when another camera flags',()=>{
    const view=render(<CommandWall />)
    fireEvent.click(cameraButtons()[0])
    expect(screen.getByRole('dialog',{name:'Entrance'})).toBeVisible()
    state.data={...state.data,events:[alert()]};view.rerender(<CommandWall />)
    expect(screen.getByRole('dialog',{name:'Entrance'})).toBeVisible()
    expect(screen.queryByRole('dialog',{name:'Review e1'})).not.toBeInTheDocument()
  })

  it('leaves an initial pending alert closed until its count is clicked',()=>{
    state.data={...state.data,events:[alert()]}
    render(<CommandWall />)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button',{name:'1 open alert'}))
    expect(screen.getByRole('dialog',{name:'Review e1'})).toBeVisible()
  })

  it('rings once per new alert after explicit sound unlock and never replays IDs on reconnect',async()=>{
    const view=render(<CommandWall />)
    fireEvent.click(screen.getByText('More',{selector:'summary'}))
    await act(async()=>fireEvent.click(screen.getByRole('button',{name:'Turn on incident sound'})))
    expect(ping.prime).toHaveBeenCalledOnce()
    expect(ping.play).not.toHaveBeenCalled()
    state.data={...state.data,events:[alert()]};view.rerender(<CommandWall />)
    expect(ping.play).toHaveBeenCalledTimes(1)
    state.data={...state.data,events:[{...alert(),revision:1}]};view.rerender(<CommandWall />)
    state.data={...state.data,events:[]};view.rerender(<CommandWall />)
    state.data={...state.data,events:[alert(),alert('e2')]};view.rerender(<CommandWall />)
    expect(ping.play).toHaveBeenCalledTimes(2)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    fireEvent.click(screen.getByText('More',{selector:'summary'}))
    fireEvent.click(screen.getByRole('button',{name:'Mute incident sound'}))
    state.data={...state.data,events:[alert(),alert('e2'),alert('e3')]};view.rerender(<CommandWall />)
    expect(ping.play).toHaveBeenCalledTimes(2)
    expect(ping.stop).toHaveBeenCalledOnce()
    view.unmount();expect(ping.dispose).toHaveBeenCalledOnce()
  })
})

describe('truthful camera availability',()=>{
  it('shows saved unpaired records as setup entries rather than phantom offline video feeds',()=>{
    state.data={...state.data,cameras:cameras.map(camera=>({...camera,paired:false}))}
    render(<CommandWall />)
    expect(screen.getByRole('status')).toHaveTextContent('0 live cameras')
    expect(screen.getByRole('button',{name:'Cameras 0 live'})).toBeVisible()
    expect(screen.getByRole('heading',{name:'No cameras connected'})).toBeVisible()
    expect(screen.getByRole('link',{name:'Add camera'})).toHaveAttribute('href','/setup#cameras')
    expect(within(screen.getByRole('main')).queryAllByRole('button').filter(button=>button.classList.contains('cm-tile'))).toHaveLength(0)
    expect(screen.getByText('2 saved cameras are waiting for a phone')).toBeVisible()
    fireEvent.click(screen.getByText('2 saved cameras are waiting for a phone'))
    expect(screen.getAllByRole('link',{name:'Connect phone'})).toHaveLength(2)
    expect(screen.getByRole('link',{name:'Manage saved cameras'})).toHaveAttribute('href','/setup#cameras')
    expect(state.data.review).not.toHaveBeenCalled()
  })

  it('keeps genuinely linked offline cameras visible and counts only live feeds',()=>{
    state.data={...state.data,cameras:[{...cameras[0],paired:true,status:'offline'},{...cameras[1],paired:true,status:'live',image:'blob:live'}]}
    render(<CommandWall />)
    expect(screen.getByRole('status')).toHaveTextContent('1 live camera')
    expect(cameraButtons()).toHaveLength(2)
    expect(within(cameraButtons()[0]).getByText('Camera offline')).toBeVisible()
    expect(screen.queryByRole('heading',{name:'No cameras connected'})).not.toBeInTheDocument()
  })

  it('retains stream history and pending incidents even if pairing is now revoked',()=>{
    state.data={...state.data,cameras:[{...cameras[0],paired:false,generation:'previous-stream'},{...cameras[1],paired:false}],events:[alert()]}
    render(<CommandWall />)
    expect(cameraButtons()).toHaveLength(2)
    expect(screen.getByRole('status')).toHaveTextContent('0 live cameras')
    expect(cameraButtons()[1]).toHaveAttribute('data-alert','review')
  })
})


describe('direct owner camera removal',()=>{
  beforeEach(()=>{state.session={me:{role:'admin'}}})
  it('removes paired offline cameras through a sibling control, without opening footage and despite stale snapshots',async()=>{
    state.data={...state.data,cameras:cameras.map(camera=>({...camera,paired:true}))}
    const view=render(<CommandWall />)
    const remove=screen.getByRole('button',{name:'Remove Entrance'})
    expect(remove.closest('button.cm-tile')).toBeNull()
    await act(async()=>fireEvent.click(remove))
    expect(apiMock).toHaveBeenCalledExactlyOnceWith('/cameras/c1','DELETE')
    expect(window.confirm).toHaveBeenCalledWith(expect.stringContaining('Previous alerts stay in history'))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(cameraButtons()).toHaveLength(1)
    view.rerender(<CommandWall />)
    expect(cameraButtons()).toHaveLength(1)
    expect(screen.queryByRole('button',{name:'Remove Entrance'})).not.toBeInTheDocument()
  })
  it('leaves a cancelled removal intact',()=>{
    vi.mocked(window.confirm).mockReturnValue(false)
    render(<CommandWall />)
    fireEvent.click(screen.getByRole('button',{name:'Remove Entrance'}))
    expect(apiMock).not.toHaveBeenCalled()
    expect(cameraButtons()).toHaveLength(2)
  })
  it('prevents duplicate deletes while pending and exposes a retry after failure',async()=>{
    let reject!:(error:Error)=>void
    apiMock.mockImplementationOnce(()=>new Promise((_,fail)=>{reject=fail}))
    render(<CommandWall />)
    const remove=screen.getByRole('button',{name:'Remove Entrance'})
    fireEvent.click(remove);fireEvent.click(remove)
    expect(remove).toBeDisabled()
    expect(apiMock).toHaveBeenCalledOnce()
    await act(async()=>reject(new Error('Connection lost')))
    expect(screen.getByRole('alert')).toHaveTextContent('Could not remove Entrance. Connection lost')
    expect(cameraButtons()).toHaveLength(2)
    await act(async()=>fireEvent.click(screen.getByRole('button',{name:'Retry removal'})))
    expect(apiMock).toHaveBeenCalledTimes(2)
    expect(window.confirm).toHaveBeenCalledOnce()
    expect(cameraButtons()).toHaveLength(1)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
  it('removes a saved unpaired entry from its disclosed row',async()=>{
    state.data={...state.data,cameras:[{...cameras[0],paired:false}]}
    render(<CommandWall />)
    fireEvent.click(screen.getByText('1 saved camera is waiting for a phone'))
    await act(async()=>fireEvent.click(screen.getByRole('button',{name:'Remove Entrance'})))
    expect(apiMock).toHaveBeenCalledExactlyOnceWith('/cameras/c1','DELETE')
    expect(screen.queryByText('1 saved camera is waiting for a phone')).not.toBeInTheDocument()
    expect(screen.getByRole('heading',{name:'No cameras connected'})).toBeVisible()
  })
  it.each(['reviewer','sample'])('does not expose deletion to %s mode',mode=>{
    if(mode==='reviewer')state.session={me:{role:'reviewer'}}
    else history.replaceState(null,'','/wall?demo=1')
    render(<CommandWall />)
    expect(screen.queryByRole('button',{name:/^Remove /})).not.toBeInTheDocument()
    expect(apiMock).not.toHaveBeenCalled()
  })
})
