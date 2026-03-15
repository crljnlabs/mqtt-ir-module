import React, { useEffect, useRef } from 'react'
import { createPortal } from 'react-dom'
import Icon from '@mdi/react'
import { mdiChevronLeft } from '@mdi/js'
import { cn } from './cn.js'

const TEXTBOX_TYPES = new Set(['text', 'search', 'email', 'url', 'tel', 'password', 'number'])
// Find the first enabled text-like control so overlays can auto-focus on open.
function findPrimaryTextbox(container) {
  if (!container) return null
  const candidates = Array.from(container.querySelectorAll('input, textarea, [contenteditable="true"]'))
  return candidates.find((element) => {
    if (element.hasAttribute('disabled') || element.getAttribute('aria-disabled') === 'true') return false
    if (element.hasAttribute('readonly')) return false
    if (element.tabIndex < 0) return false
    if (element.tagName === 'INPUT') {
      const type = (element.getAttribute('type') || 'text').toLowerCase()
      return TEXTBOX_TYPES.has(type)
    }
    return true
  })
}

export function Drawer({ open, title, children, footer, onClose, onBack, closeOnEscape = true }) {
  const panelRef = useRef(null)

  useEffect(() => {
    if (!open || !closeOnEscape) return
    const handler = (e) => {
      if (e.key === 'Escape') onClose?.()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [open, onClose, closeOnEscape])

  useEffect(() => {
    if (!open) return
    if (!panelRef.current) return
    if (panelRef.current.contains(document.activeElement)) return
    // Focus the primary textbox when the drawer opens so input flows are consistent.
    findPrimaryTextbox(panelRef.current)?.focus()
  }, [open])

  if (!open) return null

  return createPortal(
    <div className="fixed inset-0 z-50">
      <div className="absolute inset-0 bg-black/50 cursor-pointer" onClick={() => onClose?.()} />
      <div className="absolute inset-x-0 bottom-0 md:inset-y-0 md:right-0 md:left-auto flex md:items-stretch items-end">
        <div
          className={cn('w-full md:w-[420px] max-h-[90dvh] md:max-h-none rounded-t-2xl md:rounded-none md:rounded-l-2xl border border-[rgb(var(--border))] bg-[rgb(var(--card))] shadow-[var(--shadow)] flex flex-col')}
          ref={panelRef}
        >
          {title ? (
            <div className="px-4 py-3 border-b border-[rgb(var(--border))] flex items-center gap-2">
              {onBack ? (
                <button
                  type="button"
                  aria-label="Back"
                  onClick={onBack}
                  className="inline-flex h-7 w-7 items-center justify-center rounded-lg text-[rgb(var(--muted))] hover:text-[rgb(var(--fg))] transition cursor-pointer flex-shrink-0"
                >
                  <Icon path={mdiChevronLeft} size={1} />
                </button>
              ) : null}
              <span className="font-semibold">{title}</span>
            </div>
          ) : null}
          <div className="p-4 overflow-auto">{children}</div>
          {footer ? <div className="px-4 py-3 border-t border-[rgb(var(--border))]">{footer}</div> : null}
        </div>
      </div>
    </div>,
    document.body,
  )
}
