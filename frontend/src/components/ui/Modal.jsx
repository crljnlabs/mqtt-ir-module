import React, { useEffect, useRef } from 'react'
import { createPortal } from 'react-dom'
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

export function Modal({ open, title, children, footer, onClose, onConfirm }) {
  const panelRef = useRef(null)

  useEffect(() => {
    if (!open) return
    const handler = (e) => {
      if (e.key === 'Escape') onClose?.()
      if (e.key === 'Enter') {
        // Submit on Enter only when focus is inside a text-like input, not a button.
        const tag = document.activeElement?.tagName?.toLowerCase()
        if (tag === 'input' || tag === 'textarea') onConfirm?.()
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [open, onClose, onConfirm])

  useEffect(() => {
    if (!open) return
    if (!panelRef.current) return
    if (panelRef.current.contains(document.activeElement)) return
    // Focus the primary textbox when the modal opens so single-input dialogs are ready.
    findPrimaryTextbox(panelRef.current)?.focus()
  }, [open])

  if (!open) return null

  return createPortal(
    <div className="fixed inset-0 z-50">
      <div className="absolute inset-0 bg-black/50" />
      <div
        className="absolute inset-0 flex items-center justify-center p-4 cursor-pointer"
        onClick={() => onClose?.()}
        role="presentation"
      >
        {/* Close on backdrop clicks while keeping modal interactions intact. */}
        <div
          className={cn(
            'w-full max-w-lg rounded-2xl border border-[rgb(var(--border))] bg-[rgb(var(--card))] shadow-[var(--shadow)] cursor-default',
          )}
          onClick={(e) => e.stopPropagation()}
          ref={panelRef}
        >
          {title ? <div className="px-4 py-3 border-b border-[rgb(var(--border))] font-semibold">{title}</div> : null}
          <div className="p-4">{children}</div>
          {footer ? <div className="px-4 py-3 border-t border-[rgb(var(--border))]">{footer}</div> : null}
        </div>
      </div>
    </div>,
    document.body,
  )
}
