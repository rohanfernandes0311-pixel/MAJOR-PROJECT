import { useEffect, useMemo, useRef } from 'react'

function onlyDigits(value) {
  return String(value || '').replace(/\D/g, '')
}

export default function OTPInput({ value, onChange, onComplete, disabled = false, autoFocus = true }) {
  const inputsRef = useRef([])
  const digits = useMemo(() => Array.from({ length: 6 }, (_, index) => value[index] || ''), [value])

  useEffect(() => {
    if (autoFocus && !disabled) {
      inputsRef.current[0]?.focus()
    }
  }, [autoFocus, disabled])

  function focusIndex(index) {
    inputsRef.current[index]?.focus()
    inputsRef.current[index]?.select?.()
  }

  function emit(nextDigits) {
    const otp = nextDigits.join('').slice(0, 6)
    onChange(otp)
    if (otp.length === 6 && nextDigits.every(Boolean)) {
      onComplete?.(otp)
    }
  }

  function handleChange(index, rawValue) {
    const current = [...digits]
    const sanitized = onlyDigits(rawValue).slice(-1)
    current[index] = sanitized
    emit(current)
    if (sanitized && index < 5) {
      focusIndex(index + 1)
    }
  }

  function handleKeyDown(index, event) {
    if (event.key === 'Backspace') {
      event.preventDefault()
      const current = [...digits]
      if (current[index]) {
        current[index] = ''
        emit(current)
        return
      }
      if (index > 0) {
        current[index - 1] = ''
        emit(current)
        focusIndex(index - 1)
      }
    }
  }

  function handlePaste(event) {
    event.preventDefault()
    const pasted = onlyDigits(event.clipboardData.getData('text')).slice(0, 6)
    if (!pasted) return
    const nextDigits = Array.from({ length: 6 }, (_, index) => pasted[index] || digits[index] || '')
    emit(nextDigits)
    const nextIndex = Math.min(pasted.length, 5)
    focusIndex(nextIndex)
  }

  return (
    <div className="flex justify-center gap-2 sm:gap-3" onPaste={handlePaste}>
      {digits.map((digit, index) => (
        <input
          key={index}
          ref={(node) => {
            inputsRef.current[index] = node
          }}
          value={digit}
          onChange={(event) => handleChange(index, event.target.value)}
          onKeyDown={(event) => handleKeyDown(index, event)}
          inputMode="numeric"
          autoComplete="one-time-code"
          maxLength={1}
          disabled={disabled}
          className="h-14 w-11 rounded-2xl border border-white/10 bg-[#0a1320] text-center text-xl font-semibold tracking-[0.3em] text-white outline-none transition focus:border-cyan-300/60 focus:bg-[#0d1727] disabled:cursor-not-allowed disabled:opacity-60 sm:h-16 sm:w-12"
          aria-label={`OTP digit ${index + 1}`}
        />
      ))}
    </div>
  )
}
