import { skeletonGeometry, type CameraPose } from './skeletonGeometry'

/** Shares object-fit:contain coordinates with the displayed camera image. */
export function Skeletons({ poses, sourceWidth, sourceHeight, width, height }: {
  poses?: CameraPose[]; sourceWidth: number; sourceHeight: number; width: number; height: number
}) {
  const skeletons = skeletonGeometry(poses, sourceWidth, sourceHeight, width, height)
  if (!skeletons.some(pose => pose.points.length)) return null
  return <svg className="nv-skeletons" data-testid="camera-skeletons" aria-hidden="true" viewBox={`0 0 ${width} ${height}`} style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', overflow: 'hidden', pointerEvents: 'none' }}>
    {skeletons.map(pose => <g key={pose.index} data-pose={pose.index}>
      {pose.lines.map(line => <line key={`${line.from}-${line.to}`} data-bone={`${line.from}-${line.to}`} x1={line.start.x} y1={line.start.y} x2={line.end.x} y2={line.end.y} stroke="#73ffb9" strokeWidth="2" strokeLinecap="round" vectorEffect="non-scaling-stroke" />)}
      {pose.points.map(point => <circle key={point.joint} data-joint={point.joint} cx={point.x} cy={point.y} r="2.6" fill="#f7fff9" stroke="#123b2a" strokeWidth="1" vectorEffect="non-scaling-stroke" />)}
    </g>)}
  </svg>
}
