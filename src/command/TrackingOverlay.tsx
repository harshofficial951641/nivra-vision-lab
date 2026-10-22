import { Skeletons } from '../classroom/SkeletonOverlay'
import type { CameraPose } from '../classroom/skeletonGeometry'
import { useEffect, useRef, useState } from 'react'
import { containedTrackBox, type WallTrack } from './tracking'

export function TrackingOverlay({ tracks, poses, width, height }: { tracks: WallTrack[]; poses?: CameraPose[]; width: number; height: number }) {
  const element = useRef<HTMLDivElement>(null)
  const [size, setSize] = useState({ width: 0, height: 0 })
  useEffect(() => {
    const node = element.current
    if (!node) return
    const measure = () => { const rect = node.getBoundingClientRect(); setSize({ width: rect.width, height: rect.height }) }
    measure()
    if (typeof ResizeObserver === 'undefined') {
      window.addEventListener('resize', measure)
      return () => window.removeEventListener('resize', measure)
    }
    const observer = new ResizeObserver(entries => {
      const rect = entries[0]?.contentRect
      if (rect) setSize({ width: rect.width, height: rect.height })
    })
    observer.observe(node)
    return () => observer.disconnect()
  }, [])
  return <div className="cm-tracking-layer" ref={element} aria-hidden="true"><Skeletons poses={poses} sourceWidth={width} sourceHeight={height} width={size.width} height={size.height} />{tracks.map(track => {
    const position = containedTrackBox(track.box, width, height, size.width, size.height)
    return position && <div key={track.id} className={`cm-person-track ${track.ambiguous ? 'is-tentative' : ''}`} style={position}><span>Track {track.id}{track.ambiguous ? ' · tentative' : ''}</span></div>
  })}</div>
}
