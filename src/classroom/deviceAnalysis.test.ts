import { describe, expect, it } from 'vitest'
import { demoFrame } from '../lib/demoScene'
import { DeviceAnalysis } from './deviceAnalysis'

describe('original Nivra detector on camera devices', () => {
  it('expires unsent review events after a camera stall instead of replaying stale evidence', () => {
    const analysis = new DeviceAnalysis()
    const poses = (extended: boolean) => Array.from({ length: 3 }, (_, pair) =>
      demoFrame(extended ? 1861 : 0, 'conflict').poses.map(pose => pose.map(point => ({ ...point,
        x: .03 + pair * .3 + point.x * .3, y: .1 + point.y * .3,
      }))),
    ).flat()
    for (let time = 0; time < 700; time += 100) analysis.update(time, 10, poses(false), 16 / 9, 'CPU')
    expect(analysis.update(700, 10, poses(true), 16 / 9, 'CPU').events).toHaveLength(2)
    expect(analysis.update(6001, 10, poses(false), 16 / 9, 'CPU').events).toEqual([])
  })
  it.each([6, 20])('drains all disjoint interactions among %i observed poses in bounded fresh batches', count => {
    const analysis = new DeviceAnalysis()
    const received: string[] = []
    const batches: string[][] = []
    for (let time = 0; time <= 1400; time += 100) {
      const poses = Array.from({ length: count / 2 }, (_, pair) =>
        demoFrame(time === 700 ? 1861 : 0, 'conflict').poses.map(pose =>
          pose.map(point => ({ ...point, x: .03 + pair % 5 * .2 + point.x * .22,
            y: .1 + Math.floor(pair / 5) * .45 + point.y * .22 }))),
      ).flat()
      const result = analysis.update(time, 10, poses, 16 / 9, 'CPU')
      expect(result.events.length).toBeLessThanOrEqual(2)
      if (time >= 700) batches.push(result.events.map(event => event.id))
      received.push(...result.events.map(event => event.id))
    }
    expect(received).toHaveLength(count / 2)
    expect(new Set(received).size).toBe(count / 2)
    expect(batches[0][0]).toMatch(new RegExp(`-conflict-${count / 2}$`))
    expect(batches[0][1]).toMatch(new RegExp(`-conflict-${count / 2 - 1}$`))
    expect(batches.at(-1)).toEqual([])
  })
  it('keeps established bodies through slow inference and detects a later observed fast reach', () => {
    const engine = new DeviceAnalysis()
    let ids: number[] = []
    for (const time of [0, 1800, 3600]) {
      const report = engine.update(time, time === 0 ? 1600 : 80, demoFrame(0, 'conflict').poses, 16 / 9, 'CPU')
      if (!time) ids = report.tracks.map(track => track.id)
      else {
        expect(report.tracks.map(track => track.id)).toEqual(ids)
        expect(report.conflict.status).toBe('limited')
        expect(report.conflict.explanation).toContain('Motion sampling is too slow')
        expect(report.conflict.explanation).toContain('updates are 1.8 seconds apart')
      }
      expect(report.events).toEqual([])
    }
    // A genuinely sampled fast motion is still required after the slow frames.
    const reach = engine.update(3700, 80, demoFrame(1861, 'conflict').poses, 16 / 9, 'CPU')
    expect(reach.events).toHaveLength(1)
    expect(reach.conflict.status).toBe('alert')
  })

  it('does not turn sparse arm-position changes into a conflict review', () => {
    const engine = new DeviceAnalysis()
    for (let sample = 0; sample < 8; sample++) {
      const report = engine.update(sample * 1800, 1600,
        demoFrame(sample % 2 ? 1861 : 0, 'conflict').poses, 16 / 9, 'CPU')
      expect(report.events).toEqual([])
    }
  })
  it('transports only observed full-frame joints and preserves missing joints', () => {
    const pose = demoFrame(0, 'calm').poses[0].map(point => ({ ...point }))
    pose[0] = { ...pose[0], x: .123456, y: .456789, visibility: .987654 }
    pose[1] = { ...pose[1], x: -1 }
    pose[2] = { ...pose[2], y: NaN }
    pose[3] = { ...pose[3], visibility: undefined }
    const report = new DeviceAnalysis().update(0, 10, [pose], 16 / 9, 'GPU', 'right')
    expect(report.poses).toHaveLength(1)
    expect(report.poses[0]).toHaveLength(33)
    expect(report.poses[0][0]).toEqual([.5617, .4568, .9877])
    expect(report.poses[0].slice(1, 4)).toEqual([null, null, null])
    const empty = new DeviceAnalysis().update(0, 10, [], 16 / 9, 'GPU')
    expect(empty.poses).toEqual([])
  })
  it('reports 32 observed people separately from pose motion coverage', () => {
    const engine = new DeviceAnalysis()
    const people = Array.from({ length: 32 }, (_, i) => ({ box: [i % 8 / 8, Math.floor(i / 8) / 4,
      i % 8 / 8 + .09, Math.floor(i / 8) / 4 + .2] as [number, number, number, number] }))
    const report = engine.update(100, 80, [], 16 / 9, 'CPU', 'full', people)
    expect(report.observedPeople).toBe(32)
    expect(report.usablePeople).toBe(0)
    expect(report.tracks).toHaveLength(32)
    expect(report.events).toEqual([])
    expect(report.conflict.status).toBe('limited')
  })

  it('does not count the same two pose subjects twice among 20 person detections', () => {
    const poses = demoFrame(0, 'calm').poses
    const poseTracks = new DeviceAnalysis().update(0, 10, poses, 16 / 9, 'GPU').tracks
    const people = [...poseTracks, ...Array.from({ length: 18 }, (_, i) => ({
      box: [i / 20, .01, i / 20 + .025, .08] as [number, number, number, number],
    }))]
    const result = new DeviceAnalysis().update(0, 80, poses, 16 / 9, 'GPU', 'full', people)
    expect(result.observedPeople).toBe(20)
    expect(result.usablePeople).toBe(2)
    expect(result.tracks).toHaveLength(20)
    expect(result.events).toEqual([])
  })
  it('does not inflate person counts when a proposal pose drifts outside its detected box', () => {
    const poses = demoFrame(0, 'calm').poses
    const people = [{ box: [.01, .01, .1, .3] as [number, number, number, number] }, { box: [.8, .1, .95, .4] as [number, number, number, number] }]
    const report = new DeviceAnalysis().update(0, 80, poses, 16 / 9, 'CPU', 'full', people)
    expect(report.observedPeople).toBe(2)
    expect(report.tracks).toHaveLength(2)
  })
  it('exposes insufficient motion sampling when classroom inference takes over a second', () => {
    const report = new DeviceAnalysis().update(0, 1700, demoFrame(0, 'calm').poses, 16 / 9, 'CPU')
    expect(report.conflict.status).toBe('limited')
    expect(report.conflict.explanation).toContain('too slow for reliable conflict review')
    expect(report.events).toEqual([])
  })
  it('keeps nearby people tracked and emits a review with 700 ms camera-device samples', () => {
    const engine = new DeviceAnalysis()
    const events = new Set<string>()
    let ids: number[] = []
    for (let sample = 0; sample < 10; sample++) {
      // Scripted landmarks represent a rest, directed reach and withdrawal.
      // They test temporal admission, not a model's accuracy on real footage.
      const extended = sample >= 3 && sample % 2 === 1
      const poses = demoFrame(extended ? 1861 : 0, 'conflict').poses
      const report = engine.update(sample * 700, 620, poses, 16 / 9, 'CPU')
      expect(report.usablePeople).toBe(2)
      if (!sample) ids = report.tracks.map(track => track.id)
      else expect(report.tracks.map(track => track.id)).toEqual(ids)
      report.events.forEach(event => events.add(event.id))
    }
    expect(events.size).toBe(1)
  })

  it('keeps a slow-sampled four-person waving crowd quiet', () => {
    const engine = new DeviceAnalysis()
    for (let sample = 0; sample < 12; sample++) {
      const poses = [-.23, .23].flatMap(offset => demoFrame(sample * 700, 'calm').poses.map(pose =>
        pose.map(point => ({ ...point, x: .5 + (point.x - .5) * .55 + offset + Math.sin(sample) * .01,
          y: .15 + point.y * .7 }))))
      const report = engine.update(sample * 700, 620, poses, 16 / 9, 'CPU')
      expect(report.usablePeople).toBe(4)
      expect(report.events).toEqual([])
    }
  })

  it('never treats an arm position change across a long camera stall as a hit', () => {
    const engine = new DeviceAnalysis()
    for (const time of [0, 200, 400]) engine.update(time, 100, demoFrame(0, 'conflict').poses, 16 / 9, 'CPU')
    for (const time of [2500, 3200, 3900, 4600]) {
      expect(engine.update(time, 620, demoFrame(1861, 'conflict').poses, 16 / 9, 'CPU').events).toEqual([])
    }
  })

  it('admits ten small visible bodies without merging their neighboring tracks', () => {
    const engine = new DeviceAnalysis()
    const original = demoFrame(0, 'calm').poses[0]
    const poses = Array.from({ length: 10 }, (_, i) => original.map(p => ({
      ...p, x: .075 + (i % 5) * .2 + (p.x - .34) * .22, y: .15 + Math.floor(i / 5) * .42 + p.y * .22,
    })))
    let ids: number[] = []
    for (let t = 0; t < 2000; t += 100) {
      const report = engine.update(t, 50, poses, 16 / 9, 'CPU')
      expect(report.usablePeople).toBe(10)
      expect(report.tracks).toHaveLength(10)
      expect(report.events).toEqual([])
      if (t === 0) ids = report.tracks.map(track => track.id)
      else expect(report.tracks.map(track => track.id)).toEqual(ids)
    }
  })

  it('maps focused-area observations back onto the full camera image', () => {
    const poses = demoFrame(0, 'calm').poses
    const full = new DeviceAnalysis().update(0, 10, poses, 8 / 9, 'GPU')
    const focused = new DeviceAnalysis().update(0, 10, poses, 8 / 9, 'GPU', 'right')
    focused.tracks.forEach((track, i) => {
      expect(track.box[0]).toBeCloseTo(.5 + full.tracks[i].box[0] * .5)
      expect(track.box[2]).toBeCloseTo(.5 + full.tracks[i].box[2] * .5)
      expect(track.box[1]).toBeCloseTo(full.tracks[i].box[1])
    })
  })
  it('produces a single-hit review with observed regions; calm interactions stay quiet', () => {
    for (const scenario of ['conflict', 'calm'] as const) {
      const engine = new DeviceAnalysis()
      const events = new Set<string>()
      for (let t = 0; t <= 3000; t += 100) {
        const report = engine.update(t, 22, demoFrame(t, scenario).poses, 16 / 9, 'GPU')
        report.events.forEach(e => events.add(e.id))
        expect(report.model).toBe('nivra-browser-motion-v1')
        expect(report.tracks.length).toBeLessThanOrEqual(report.usablePeople)
      }
      expect(events.size).toBe(scenario === 'conflict' ? 1 : 0)
    }
  })

  it('does not invent evidence when pose visibility disappears', () => {
    const engine = new DeviceAnalysis()
    engine.update(0, 30, demoFrame(0, 'calm').poses, 16 / 9, 'CPU')
    const lost = engine.update(800, 30, [], 16 / 9, 'CPU')
    expect(lost.tracks).toEqual([])
    expect(lost.events).toEqual([])
    expect(lost.conflict.status).toBe('limited')
  })
})
