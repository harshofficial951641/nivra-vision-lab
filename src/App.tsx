import { lazy, Suspense } from 'react'
import AccessGate from './classroom/AccessGate'
const VisionLab = lazy(() => import('./VisionLab'))
const Dashboard = lazy(() => import('./classroom/Dashboard'))
const Publisher = lazy(() => import('./classroom/Publisher'))
const FightDemo = lazy(() => import('./FightDemo'))
export default function App() {
  const route = window.location.pathname
  return (
    <Suspense fallback={<p role="status">Opening Nivra…</p>}>
      {route === '/fight' ? (
        <FightDemo />
      ) : route === '/lab' ? (
        <VisionLab />
      ) : route === '/camera' ? (
        <Publisher />
      ) : (
        <AccessGate><Dashboard /></AccessGate>
      )}
    </Suspense>
  )
}
