// Sample floor plan for the Command demo. Positions are plan units in a
// 1000 × 620 viewBox; one unit is 0.1 m, so the floor is about 96 m wide.
// This is illustrative site data, not a surveyed building.
import type { CameraSlot, FloorRecord, MapFloor, Placement, WallGuard } from './types'
export type { CameraSlot } from './types'

export const PLAN = { width: 1000, height: 620, metersPerUnit: 0.1 } as const
export const SITE = { name: 'Orbit Mall', floor: 'Floor 2' } as const

export type RoomKind = 'shop' | 'washroom' | 'stair' | 'service' | 'cafe'
export interface Room {
  id: string
  label: string
  x: number
  y: number
  w: number
  h: number
  kind: RoomKind
}

export const ROOMS: Room[] = [
  { id: 'exit-a', label: 'Fire exit A', x: 20, y: 20, w: 70, h: 110, kind: 'stair' },
  { id: '201', label: '201 Apparel', x: 90, y: 20, w: 100, h: 110, kind: 'shop' },
  { id: '202', label: '202 Footwear', x: 190, y: 20, w: 100, h: 110, kind: 'shop' },
  { id: '203', label: '203 Electronics', x: 290, y: 20, w: 100, h: 110, kind: 'shop' },
  { id: '204', label: '204 Books', x: 390, y: 20, w: 90, h: 110, kind: 'shop' },
  { id: '205', label: '205 Eyewear', x: 480, y: 20, w: 90, h: 110, kind: 'shop' },
  { id: '211', label: '211 Mobile', x: 570, y: 20, w: 80, h: 110, kind: 'shop' },
  { id: 'wc', label: 'Washrooms', x: 650, y: 20, w: 140, h: 110, kind: 'washroom' },
  { id: '206', label: '206 Toys', x: 790, y: 20, w: 100, h: 110, kind: 'shop' },
  { id: 'exit-b', label: 'Fire exit B', x: 890, y: 20, w: 90, h: 110, kind: 'stair' },
  { id: '210', label: '210 Gifts', x: 20, y: 150, w: 110, h: 100, kind: 'shop' },
  { id: '209', label: '209 Sports', x: 20, y: 250, w: 110, h: 100, kind: 'shop' },
  { id: '208', label: '208 Salon', x: 20, y: 350, w: 110, h: 90, kind: 'shop' },
  { id: '207', label: '207 Café', x: 800, y: 150, w: 180, h: 70, kind: 'cafe' },
  { id: 'counters', label: 'Food counters', x: 940, y: 235, w: 40, h: 250, kind: 'service' },
  { id: '212', label: '212 Pharmacy', x: 200, y: 500, w: 112, h: 60, kind: 'shop' },
  { id: '213', label: '213 Beauty', x: 312, y: 500, w: 112, h: 60, kind: 'shop' },
  { id: '214', label: '214 Watches', x: 424, y: 500, w: 112, h: 60, kind: 'shop' },
  { id: '215', label: '215 Bags', x: 536, y: 500, w: 112, h: 60, kind: 'shop' },
  { id: '216', label: '216 Kids', x: 648, y: 500, w: 112, h: 60, kind: 'shop' },
  { id: 'service', label: 'Service corridor', x: 200, y: 560, w: 780, h: 40, kind: 'service' },
]

export const LIFTS = [
  { x: 30, y: 505, w: 40, h: 46 },
  { x: 75, y: 505, w: 40, h: 46 },
  { x: 120, y: 505, w: 40, h: 46 },
]
export const ATRIUM = { cx: 455, cy: 315, halfWidth: 210, radius: 120 }
export const ESCALATORS = [
  { x: 398, y: 365, w: 22, h: 72 },
  { x: 428, y: 365, w: 22, h: 72 },
]
export const SCENIC_LIFT = { x: 530, y: 402, r: 16 }
export const PLANTERS = [
  { x: 300, y: 252 },
  { x: 300, y: 378 },
  { x: 610, y: 252 },
  { x: 610, y: 378 },
  { x: 455, y: 268 },
]
export const FOOD_TABLES = [800, 845, 890].flatMap((x) =>
  [275, 320, 365, 410, 455].map((y) => ({ x, y })),
)
export const EXITS = [
  { id: 'exit-a', x: 55, y: 75 },
  { id: 'exit-b', x: 935, y: 75 },
]

export const CAMERA_SLOTS: CameraSlot[] = [
  { id: 'cam-01', label: 'CAM-01', name: 'Shop row B', x: 215, y: 150, angle: 5, fov: 50, range: 200, covers: '201 Apparel, 202 Footwear, 203 Electronics', image: '/demo/mall/cam-01-shop-row-b.jpg' },
  { id: 'cam-02', label: 'CAM-02', name: 'Shop row A', x: 770, y: 150, angle: 175, fov: 50, range: 200, covers: '204 Books, 205 Eyewear, 211 Mobile', image: '/demo/mall/cam-02-shop-row-a.jpg' },
  { id: 'cam-03', label: 'CAM-03', name: 'Lift bank', x: 215, y: 475, angle: 165, fov: 70, range: 150, covers: 'Lifts 1–3', image: '/demo/mall/cam-03-lift-bank.jpg' },
  { id: 'cam-04', label: 'CAM-04', name: 'Atrium East', x: 705, y: 195, angle: 92, fov: 60, range: 220, covers: 'Atrium east walkway and railing', image: '/demo/mall/cam-04-atrium-east.jpg' },
  { id: 'cam-05', label: 'CAM-05', name: 'Lift lobby', x: 100, y: 445, angle: 60, fov: 70, range: 130, covers: 'Lift lobby, 208 Salon', image: '/demo/mall/cam-05-lift-lobby.jpg' },
  { id: 'cam-06', label: 'CAM-06', name: 'Food court east', x: 965, y: 515, angle: 220, fov: 70, range: 170, covers: 'Food court seating', image: '/demo/mall/cam-06-food-court-east.jpg' },
  { id: 'cam-07', label: 'CAM-07', name: 'Food court', x: 790, y: 245, angle: 40, fov: 75, range: 200, covers: 'Food court, 207 Café', image: '/demo/mall/cam-07-food-court.jpg' },
  { id: 'cam-08', label: 'CAM-08', name: 'Escalator landing', x: 440, y: 485, angle: 270, fov: 70, range: 120, covers: 'Escalators, 213 Beauty', image: '/demo/mall/cam-08-escalator-landing.jpg' },
  { id: 'cam-09', label: 'CAM-09', name: 'Service corridor', x: 965, y: 580, angle: 180, fov: 24, range: 300, covers: 'Service corridor', image: '' },
  { id: 'cam-10', label: 'CAM-10', name: 'Salon corridor', x: 185, y: 190, angle: 90, fov: 55, range: 250, covers: '210 Gifts, 209 Sports, 208 Salon', image: '/demo/mall/cam-10-salon-corridor.jpg' },
]

export const SAMPLE_FLOOR: MapFloor = {
  id: 'sample',
  name: SITE.floor,
  width: PLAN.width,
  height: PLAN.height,
  metersPerUnit: PLAN.metersPerUnit,
  planUrl: null,
  sample: true,
}

export const SAMPLE_GUARDS: WallGuard[] = [
  { id: 'G1', name: 'Imran', x: 150, y: 262, status: 'break' },
  { id: 'G2', name: 'Rohan', x: 690, y: 452, status: 'available' },
  { id: 'G3', name: 'Priya', x: 300, y: 160, status: 'available' },
  { id: 'G4', name: 'Arjun', x: 905, y: 525, status: 'available' },
  { id: 'G5', name: 'Meera', x: 420, y: 470, status: 'available' },
].map((g) => ({ ...g, floorId: 'sample', online: null, push: null }) as WallGuard)

/** Convert a server floor into drawable plan units. */
export function mapFloor(floor: FloorRecord): MapFloor {
  if (floor.sample || !floor.plan)
    return {
      id: floor.id,
      name: floor.name,
      width: floor.plan?.width ?? PLAN.width,
      height: floor.plan?.height ?? PLAN.height,
      metersPerUnit: floor.metersPerUnit ?? (floor.sample ? PLAN.metersPerUnit : null),
      planUrl: floor.sample ? null : floor.plan?.url ?? null,
      sample: floor.sample,
    }
  return {
    id: floor.id,
    name: floor.name,
    width: floor.plan.width,
    height: floor.plan.height,
    metersPerUnit: floor.metersPerUnit,
    planUrl: floor.plan.url,
    sample: false,
  }
}

/** Normalized placement → plan units. */
export function slotFromPlacement(
  camera: { id: string; label?: string | null; name: string },
  placement: Placement,
  floor: MapFloor,
): CameraSlot {
  return {
    id: camera.id,
    label: camera.label || camera.name,
    name: camera.name,
    x: placement.x * floor.width,
    y: placement.y * floor.height,
    angle: placement.angle,
    fov: placement.fov,
    range: placement.range * floor.width,
    covers: '',
    image: '',
  }
}

const radians = (degrees: number) => (degrees * Math.PI) / 180

/** SVG path for a camera's field-of-view wedge. */
export function conePath(slot: Pick<CameraSlot, 'x' | 'y' | 'angle' | 'fov' | 'range'>) {
  const start = radians(slot.angle - slot.fov / 2)
  const end = radians(slot.angle + slot.fov / 2)
  const ax = slot.x + Math.cos(start) * slot.range
  const ay = slot.y + Math.sin(start) * slot.range
  const bx = slot.x + Math.cos(end) * slot.range
  const by = slot.y + Math.sin(end) * slot.range
  const large = slot.fov > 180 ? 1 : 0
  return `M ${slot.x} ${slot.y} L ${ax.toFixed(1)} ${ay.toFixed(1)} A ${slot.range} ${slot.range} 0 ${large} 1 ${bx.toFixed(1)} ${by.toFixed(1)} Z`
}

/**
 * Approximate incident position: the middle of the camera's view. A single
 * 2D camera cannot place a person on the floor without calibration.
 */
export function incidentPoint(slot: Pick<CameraSlot, 'x' | 'y' | 'angle' | 'range'>) {
  const axis = radians(slot.angle)
  return {
    x: Math.round(slot.x + Math.cos(axis) * slot.range * 0.55),
    y: Math.round(slot.y + Math.sin(axis) * slot.range * 0.55),
  }
}

/** Metres between two plan points, or null when the floor has no scale. */
export const distanceMeters = (
  a: { x: number; y: number },
  b: { x: number; y: number },
  metersPerUnit: number | null = PLAN.metersPerUnit,
) => (metersPerUnit ? Math.hypot(a.x - b.x, a.y - b.y) * metersPerUnit : null)

/** Straight-line walking estimate at 1.3 m/s, rounded to 5 s. */
export const walkSeconds = (meters: number) =>
  Math.max(5, Math.round(meters / 1.3 / 5) * 5)

export interface RankedGuard {
  guard: WallGuard
  meters: number | null
  seconds: number | null
  /** Plan-unit distance, used for ordering when there is no scale. */
  units: number
}

/** Guards on this floor with a post: available first, then by distance. */
export function nearestGuards(
  point: { x: number; y: number },
  guards: WallGuard[],
  metersPerUnit: number | null = PLAN.metersPerUnit,
): RankedGuard[] {
  return guards
    .filter((g): g is WallGuard & { x: number; y: number } => g.x != null && g.y != null)
    .map((guard) => {
      const units = Math.hypot(point.x - guard.x, point.y - guard.y)
      const meters = metersPerUnit ? Math.round(units * metersPerUnit) : null
      return { guard, units, meters, seconds: meters == null ? null : walkSeconds(meters) }
    })
    .sort(
      (a, b) =>
        Number(a.guard.status !== 'available') - Number(b.guard.status !== 'available') || a.units - b.units,
    )
}

/** A window around two points, kept inside the plan, for the guard route view. */
export function routeView(
  a: { x: number; y: number },
  b: { x: number; y: number },
  floor: Pick<MapFloor, 'width' | 'height'> = PLAN,
) {
  const scale = floor.width / PLAN.width
  const pad = 110 * scale
  let x0 = Math.min(a.x, b.x) - pad
  let y0 = Math.min(a.y, b.y) - pad
  let w = Math.abs(a.x - b.x) + pad * 2
  let h = Math.abs(a.y - b.y) + pad * 2
  const side = Math.max(w, h * 1.1, 340 * scale)
  x0 -= (side - w) / 2
  y0 -= (side / 1.1 - h) / 2
  w = Math.min(side, floor.width)
  h = Math.min(side / 1.1, floor.height)
  x0 = Math.max(0, Math.min(x0, floor.width - w))
  y0 = Math.max(0, Math.min(y0, floor.height - h))
  return { x: Math.round(x0), y: Math.round(y0), w: Math.round(w), h: Math.round(h) }
}
