import type { GPSLocation } from '../location/gps'

// Shapes shared by the Command wall, Setup portal and Guard app.
// Server shapes follow docs/command-system-contract.md (snapshot v3).

export interface Placement {
  floorId: string
  /** Normalized 0..1 of the plan image. */
  x: number
  y: number
  /** Degrees, 0 = east, clockwise. */
  angle: number
  fov: number
  /** Fraction of plan width. */
  range: number
}

export interface FloorRecord {
  id: string
  name: string
  order: number
  plan: { url: string; width: number; height: number } | null
  sample: boolean
  metersPerUnit: number | null
}

export interface GuardRecord {
  gps?: GPSLocation | null
  floorName?: string | null
  id: string
  callsign: string
  name: string
  userId: string | null
  email: string | null
  floorId: string | null
  post: { x: number; y: number } | null
  shift: 'on_shift' | 'break' | 'off'
  presence: { online: boolean; lastSeen: number | null }
  push: boolean
}

/** A floor ready to draw, in plan units (pixels of the plan image). */
export interface MapFloor {
  id: string
  name: string
  width: number
  height: number
  metersPerUnit: number | null
  planUrl: string | null
  /** Draw the built-in sample mall instead of an image. */
  sample: boolean
}

/** Camera geometry in plan units. */
export interface CameraSlot {
  id: string
  label: string
  name: string
  x: number
  y: number
  angle: number
  fov: number
  range: number
  covers: string
  image: string
}

export interface WallGuard {
  gps?: GPSLocation | null
  floorName?: string | null
  /** Call sign, e.g. G2. */
  id: string
  name: string
  floorId: string | null
  /** Post in plan units; null when not placed. */
  x: number | null
  y: number | null
  status: 'available' | 'break' | 'off'
  online: boolean | null
  push: boolean | null
}
