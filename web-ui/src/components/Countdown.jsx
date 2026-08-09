export default function Countdown({ seconds }) {
  const safeSeconds = Math.max(0, Number(seconds) || 0)
  const minutes = String(Math.floor(safeSeconds / 60)).padStart(2, '0')
  const remainder = String(safeSeconds % 60).padStart(2, '0')

  return (
    <span className="font-semibold text-cyan-200">
      {minutes}:{remainder}
    </span>
  )
}
