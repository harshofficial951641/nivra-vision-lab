/** The supplied NIVRA tower mark, shared by every staff-facing screen. */
export function Brand({ compact = false }: { compact?: boolean }) {
  return <span className={`nv-identity${compact ? ' nv-identity--compact' : ''}`}>
    <img src="/brand/nivra-mark.png" width="40" height="40" alt="" />
    {!compact && <span>NIVRA</span>}
  </span>
}
