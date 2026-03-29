import { useRef, useState } from 'react'
import Icon from '@mdi/react'
import { mdiClose, mdiEye, mdiEyeOff } from '@mdi/js'
import { cn } from './cn.js'

export function TextField({ label, hint, className, onClear, clearLabel, showToggle, type, ...props }) {
  const inputRef = useRef(null)
  const [passwordVisible, setPasswordVisible] = useState(false)

  const stringValue =
    typeof props.value === 'string' ? props.value : typeof props.value === 'number' ? String(props.value) : ''
  const hasClearAction = Boolean(onClear) && Boolean(clearLabel)
  const isPasswordField = showToggle && type === 'password'
  // Only show the clear action when the field is editable and has content (not on password toggle fields).
  const canClear = hasClearAction && !isPasswordField && stringValue.trim().length > 0 && !props.disabled && !props.readOnly
  // Reserve space for the right-side button to avoid text jumping when it appears.
  const inputPadding = hasClearAction || isPasswordField ? 'pl-3 pr-12' : 'px-3'
  const resolvedType = isPasswordField ? (passwordVisible ? 'text' : 'password') : type

  const handleClear = () => {
    onClear?.()
    inputRef.current?.focus()
  }

  return (
    <label className={cn('block', className)}>
      {label ? <div className="mb-1 text-sm font-medium">{label}</div> : null}
      <div className="relative">
        <input
          ref={inputRef}
          type={resolvedType}
          className={cn(
            'h-11 w-full rounded-xl border border-[rgb(var(--border))] bg-[rgb(var(--bg))] text-sm text-[rgb(var(--fg))] outline-none focus:ring-2 focus:ring-[rgb(var(--primary))]',
            inputPadding,
          )}
          {...props}
        />
        {isPasswordField ? (
          <button
            type="button"
            onClick={() => setPasswordVisible((v) => !v)}
            aria-label={passwordVisible ? 'Hide password' : 'Show password'}
            className="absolute right-3 top-1/2 -translate-y-1/2 rounded-md p-1 text-[rgb(var(--muted))] hover:text-[rgb(var(--fg))] focus:outline-none focus:ring-2 focus:ring-[rgb(var(--primary))] focus:ring-offset-2 focus:ring-offset-[rgb(var(--bg))]"
          >
            <Icon path={passwordVisible ? mdiEyeOff : mdiEye} size={0.75} aria-hidden="true" />
          </button>
        ) : canClear ? (
          <button
            type="button"
            onClick={handleClear}
            aria-label={clearLabel}
            className="absolute right-3 top-1/2 -translate-y-1/2 rounded-md p-1 text-[rgb(var(--muted))] hover:text-[rgb(var(--fg))] focus:outline-none focus:ring-2 focus:ring-[rgb(var(--primary))] focus:ring-offset-2 focus:ring-offset-[rgb(var(--bg))]"
          >
            <Icon path={mdiClose} size={0.75} aria-hidden="true" />
          </button>
        ) : null}
      </div>
      {hint ? <div className="mt-1 text-xs text-[rgb(var(--muted))]">{hint}</div> : null}
    </label>
  )
}
