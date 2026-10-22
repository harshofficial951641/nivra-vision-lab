import { afterEach, describe, expect, it, vi } from 'vitest'
import { AlertPing } from './AlertPing'
afterEach(()=>vi.unstubAllGlobals())
describe('short wall ping',()=>{
  it('unlocks silently, schedules one short note, and disposes its audio context',async()=>{
    const note={type:'',frequency:{value:0},connect:vi.fn(),disconnect:vi.fn(),start:vi.fn(),stop:vi.fn(),onended:null as (()=>void)|null}
    const gain={gain:{setValueAtTime:vi.fn(),linearRampToValueAtTime:vi.fn(),exponentialRampToValueAtTime:vi.fn()},connect:vi.fn(),disconnect:vi.fn()}
    const close=vi.fn().mockResolvedValue(undefined),createOscillator=vi.fn(()=>note)
    class Audio { state='running';currentTime=10;destination={};createOscillator=createOscillator;createGain=()=>gain;close=close }
    vi.stubGlobal('AudioContext',Audio)
    const ping=new AlertPing()
    expect(await ping.prime()).toBe(true)
    expect(createOscillator).not.toHaveBeenCalled()
    await ping.play()
    expect(createOscillator).toHaveBeenCalledOnce()
    expect(note.start).toHaveBeenCalledOnce()
    expect(note.stop).toHaveBeenCalledExactlyOnceWith(10.16)
    await Promise.all([ping.play(), ping.play(), ping.play()])
    expect(createOscillator).toHaveBeenCalledOnce()
    note.onended?.()
    expect(note.disconnect).toHaveBeenCalledOnce()
    expect(gain.disconnect).toHaveBeenCalledOnce()
    ping.dispose();expect(close).toHaveBeenCalledOnce()
    await ping.play();expect(createOscillator).toHaveBeenCalledOnce()
  })
  it('does not play a late note when sound was muted during audio unlock',async()=>{
    let resume!:()=>void
    const createOscillator=vi.fn()
    class Audio {state='suspended';resume=()=>new Promise<void>(resolve=>{resume=()=>{this.state='running';resolve()}});createOscillator=createOscillator}
    vi.stubGlobal('AudioContext',Audio)
    const ping=new AlertPing(),pending=ping.play()
    ping.stop();resume();await pending
    expect(createOscillator).not.toHaveBeenCalled()
  })
})
