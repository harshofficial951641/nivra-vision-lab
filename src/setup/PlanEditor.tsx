import { useRef, useState, type KeyboardEvent, type PointerEvent } from 'react'
import { FloorMap } from '../command/FloorMap'
import type { WallCamera } from '../command/model'
import type { MapFloor, WallGuard } from '../command/types'

export type EditTarget = { kind: 'camera' | 'guard'; id: string }
export interface CameraGeometry {
  x: number
  y: number
  angle: number
}

interface Props {
  floor: MapFloor
  cameras: WallCamera[]
  guards: WallGuard[]
  mode: 'camera' | 'guard'
  selected: string | null
  /** Item waiting to be dropped with a click, e.g. an unplaced camera. */
  placing: string | null
  onSelect: (id: string | null) => void
  /** Live preview while dragging (plan units). */
  onPreview: (id: string, geometry: Partial<CameraGeometry>) => void
  /** Commit after the pointer is released or a key is pressed (plan units). */
  onCommit: (id: string, geometry: Partial<CameraGeometry>) => void
  onPlace: (id: string, point: { x: number; y: number }) => void
  label: string
}

const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value))
const normalizeAngle = (degrees: number) => ((Math.round(degrees) % 360) + 360) % 360

/**
 * Edit layer drawn over the shared FloorMap. Cameras drag to move and turn by
 * dragging the round handle at the end of their view axis. Guards drag to
 * their post. Keyboard: arrows move (Shift = larger steps), [ and ] rotate.
 */
export function PlanEditor({
  floor,
  cameras,
  guards,
  mode,
  selected,
  placing,
  onSelect,
  onPreview,
  onCommit,
  onPlace,
  label,
}: Props) {
  const svg = useRef<SVGSVGElement>(null)
  const drag = useRef<{ id: string; kind: 'move' | 'rotate'; last: Partial<CameraGeometry> } | null>(null)
  const [hover, setHover] = useState<{ x: number; y: number } | null>(null)
  const k = floor.width / 1000

  const toPlan = (event: { clientX: number; clientY: number }) => {
    const node = svg.current
    const matrix = node?.getScreenCTM()
    if (!node || !matrix) return null
    const point = new DOMPoint(event.clientX, event.clientY).matrixTransform(matrix.inverse())
    return { x: clamp(point.x, 0, floor.width), y: clamp(point.y, 0, floor.height) }
  }

  const onFloorCameras = cameras.filter((c) => c.floorId === floor.id && c.slot)
  const onFloorGuards = guards.filter((g) => g.floorId === floor.id && g.x != null && g.y != null)

  const start = (event: PointerEvent, id: string, kind: 'move' | 'rotate') => {
    event.stopPropagation()
    event.preventDefault()
    ;(event.currentTarget as Element).setPointerCapture(event.pointerId)
    onSelect(id)
    drag.current = { id, kind, last: {} }
  }
  const move = (event: PointerEvent) => {
    const point = toPlan(event)
    if (placing) setHover(point)
    const current = drag.current
    if (!current || !point) return
    let geometry: Partial<CameraGeometry>
    if (current.kind === 'move') geometry = { x: point.x, y: point.y }
    else {
      const camera = onFloorCameras.find((c) => c.id === current.id)
      if (!camera?.slot) return
      geometry = { angle: normalizeAngle((Math.atan2(point.y - camera.slot.y, point.x - camera.slot.x) * 180) / Math.PI) }
    }
    current.last = geometry
    onPreview(current.id, geometry)
  }
  const end = () => {
    const current = drag.current
    drag.current = null
    if (current && Object.keys(current.last).length) onCommit(current.id, current.last)
  }
  const click = (event: PointerEvent) => {
    if (drag.current) return
    const point = toPlan(event)
    if (placing && point) {
      onPlace(placing, point)
      setHover(null)
      return
    }
    if ((event.target as Element).closest('[data-handle]')) return
    onSelect(null)
  }
  const keys = (event: KeyboardEvent) => {
    if (!selected) return
    const step = (event.shiftKey ? 0.02 : 0.005) * floor.width
    const camera = onFloorCameras.find((c) => c.id === selected)
    const guard = onFloorGuards.find((g) => g.id === selected)
    const x = camera?.slot?.x ?? guard?.x
    const y = camera?.slot?.y ?? guard?.y
    if (x == null || y == null) return
    const moves: Record<string, [number, number]> = {
      ArrowLeft: [-step, 0],
      ArrowRight: [step, 0],
      ArrowUp: [0, -step],
      ArrowDown: [0, step],
    }
    if (moves[event.key]) {
      event.preventDefault()
      const [dx, dy] = moves[event.key]
      onCommit(selected, { x: clamp(x + dx, 0, floor.width), y: clamp(y + dy, 0, floor.height) })
    } else if (camera?.slot && (event.key === '[' || event.key === ']')) {
      event.preventDefault()
      onCommit(selected, { angle: normalizeAngle(camera.slot.angle + (event.key === ']' ? 5 : -5)) })
    } else if (event.key === 'Escape') onSelect(null)
  }

  const selectedCamera = mode === 'camera' ? onFloorCameras.find((c) => c.id === selected) : undefined
  const handle = selectedCamera?.slot
    ? {
        x: selectedCamera.slot.x + Math.cos((selectedCamera.slot.angle * Math.PI) / 180) * selectedCamera.slot.range,
        y: selectedCamera.slot.y + Math.sin((selectedCamera.slot.angle * Math.PI) / 180) * selectedCamera.slot.range,
      }
    : null

  return (
    <div className={`st-editor ${placing ? 'is-placing' : ''}`}>
      <FloorMap
        floor={floor}
        cameras={cameras}
        guards={mode === 'guard' ? [] : guards}
        events={[]}
        selected={mode === 'camera' ? selected : null}
        label={label}
      />
      <svg
        ref={svg}
        className="st-editor-layer"
        viewBox={`0 0 ${floor.width} ${floor.height}`}
        role="application"
        aria-label={`${label}. ${placing ? 'Click where it is mounted.' : 'Select an item, then drag it or use the arrow keys. [ and ] rotate a camera.'}`}
        tabIndex={0}
        onPointerMove={move}
        onPointerUp={end}
        onPointerCancel={end}
        onPointerDown={click}
        onPointerLeave={() => setHover(null)}
        onKeyDown={keys}
      >
        {mode === 'camera' &&
          onFloorCameras.map((camera) => (
            <circle
              key={camera.id}
              data-handle
              className={`st-grab ${camera.id === selected ? 'is-selected' : ''}`}
              cx={camera.slot!.x}
              cy={camera.slot!.y}
              r={18 * k}
              onPointerDown={(e) => start(e, camera.id, 'move')}
            >
              <title>{`${camera.label} ${camera.name}. Drag to move.`}</title>
            </circle>
          ))}
        {selectedCamera?.slot && handle && (
          <g data-handle>
            <line
              className="st-axis"
              x1={selectedCamera.slot.x}
              y1={selectedCamera.slot.y}
              x2={handle.x}
              y2={handle.y}
              style={{ strokeWidth: 1.5 * k, strokeDasharray: `${4 * k} ${4 * k}` }}
            />
            <circle className="st-rotate" cx={handle.x} cy={handle.y} r={9 * k} onPointerDown={(e) => start(e, selectedCamera.id, 'rotate')}>
              <title>Drag to turn the camera</title>
            </circle>
          </g>
        )}
        {mode === 'guard' &&
          onFloorGuards.map((guard) => (
            <g
              key={guard.id}
              data-handle
              className={`st-pin ${guard.id === selected ? 'is-selected' : ''}`}
              transform={`translate(${guard.x} ${guard.y}) scale(${k})`}
              onPointerDown={(e) => start(e, guard.id, 'move')}
            >
              <title>{`${guard.id} ${guard.name}. Drag to their post.`}</title>
              <circle r="15" />
              <text y="4">{guard.id}</text>
            </g>
          ))}
        {placing && hover && (
          <g className="st-ghost" transform={`translate(${hover.x} ${hover.y}) scale(${k})`} pointerEvents="none">
            <circle r="14" />
            <text y="-20">Click to place</text>
          </g>
        )}
      </svg>
    </div>
  )
}
