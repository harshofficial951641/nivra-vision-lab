import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { ReviewWindow } from './ReviewWindow'
import type { Incident } from '../classroom/contracts'
import type { WallGuard } from './types'
vi.mock('./ClipPlayer', () => ({ ClipPlayer: () => <div>Playback</div> }))
vi.mock('../location/GoogleMap', () => ({ GoogleMap: () => <div>Camera location</div> }))
const event: Incident = { id: 'e1', camera_id: 'c1', camera_name: 'Entrance', location: 'Ground floor', received_at: 1000, source_ms: 1000, evidence_ms: 1000, model: 'nivra-browser-motion-v1', detail: 'Observed motion', status: 'open', revision: 0, updated_at: 1000 }
const guards: WallGuard[] = [{ id: 'G1', name: 'Asha', floorId: null, floorName: 'Ground floor', x: null, y: null, status: 'available', online: true, push: true }]
const showModal = Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, 'showModal')
const closeDialog = Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, 'close')
beforeAll(() => {
  Object.defineProperty(HTMLDialogElement.prototype, 'showModal', { configurable: true, value() { this.open = true } })
  Object.defineProperty(HTMLDialogElement.prototype, 'close', { configurable: true, value() { this.open = false } })
})
afterAll(() => {
  if (showModal) Object.defineProperty(HTMLDialogElement.prototype, 'showModal', showModal); else Reflect.deleteProperty(HTMLDialogElement.prototype, 'showModal')
  if (closeDialog) Object.defineProperty(HTMLDialogElement.prototype, 'close', closeDialog); else Reflect.deleteProperty(HTMLDialogElement.prototype, 'close')
})
beforeEach(() => vi.spyOn(document, 'hasFocus').mockReturnValue(false))
afterEach(() => { cleanup(); vi.restoreAllMocks() })
function review() {
  const act = vi.fn().mockResolvedValue(undefined), close = vi.fn()
  render(<ReviewWindow event={event} events={[event]} cameras={[]} now={2000} clips={null} floors={[]} guards={guards} sample={false} queue={1} act={act} close={close} />)
  return { act, close }
}
describe('clear and explicit review decisions', () => {
  it.each([false, true])('renders police contact for undecided and active-response incidents (%s)', active => {
    const incident: Incident = { ...event, ...(active ? { status: 'acknowledged' as const, decision: 'confirmed' as const, guard: 'G1', alerted_at: 1000 } : {}), police: { at: new Date(2026, 9, 23, 14, 32).getTime(), by: 'guard:G2', method: 'text', count: 2 } }
    render(<ReviewWindow event={incident} events={[incident]} cameras={[]} now={2000} clips={null} floors={[]} guards={guards} sample={false} queue={1} act={vi.fn()} close={vi.fn()} />)
    expect(screen.getByRole('group', { name: 'Contact police' })).toBeVisible()
    expect(screen.getByText('Police contacted (text) by G2 at 14:32')).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: 'Police' }))
    expect(screen.getByRole('link', { name: 'Call 112' })).toHaveAttribute('href', 'tel:112')
  })
  it('closes an undecided alert without requiring a false-alarm reason',async()=>{
    const {act,close}=review()
    fireEvent.click(screen.getByRole('button',{name:'Close alert'}))
    await waitFor(()=>expect(close).toHaveBeenCalledOnce())
    expect(act).toHaveBeenCalledExactlyOnceWith('close',{})
    expect(screen.queryByRole('radiogroup',{name:'False alarm reason'})).not.toBeInTheDocument()
  })

  it('keeps a failed closure visible and allows a retry after a revision conflict',async()=>{
    const act=vi.fn().mockRejectedValueOnce(new Error('This alert changed. Try again.')).mockResolvedValueOnce(undefined),close=vi.fn()
    const props={event,events:[event],cameras:[],now:2000,clips:null,floors:[],guards,sample:false,queue:1,act,close}
    const view=render(<ReviewWindow {...props}/>)
    fireEvent.click(screen.getByRole('button',{name:'Close alert'}))
    await waitFor(()=>expect(screen.getByRole('alert')).toHaveTextContent('This alert changed'))
    expect(close).not.toHaveBeenCalled()
    view.rerender(<ReviewWindow {...props} event={{...event,revision:1,status:'acknowledged'}} />)
    fireEvent.click(screen.getByRole('button',{name:'Close alert'}))
    await waitFor(()=>expect(close).toHaveBeenCalledOnce())
    expect(act).toHaveBeenCalledTimes(2)
  })

  it('does not offer undecided closure for a confirmed incident with a dispatched guard',()=>{
    render(<ReviewWindow event={{...event,status:'acknowledged',decision:'confirmed',guard:'G1',alerted_at:1000}} events={[]} cameras={[]} now={2000} clips={null} floors={[]} guards={guards} sample={false} queue={0} act={vi.fn()} close={vi.fn()} />)
    expect(screen.queryByRole('button',{name:'Close alert'})).not.toBeInTheDocument()
    expect(screen.getByRole('button',{name:'Situation clear'})).toBeVisible()
  })

  it('reveals false-alarm reasons without dismissing and still requires a chosen reason to save', async () => {
    const { act, close } = review()
    expect(screen.queryByRole('radiogroup', { name: 'False alarm reason' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'False alarm' }))
    expect(screen.getByRole('radiogroup', { name: 'False alarm reason' })).toBeVisible()
    expect(act).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Save false alarm' }))
    expect(screen.getByRole('alert')).toHaveTextContent('Pick why this is a false alarm first.')
    expect(act).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('radio', { name: /greeting/i }))
    fireEvent.click(screen.getByRole('button', { name: 'Save false alarm' }))
    await waitFor(() => expect(close).toHaveBeenCalledOnce())
    expect(act).toHaveBeenCalledExactlyOnceWith('dismiss', { reason: 'greeting', note: '' })
  })
  it('keeps confirmation without dispatch separate from the explicit send-guard button', async () => {
    const { act } = review()
    fireEvent.click(screen.getByRole('button', { name: 'Confirm only' }))
    await waitFor(() => expect(act).toHaveBeenCalledExactlyOnceWith('confirm', { note: '' }))
  })
  it('dispatches the selected guard only after the confirm-and-send action', async () => {
    const { act } = review()
    fireEvent.click(screen.getByRole('button', { name: 'Confirm & send G1' }))
    await waitFor(() => expect(act).toHaveBeenCalledExactlyOnceWith('confirm', { note: '', guard: 'G1' }))
  })
})

it('explains a video classifier incident and retains explicit human confirmation',()=>{
  const incident:Incident={...event,model:'movinet-a0-vid-v1',detail:'Video classifier: possible physical conflict. Review the clip.'}
  render(<ReviewWindow event={incident} events={[incident]} cameras={[]} now={2000} clips={null} floors={[]} guards={guards} sample={false} queue={1} act={vi.fn()} close={vi.fn()} />)
  fireEvent.click(screen.getByText('Why this needs a look'))
  expect(screen.getByText(incident.detail)).toBeVisible()
  expect(screen.getByRole('button',{name:'Confirm & send G1'})).toBeVisible()
  expect(screen.queryByText('Test · not a real incident')).not.toBeInTheDocument()
})
