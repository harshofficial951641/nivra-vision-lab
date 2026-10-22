export interface PersonObservation {
  /** Full-frame normalized left, top, right, bottom. */
  box: [number, number, number, number]
  score: number
}
export interface PeopleResult {
  timestampMs: number
  inferenceMs: number
  people: PersonObservation[]
}
export type PeopleWorkerRequest =
  | { type: 'init'; modelPath: string; wasmRoot: string }
  | { type: 'frame'; bitmap: ImageBitmap; timestampMs: number }
export type PeopleWorkerResponse =
  | { type: 'ready' }
  | { type: 'people-result'; result: PeopleResult }
  | { type: 'error'; message: string }
