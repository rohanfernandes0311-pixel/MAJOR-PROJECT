import { Loader2 } from 'lucide-react'

export default function VerifyButton({ loading, disabled, children, className = '' }) {
  return (
    <button
      type="submit"
      disabled={disabled || loading}
      className={`inline-flex items-center justify-center gap-2 rounded-2xl px-5 py-3 text-sm font-semibold transition disabled:cursor-not-allowed disabled:opacity-50 ${className}`}
    >
      {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
      <span>{children}</span>
    </button>
  )
}
