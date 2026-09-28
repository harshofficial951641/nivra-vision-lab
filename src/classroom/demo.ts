import type { Snapshot } from './contracts'
const now = Date.now()
export const demoSnapshot: Snapshot = {
  version: 2,
  type: 'snapshot',
  service: 'ready',
  publicOrigin: null,
  retention: 'event-records-only',
  experimental: true,
  runtime: { personModel: 'rtmo', fightModel: 'x3d', maxPeople: 50 },
  cameras: ['8A', '8B', '9A', '9B'].map((name, index) => ({
    id: `sample-${index}`,
    name: `Classroom ${name}`,
    building: 'Main building',
    floor: index < 2 ? 'Floor 1' : 'Floor 2',
    enabled: true,
    feed: index === 3 ? 'offline' : 'live',
    analysis: index === 3 ? 'unavailable' : 'current',
    generation: 'sample',
    framesReceived: 0,
    framesAnalyzed: 0,
    framesReplaced: 0,
    result:
      index === 3
        ? null
        : {
            timestampMs: 0,
            evidenceTimestampMs: 0,
            inferenceMs: 0,
            coverage: {
              observedPeople: 32,
              analyzedPeople: 32,
              excludedPeople: 0,
              status: index === 2 ? 'limited' : 'analyzing',
              actionPeople: index === 2 ? 12 : 32,
            },
            conflict: {
              status: index === 2 ? 'limited' : 'clear',
              explanation:
                'Illustrative state only. No model is analyzing this generated image.',
            },
          },
  })),
  events: [
    {
      id: 'sample-review',
      camera_id: 'sample-1',
      camera_name: 'Classroom 8B',
      location: 'Main building · Floor 1',
      received_at: now - 120000,
      source_ms: 0,
      evidence_ms: 0,
      model: 'sample',
      detail:
        'Example review event. This generated classroom image does not depict an incident.',
      status: 'open',
      revision: 0,
      updated_at: now - 120000,
    },
    {
      id: 'sample-resolved',
      camera_id: 'sample-0',
      camera_name: 'Classroom 8A',
      location: 'Main building · Floor 1',
      received_at: now - 1800000,
      source_ms: 0,
      evidence_ms: 0,
      model: 'sample',
      detail: 'Example resolved record.',
      status: 'resolved',
      revision: 1,
      updated_at: now - 1700000,
    },
  ],
  analytics: { total: 2, pending: 1, resolved: 1 },
}
