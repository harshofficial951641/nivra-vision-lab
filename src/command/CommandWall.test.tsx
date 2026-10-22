import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import CommandWall from './CommandWall'
import type { CommandData } from './useCommand'
import type { Incident } from '../classroom/contracts'
import type { WallCamera } from './model'

const { state, ping } = vi.hoisted(() => ({ state:{data:null as unknown as CommandData}, ping:{prime:vi.fn(),play:vi.fn(),stop:vi.fn(),dispose:vi.fn()} }))
vi.mock('./useCommand',()=>({useCommand:()=>state.data}))
vi.mock('../auth/context',()=>({useOptionalSession:()=>null}))
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
  history.replaceState(null,'','/wall');localStorage.clear();vi.clearAllMocks();ping.prime.mockResolvedValue(true)
  state.data={sample:false,connection:'connected',error:'',service:'ready',runtime:null,siteName:'Workshop',floors:[],cameras,guards:[],events:[],clips:null,review:vi.fn(),runSample:vi.fn(),resetSample:vi.fn()}
})
afterEach(cleanup)

describe('calm wall alerts',()=>{
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
