import { cleanup, render } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { CameraTile } from './CameraTile'
import { NativeVideoBus } from '../classroom/nativeVideo'
import type { WallCamera } from './model'
afterEach(()=>{cleanup();vi.unstubAllGlobals()})
it('leaves thumbnails JPEG-only while full tiles can subscribe to native video',()=>{
  vi.stubGlobal('VideoDecoder',undefined)
  const camera:WallCamera={id:'c',label:'CAM-1',name:'Entrance',floorId:null,slot:null,status:'live',sample:false,image:'blob:jpeg',people:0,fps:40,generation:'g'}
  const bus=new NativeVideoBus()
  const thumb=render(<CameraTile camera={camera} events={[]} now={1000} nativeVideo={bus} size="thumb"/>)
  expect(thumb.container.querySelector('canvas')).toBeNull()
  expect(thumb.container.querySelector('img')).toHaveAttribute('src','blob:jpeg')
  thumb.unmount()
  const full=render(<CameraTile camera={camera} events={[]} now={1000} nativeVideo={bus} size="hero"/>)
  expect(full.container.querySelector('canvas')).toBeInTheDocument()
})
