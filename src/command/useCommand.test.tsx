import { act, cleanup, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useCommand } from './useCommand'
import type { Incident } from '../classroom/contracts'
const { api }=vi.hoisted(()=>({api:vi.fn()}))
vi.mock('../classroom/contracts',async original=>({...await original<typeof import('../classroom/contracts')>(),api}))
vi.mock('../classroom/useClassroom',()=>({useClassroom:()=>({snapshot:null,previews:{},analysisPreviews:{},connection:'connected',error:''})}))
const event:Incident={id:'e1',camera_id:'c1',camera_name:'Entrance',location:'',received_at:1000,source_ms:1000,evidence_ms:1000,model:'test',detail:'Observed motion',status:'acknowledged',revision:7,updated_at:1000}
beforeEach(()=>vi.clearAllMocks())
afterEach(cleanup)
describe('closing a prior alert',()=>{
  it('patches only its resolved status and revision, releasing only that alert’s memory clip on success',async()=>{
    api.mockResolvedValue({})
    const {result}=renderHook(()=>useCommand(false))
    result.current.clips!.capture('e1','c1',1000)
    result.current.clips!.capture('e2','c1',1000)
    await act(async()=>result.current.review(event,'close'))
    expect(api).toHaveBeenCalledExactlyOnceWith('/events/e1','PATCH',{status:'resolved',revision:7})
    expect(result.current.clips!.get('e1')).toBeNull()
    expect(result.current.clips!.get('e2')).not.toBeNull()
  })
  it('preserves evidence on a failed write and sends the refreshed revision on explicit retry',async()=>{
    api.mockRejectedValueOnce(new Error('409 conflict')).mockResolvedValueOnce({})
    const {result}=renderHook(()=>useCommand(false))
    result.current.clips!.capture('e1','c1',1000)
    await expect(result.current.review(event,'close')).rejects.toThrow('409 conflict')
    expect(result.current.clips!.get('e1')).not.toBeNull()
    await act(async()=>result.current.review({...event,revision:8},'close'))
    expect(api).toHaveBeenLastCalledWith('/events/e1','PATCH',{status:'resolved',revision:8})
    expect(result.current.clips!.get('e1')).toBeNull()
  })
  it('does not close an already confirmed or resolved incident through the undecided action',async()=>{
    const {result}=renderHook(()=>useCommand(false))
    await expect(result.current.review({...event,decision:'confirmed'},'close')).rejects.toThrow('already changed')
    await expect(result.current.review({...event,status:'resolved'},'close')).rejects.toThrow('already changed')
    expect(api).not.toHaveBeenCalled()
  })
})
