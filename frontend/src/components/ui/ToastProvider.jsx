import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'

const ToastContext = createContext(null)
const AUTO_DISMISS_MS = 3500

// Spring-like easing that slightly overshoots — mimics native notification feel
const SPRING = 'cubic-bezier(0.34, 1.56, 0.64, 1)'

function ToastItem({ t, removeToast, pauseTimer, resumeTimer }) {
  const touchStartRef = useRef(null)
  const [swipeOffset, setSwipeOffset] = useState(0)
  // Start invisible/above; after first paint flip to true to trigger the slide-in
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    // Double rAF ensures the "from" state is painted before transitioning
    const raf = requestAnimationFrame(() => requestAnimationFrame(() => setVisible(true)))
    return () => cancelAnimationFrame(raf)
  }, [])

  const handleTouchStart = (e) => {
    touchStartRef.current = { y: e.touches[0].clientY }
    pauseTimer(t.id)
  }

  const handleTouchMove = (e) => {
    if (!touchStartRef.current) return
    const deltaY = e.touches[0].clientY - touchStartRef.current.y
    // Only allow upward swipe
    if (deltaY < 0) {
      e.preventDefault()
      setSwipeOffset(deltaY)
    }
  }

  const handleTouchEnd = (e) => {
    if (!touchStartRef.current) return
    const deltaY = e.changedTouches[0].clientY - touchStartRef.current.y
    touchStartRef.current = null

    if (deltaY < -60) {
      removeToast(t.id)
    } else {
      setSwipeOffset(0)
      resumeTimer(t.id)
    }
  }

  const isSwiping = swipeOffset !== 0
  // Slide-in from above when mounting; follow finger during swipe
  const translateY = visible ? swipeOffset : -32
  // Fade out as user swipes up; invisible before enter animation
  const opacity = !visible ? 0 : swipeOffset < 0 ? Math.max(0, 1 + swipeOffset / 120) : 1
  // Spring on enter/snap-back; no transition while finger is dragging
  const transition = isSwiping ? 'none' : `transform 0.35s ${SPRING}, opacity 0.25s ease`

  return (
    <>
      {/* Mobile: native notification style */}
      <div
        className="sm:hidden"
        style={{ transform: `translateY(${translateY}px)`, opacity, transition }}
        onTouchStart={handleTouchStart}
        onTouchMove={handleTouchMove}
        onTouchEnd={handleTouchEnd}
      >
        <div className="rounded-2xl border border-[rgb(var(--border))] bg-[rgb(var(--card))] shadow-(--shadow) overflow-hidden">
          {/* Drag handle */}
          <div className="flex justify-center pt-2 pb-1">
            <div className="w-8 h-1 rounded-full bg-[rgb(var(--muted))/40]" />
          </div>
          <div className="px-4 pb-4 pt-1">
            {t.title ? (
              <div className="font-semibold text-sm mb-0.5">{t.title}</div>
            ) : null}
            <div className="text-xs text-[rgb(var(--muted))]">{t.message}</div>
          </div>
        </div>
      </div>

      {/* Desktop: existing style with X button */}
      <div
        className="hidden sm:block relative w-[320px] rounded-2xl border border-[rgb(var(--border))] bg-[rgb(var(--card))] shadow-(--shadow) p-3 pr-9"
        style={{ transform: `translateY(${translateY}px)`, opacity, transition }}
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
    </>
  )
}

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])
  const timersRef = useRef(new Map())

  const clearTimer = useCallback((id) => {
    const timer = timersRef.current.get(id)
    if (!timer) return
    if (timer.timeoutId) window.clearTimeout(timer.timeoutId)
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
      if (existing?.timeoutId) window.clearTimeout(existing.timeoutId)
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
      startTimer(id, timer.remaining)
    },
    [removeToast, startTimer],
  )

  const show = useCallback(
    (toast) => {
      const id = `${Date.now()}_${Math.random().toString(16).slice(2)}`
      const item = { id, title: toast.title || '', message: toast.message || '' }

      // Replace any existing toast (max 1 visible at a time)
      setToasts((prev) => {
        prev.forEach((t) => clearTimer(t.id))
        return [item]
      })
      startTimer(id, AUTO_DISMISS_MS)
    },
    [startTimer, clearTimer],
  )

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
      {/* Container: full-width top-center on mobile, fixed right on desktop */}
      <div className="fixed top-4 left-4 right-4 sm:left-auto sm:right-4 sm:w-[320px] z-60 space-y-2">
        {toasts.map((t) => (
          <ToastItem
            key={t.id}
            t={t}
            removeToast={removeToast}
            pauseTimer={pauseTimer}
            resumeTimer={resumeTimer}
          />
        ))}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast() {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error('useToast must be used within ToastProvider')
  return ctx
}
