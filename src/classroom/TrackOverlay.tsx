import { useEffect, useRef, useState } from 'react'
import type { CameraLocation } from './contracts'

export function TrackOverlay({
  tracks,
  width,
  height,
}: {
  tracks: NonNullable<CameraLocation['result']>['tracks']
  width: number
  height: number
}) {
  const element = useRef<HTMLDivElement>(null)
  const [size, setSize] = useState({ width: 0, height: 0 })
  useEffect(() => {
    const node = element.current
    if (!node) return
    const resize = new ResizeObserver((entries) =>
      setSize({
        width: entries[0].contentRect.width,
        height: entries[0].contentRect.height,
      }),
    )
    resize.observe(node)
    return () => resize.disconnect()
  }, [])
  const scale = Math.min(size.width / width, size.height / height),
    imageWidth = width * scale,
    imageHeight = height * scale
  const left = (size.width - imageWidth) / 2,
    top = (size.height - imageHeight) / 2
  return (
    <div className="nv-track-layer" ref={element} aria-hidden="true">
      {Number.isFinite(scale) &&
        tracks
          ?.filter((track) => track.observed)
          .map((track) => (
            <div
              key={track.id}
              className={`nv-track ${track.ambiguous ? 'is-ambiguous' : ''}`}
              style={{
                left: left + track.box[0] * imageWidth,
                top: top + track.box[1] * imageHeight,
                width: (track.box[2] - track.box[0]) * imageWidth,
                height: (track.box[3] - track.box[1]) * imageHeight,
              }}
            >
              <span>
                {track.ambiguous ? 'Uncertain track' : `Track ${track.id}`}
              </span>
            </div>
          ))}
    </div>
  )
}
