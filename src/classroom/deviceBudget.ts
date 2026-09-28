export type AnalysisArea = 'full' | 'left' | 'center' | 'right'
export type DeviceProfile = 'balanced' | 'detail'
export const analysisRegion = (area: AnalysisArea) => area === 'full'
  ? { x: 0, y: 0, width: 1, height: 1 }
  : { x: area === 'left' ? 0 : area === 'center' ? .25 : .5, y: 0, width: .5, height: 1 }

/** Adjust expendable preview work before sacrificing inference resolution. */
export class DeviceBudget {
  private averageMs = 0
  observe(inferenceMs: number) {
    if (!Number.isFinite(inferenceMs) || inferenceMs < 0) return
    this.averageMs = this.averageMs ? this.averageMs * .8 + inferenceMs * .2 : inferenceMs
  }
  get previewSide() { return this.averageMs > 140 ? 640 : 960 }
  get previewInterval() { return this.averageMs > 140 ? 125 : 84 }
  get analysisInterval() { return Math.max(100, Math.min(500, this.averageMs * 1.2)) }
  get inferenceMs() { return this.averageMs }
}
