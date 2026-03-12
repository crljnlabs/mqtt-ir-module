import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'

const ToastContext = createContext(null)
const AUTO_DISMISS_MS = 3500

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])
  const timersRef = useRef(new Map())

  const clearTimer = useCallback((id) => {
    const timer = timersRef.current.get(id)
    if (!timer) return
    if (timer.timeoutId) {
      window.clearTimeout(timer.timeoutId)
    }
    timersRef.current.delete(id)
  }, [])

  const removeToast = useCallback(
    (id) => {
      setToasts((prev) => prev.filter((t) => t.id !== id))
      clearTimer(id)
    },
    [clearTimer],
  )

  const startTimer = useCallback(
    (id, duration) => {
      const existing = timersRef.current.get(id)
      if (existing?.timeoutId) {
        window.clearTimeout(existing.timeoutId)
      }

      const timeoutId = window.setTimeout(() => removeToast(id), duration)
      timersRef.current.set(id, { timeoutId, startedAt: Date.now(), remaining: duration })
    },
    [removeToast],
  )

  const pauseTimer = useCallback((id) => {
    const timer = timersRef.current.get(id)
    if (!timer || !timer.timeoutId) return

    window.clearTimeout(timer.timeoutId)
    const elapsed = Date.now() - timer.startedAt
    const remaining = Math.max(0, timer.remaining - elapsed)
    // Persist remaining time so the toast can resume after hover.
    timersRef.current.set(id, { timeoutId: null, startedAt: 0, remaining })
  }, [])

  const resumeTimer = useCallback(
    (id) => {
      const timer = timersRef.current.get(id)
      if (!timer || timer.timeoutId) return
      if (timer.remaining <= 0) {
        removeToast(id)
        return
      }
      // Resume with the stored remaining duration.
      startTimer(id, timer.remaining)
    },
    [removeToast, startTimer],
  )

  const show = useCallback((toast) => {
    const id = `${Date.now()}_${Math.random().toString(16).slice(2)}`
    const item = { id, title: toast.title || '', message: toast.message || '' }
    setToasts((prev) => [...prev, item])
    startTimer(id, AUTO_DISMISS_MS)
  }, [startTimer])

  useEffect(() => {
    return () => {
      timersRef.current.forEach((timer) => {
        if (timer.timeoutId) window.clearTimeout(timer.timeoutId)
      })
      timersRef.current.clear()
    }
  }, [])

  const value = useMemo(() => ({ show }), [show])

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="fixed top-4 right-4 z-[60] space-y-2">
        {toasts.map((t) => (
          <div
            key={t.id}
            className="relative w-[320px] rounded-2xl border border-[rgb(var(--border))] bg-[rgb(var(--card))] shadow-[var(--shadow)] p-3 pr-9"
            onMouseEnter={() => pauseTimer(t.id)}
            onMouseLeave={() => resumeTimer(t.id)}
          >
            <button
              onClick={() => removeToast(t.id)}
              className="absolute top-2 right-2 w-6 h-6 rounded-full flex items-center justify-center bg-[rgb(var(--muted))/20] hover:bg-[rgb(var(--muted))/40] text-[rgb(var(--muted))] transition-colors"
              aria-label="Dismiss"
            >
              ✕
            </button>
            {t.title ? <div className="font-semibold text-sm">{t.title}</div> : null}
            <div className="text-xs text-[rgb(var(--muted))]">{t.message}</div>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast() {
  const ctx = useContext(ToastContext)
  if (!ctx) {
    throw new Error('useToast must be used within ToastProvider')
  }
  return ctx
}
