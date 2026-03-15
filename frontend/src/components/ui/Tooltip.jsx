import React, { useCallback, useId, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { cn } from './cn.js'

const VIEWPORT_PADDING = 8

const ARROW_SIDE = {
  top: 'bottom-[-4px]',
  bottom: 'top-[-4px]',
}

const ARROW_ALIGN = {
  center: 'left-1/2 -translate-x-1/2',
  start: 'left-3',
  end: 'right-3',
}

// Keep consumer handlers while still toggling tooltip state.
function mergeEventHandlers(userHandler, internalHandler) {
  return (event) => {
    if (typeof userHandler === 'function') {
      userHandler(event)
    }
    if (!event.defaultPrevented) {
      internalHandler(event)
    }
  }
}

export function Tooltip({ label, side = 'top', align = 'center', className, wrapperClassName, children }) {
  const [open, setOpen] = useState(false)
  const [style, setStyle] = useState(null)
  const [resolvedSide, setResolvedSide] = useState(side)
  const [resolvedAlign, setResolvedAlign] = useState(align)
  const tooltipId = useId()
  const wrapperRef = useRef(null)
  const tooltipRef = useRef(null)

  if (!label) {
    return children
  }

  const resolvePosition = useCallback(() => {
    const wrapper = wrapperRef.current
    const tooltip = tooltipRef.current
    if (!wrapper || !tooltip) return

    const triggerRect = wrapper.getBoundingClientRect()
    const tooltipRect = tooltip.getBoundingClientRect()
    const viewportWidth = window.innerWidth
    const viewportHeight = window.innerHeight

    const needVertical = tooltipRect.height + VIEWPORT_PADDING
    const spaceAbove = triggerRect.top
    const spaceBelow = viewportHeight - triggerRect.bottom

    let nextSide = side
    if (side === 'top' && spaceAbove < needVertical && spaceBelow >= needVertical) {
      nextSide = 'bottom'
    } else if (side === 'bottom' && spaceBelow < needVertical && spaceAbove >= needVertical) {
      nextSide = 'top'
    } else if (spaceAbove < needVertical && spaceBelow < needVertical) {
      nextSide = spaceAbove >= spaceBelow ? 'top' : 'bottom'
    }

    let nextAlign = align
    if (align === 'center') {
      const centerX = triggerRect.left + triggerRect.width / 2
      const halfWidth = tooltipRect.width / 2
      const fitsCenter =
        centerX - halfWidth >= VIEWPORT_PADDING &&
        centerX + halfWidth <= viewportWidth - VIEWPORT_PADDING
      const fitsStart = triggerRect.left + tooltipRect.width <= viewportWidth - VIEWPORT_PADDING
      const fitsEnd = triggerRect.right - tooltipRect.width >= VIEWPORT_PADDING

      if (!fitsCenter) {
        if (fitsStart) {
          nextAlign = 'start'
        } else if (fitsEnd) {
          nextAlign = 'end'
        }
      }
    }

    // Compute fixed pixel position so the tooltip renders above any overflow container.
    const top =
      nextSide === 'top'
        ? triggerRect.top - tooltipRect.height - 8
        : triggerRect.bottom + 8

    let left
    if (nextAlign === 'center') {
      left = triggerRect.left + triggerRect.width / 2 - tooltipRect.width / 2
    } else if (nextAlign === 'start') {
      left = triggerRect.left
    } else {
      left = triggerRect.right - tooltipRect.width
    }
    left = Math.max(VIEWPORT_PADDING, Math.min(left, viewportWidth - tooltipRect.width - VIEWPORT_PADDING))

    setResolvedSide((prev) => (prev === nextSide ? prev : nextSide))
    setResolvedAlign((prev) => (prev === nextAlign ? prev : nextAlign))
    setStyle({ position: 'fixed', top, left })
  }, [align, side])

  useLayoutEffect(() => {
    if (!open) {
      setResolvedSide(side)
      setResolvedAlign(align)
      setStyle(null)
      return
    }

    // Flip and align the tooltip so it stays within the viewport.
    resolvePosition()
    window.addEventListener('resize', resolvePosition)
    window.addEventListener('scroll', resolvePosition, true)
    return () => {
      window.removeEventListener('resize', resolvePosition)
      window.removeEventListener('scroll', resolvePosition, true)
    }
  }, [open, align, side, resolvePosition])

  const trigger = React.Children.only(children)
  // Preserve any existing aria-describedby while wiring the tooltip.
  const describedBy = [trigger.props['aria-describedby'], tooltipId].filter(Boolean).join(' ') || undefined

  const triggerProps = {
    'aria-describedby': describedBy,
    onMouseEnter: mergeEventHandlers(trigger.props.onMouseEnter, () => setOpen(true)),
    onMouseLeave: mergeEventHandlers(trigger.props.onMouseLeave, () => setOpen(false)),
    onFocus: mergeEventHandlers(trigger.props.onFocus, () => setOpen(true)),
    onBlur: mergeEventHandlers(trigger.props.onBlur, () => setOpen(false)),
    onKeyDown: mergeEventHandlers(trigger.props.onKeyDown, (event) => {
      if (event.key === 'Escape') setOpen(false)
    }),
  }

  // Render off-screen when not yet positioned so getBoundingClientRect returns
  // the correct dimensions for the initial placement calculation.
  const tooltipStyle = style ?? { position: 'fixed', top: -9999, left: -9999 }

  return (
    <span ref={wrapperRef} className={cn('relative inline-flex', wrapperClassName)}>
      {React.cloneElement(trigger, triggerProps)}
      {createPortal(
        <span
          role="tooltip"
          id={tooltipId}
          ref={tooltipRef}
          style={tooltipStyle}
          className={cn(
            'pointer-events-none z-[9999] w-max max-w-[min(20rem,calc(100vw-2rem))] rounded-xl border border-[rgb(var(--border))] bg-[rgb(var(--card))] px-3 py-2 text-center text-xs font-medium leading-snug text-[rgb(var(--fg))] shadow-[var(--shadow)] transition-opacity duration-150',
            open ? 'opacity-100' : 'opacity-0',
            className,
          )}
        >
          <span className="block whitespace-normal break-words">{label}</span>
          <span
            className={cn(
              'absolute h-2 w-2 rotate-45 border border-[rgb(var(--border))] bg-[rgb(var(--card))]',
              ARROW_SIDE[resolvedSide] || ARROW_SIDE.top,
              ARROW_ALIGN[resolvedAlign] || ARROW_ALIGN.center,
            )}
          />
        </span>,
        document.body,
      )}
    </span>
  )
}
