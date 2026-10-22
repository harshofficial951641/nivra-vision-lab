import { useId, type KeyboardEvent } from 'react'
import type { Incident } from '../classroom/contracts'
import { alertLevel, isActiveResponse, needsDecision, type WallCamera } from './model'
import {
  ATRIUM,
  ESCALATORS,
  EXITS,
  FOOD_TABLES,
  LIFTS,
  PLANTERS,
  ROOMS,
  SCENIC_LIFT,
  conePath,
  incidentPoint,
  nearestGuards,
  type Room,
} from './siteMap'
import type { MapFloor, WallGuard } from './types'

interface Props {
  floor: MapFloor
  cameras: WallCamera[]
  guards: WallGuard[]
  events: Incident[]
  selected?: string | null
  onSelect?: (id: string) => void
  /** Incident whose guard routes are drawn. */
  focus?: Incident | null
  /** Guard chosen in the review window. */
  chosenGuard?: string | null
  compact?: boolean
  label?: string
  /** Zoomed viewBox in plan units; defaults to the whole floor. */
  view?: { x: number; y: number; w: number; h: number }
}

const { cx, cy, halfWidth, radius } = ATRIUM
const stadium = (inset: number) => {
  const r = radius - inset
  const left = cx - halfWidth + radius
  const right = cx + halfWidth - radius
  return `M ${left} ${cy - r} H ${right} A ${r} ${r} 0 0 1 ${right} ${cy + r} H ${left} A ${r} ${r} 0 0 1 ${left} ${cy - r} Z`
}

function door(room: Room) {
  const mid = (a: number, b: number) => a + b / 2
  if (room.y + room.h === 130) return { x1: mid(room.x, room.w) - 11, y1: 130, x2: mid(room.x, room.w) + 11, y2: 130 }
  if (room.x === 20 && room.y >= 150) return { x1: 130, y1: mid(room.y, room.h) - 11, x2: 130, y2: mid(room.y, room.h) + 11 }
  if (room.y === 500) return { x1: mid(room.x, room.w) - 11, y1: 500, x2: mid(room.x, room.w) + 11, y2: 500 }
  if (room.id === '207') return { x1: 800, y1: 175, x2: 800, y2: 197 }
  return null
}

/** The built-in sample mall (1000 × 620 plan units). */
function SamplePlan({ compact }: { compact: boolean }) {
  return (
    <>
      <rect className="cm-map-floor" x="20" y="20" width="960" height="580" />
      {ROOMS.map((room) => {
        const opening = door(room)
        return (
          <g key={room.id} className={`cm-room cm-room--${room.kind}`}>
            <rect x={room.x} y={room.y} width={room.w} height={room.h} />
            {opening && <line className="cm-door" {...opening} />}
            {!compact && room.kind !== 'stair' && (
              <text x={room.x + room.w / 2} y={room.y + room.h / 2 + 4}>
                {room.label}
              </text>
            )}
          </g>
        )
      })}
      {LIFTS.map((lift, index) => (
        <g key={index} className="cm-lift">
          <rect x={lift.x} y={lift.y} width={lift.w} height={lift.h} />
          <path d={`M ${lift.x} ${lift.y} L ${lift.x + lift.w} ${lift.y + lift.h} M ${lift.x + lift.w} ${lift.y} L ${lift.x} ${lift.y + lift.h}`} />
        </g>
      ))}
      {!compact && (
        <text className="cm-area-label" x="110" y="485">
          Lift lobby
        </text>
      )}
      <path className="cm-atrium" d={stadium(0)} />
      <path className="cm-atrium-rail" d={stadium(9)} />
      {!compact && (
        <text className="cm-area-label" x={cx - 70} y={cy + 4}>
          Atrium
        </text>
      )}
      {ESCALATORS.map((escalator, index) => (
        <g key={index} className="cm-escalator">
          <rect x={escalator.x} y={escalator.y} width={escalator.w} height={escalator.h} />
          {Array.from({ length: 8 }, (_, step) => (
            <line
              key={step}
              x1={escalator.x + 3}
              x2={escalator.x + escalator.w - 3}
              y1={escalator.y + 8 + step * 8}
              y2={escalator.y + 8 + step * 8}
            />
          ))}
        </g>
      ))}
      {!compact && (
        <text className="cm-small-label" x="424" y="452">
          Escalators
        </text>
      )}
      <circle className="cm-scenic" cx={SCENIC_LIFT.x} cy={SCENIC_LIFT.y} r={SCENIC_LIFT.r} />
      {PLANTERS.map((planter, index) => (
        <g key={index} className="cm-planter">
          <circle cx={planter.x} cy={planter.y} r="13" />
          <circle cx={planter.x} cy={planter.y} r="6" />
        </g>
      ))}
      {FOOD_TABLES.map((table, index) => (
        <circle key={index} className="cm-table" cx={table.x} cy={table.y} r="9" />
      ))}
      {!compact && (
        <text className="cm-area-label" x="850" y="505">
          Food court
        </text>
      )}
      {EXITS.map((exit) => (
        <g key={exit.id} className="cm-exit">
          <rect x={exit.x - 22} y={exit.y - 11} width="44" height="22" rx="3" />
          <text x={exit.x} y={exit.y + 4}>
            EXIT
          </text>
          {!compact && (
            <text className="cm-exit-label" x={exit.x} y={exit.y + 30}>
              {exit.id === 'exit-a' ? 'Fire exit A' : 'Fire exit B'}
            </text>
          )}
        </g>
      ))}

    </>
  )
}

export function FloorMap({
  floor,
  cameras: allCameras,
  guards: allGuards,
  events,
  selected = null,
  onSelect,
  focus = null,
  chosenGuard = null,
  compact = false,
  label,
  view,
}: Props) {
  const clipId = useId()
  // Markers scale with the plan so icons read the same on any image size.
  const k = floor.width / 1000
  const cameras = allCameras.filter((c) => c.floorId === floor.id && c.slot)
  const guards = allGuards.filter((g) => g.floorId === floor.id && g.x != null && g.y != null)
  const incidents = events.filter((e) => needsDecision(e) || isActiveResponse(e))
  const focusCamera = focus ? cameras.find((c) => c.id === focus.camera_id) : undefined
  const focusPoint = focusCamera?.slot ? incidentPoint(focusCamera.slot) : null
  const ranked = focusPoint ? nearestGuards(focusPoint, guards, floor.metersPerUnit) : []
  const routeGuards = focus
    ? ranked.filter((r) =>
        focus.guard ? r.guard.id === focus.guard : chosenGuard ? r.guard.id === chosenGuard : false,
      )
    : []
  const shownRoutes = routeGuards.length
    ? routeGuards
    : ranked.filter((r) => r.guard.status === 'available').slice(0, focus?.decision ? 0 : 2)
  const bounds = floor.sample ? { x: 20, y: 20, w: 960, h: 580 } : { x: 0, y: 0, w: floor.width, h: floor.height }

  const keySelect = (event: KeyboardEvent, id: string) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      onSelect?.(id)
    }
  }

  return (
    <svg
      className={`cm-map ${compact ? 'cm-map--compact' : ''}`}
      viewBox={view ? `${view.x} ${view.y} ${view.w} ${view.h}` : `0 0 ${floor.width} ${floor.height}`}
      role="group"
      aria-label={label ?? `${floor.name} map`}
    >
      <defs>
        <clipPath id={clipId}>
          <rect x={bounds.x} y={bounds.y} width={bounds.w} height={bounds.h} />
        </clipPath>
      </defs>
      {floor.sample ? (
        <SamplePlan compact={compact} />
      ) : floor.planUrl ? (
        <image href={floor.planUrl} x="0" y="0" width={floor.width} height={floor.height} preserveAspectRatio="none" />
      ) : (
        <g className="cm-noplan">
          <rect x="0" y="0" width={floor.width} height={floor.height} />
          <text x={floor.width / 2} y={floor.height / 2} fontSize={18 * k}>
            No floor plan yet. Upload one in Setup.
          </text>
        </g>
      )}

      <g clipPath={`url(#${clipId})`}>
        {cameras.map((camera) => {
          const level = alertLevel(camera.id, events)
          const state = level
            ? 'alert'
            : selected === camera.id
              ? 'selected'
              : selected
                ? 'dim'
                : camera.status === 'offline'
                  ? 'offline'
                  : 'idle'
          return (
            <path
              key={`cone-${camera.id}`}
              className={`cm-cone cm-cone--${state}`}
              d={conePath(camera.slot!)}
              style={{ strokeWidth: (state === 'selected' ? 2 : 1) * k }}
              onClick={() => onSelect?.(camera.id)}
            />
          )
        })}
      </g>

      {shownRoutes.map(({ guard, meters }) =>
        focusPoint && guard.x != null && guard.y != null ? (
          <g key={`route-${guard.id}`} className="cm-route">
            <line
              x1={guard.x}
              y1={guard.y}
              x2={focusPoint.x}
              y2={focusPoint.y}
              style={{ strokeWidth: 1.6 * k, strokeDasharray: `${5 * k} ${5 * k}` }}
            />
            {!compact && meters != null && (
              <text
                x={(guard.x + focusPoint.x) / 2 + 8 * k}
                y={(guard.y + focusPoint.y) / 2}
                style={{ fontSize: 11 * k, strokeWidth: 3 * k }}
              >
                {meters} m
              </text>
            )}
          </g>
        ) : null,
      )}

      {incidents.map((event) => {
        const camera = cameras.find((c) => c.id === event.camera_id)
        if (!camera?.slot) return null
        const point = incidentPoint(camera.slot)
        const review = needsDecision(event)
        return (
          <g
            key={`incident-${event.id}`}
            className={`cm-incident ${review ? 'is-review' : ''}`}
            transform={`translate(${point.x} ${point.y}) scale(${k})`}
          >
            <circle className="cm-incident-pulse" r="20" />
            <circle className="cm-incident-dot" r="8" />
            {!compact && (
              <g className="cm-incident-label" transform="translate(16 -12)">
                <rect width={review ? 168 : 132} height="22" rx="4" />
                <text x="8" y="15">
                  {review ? 'Possible physical conflict' : 'Confirmed incident'}
                </text>
              </g>
            )}
          </g>
        )
      })}

      {guards.map((guard) => (
        <g
          key={guard.id}
          className={`cm-guard ${guard.status !== 'available' ? 'is-break' : ''} ${chosenGuard === guard.id || focus?.guard === guard.id ? 'is-chosen' : ''}`}
          transform={`translate(${guard.x} ${guard.y}) scale(${k})`}
        >
          <title>{`${guard.id} ${guard.name}${guard.status === 'break' ? ' · on break' : guard.status === 'off' ? ' · off shift' : ''}`}</title>
          <circle r={compact ? 9 : 12} />
          {!compact && <text y="4">{guard.id}</text>}
        </g>
      ))}

      {cameras.map((camera) => {
        const slot = camera.slot!
        const level = alertLevel(camera.id, events)
        const status =
          level === 'review' ? 'possible incident, review needed' : level === 'confirmed' ? 'confirmed incident' : camera.status
        const labelLeft = slot.x > floor.width * 0.9
        return (
          <g
            key={`camera-${camera.id}`}
            className={`cm-camera ${selected === camera.id ? 'is-selected' : ''} ${level ? 'is-alert' : ''} ${camera.status === 'offline' ? 'is-offline' : ''}`}
            role={onSelect ? 'button' : undefined}
            tabIndex={onSelect ? 0 : undefined}
            aria-label={onSelect ? `${camera.label} ${camera.name}, ${status}` : undefined}
            aria-pressed={onSelect ? selected === camera.id : undefined}
            onClick={() => onSelect?.(camera.id)}
            onKeyDown={(event) => keySelect(event, camera.id)}
            transform={`translate(${slot.x} ${slot.y}) scale(${k})`}
          >
            <circle className="cm-camera-hit" r="17" />
            <g transform={`rotate(${slot.angle})`}>
              <rect className="cm-camera-body" x="-9" y="-6" width="14" height="12" rx="2" />
              <path className="cm-camera-body" d="M 5 -4 L 11 -7 L 11 7 L 5 4 Z" />
            </g>
            {!compact && (
              <text className={`cm-camera-label ${labelLeft ? 'is-left' : ''}`} x={labelLeft ? -14 : 14} y="-12">
                {camera.label}
                {camera.status === 'offline' ? ' · offline' : ''}
              </text>
            )}
          </g>
        )
      })}

      {!compact && floor.sample && (
        <g className="cm-compass" transform="translate(48 588)">
          <path d="M 0 -26 L 7 -6 L 0 -11 L -7 -6 Z" />
          <text y="2">N</text>
          <g transform="translate(26 -6)">
            <line x1="0" x2="100" y1="0" y2="0" />
            <line x1="0" x2="0" y1="-4" y2="4" />
            <line x1="100" x2="100" y1="-4" y2="4" />
            <text x="50" y="-7">
              10 m
            </text>
          </g>
        </g>
      )}
    </svg>
  )
}
