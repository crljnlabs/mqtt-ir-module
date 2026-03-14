import React, { useEffect, useId, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { cn } from './cn.js'

const LISTBOX_GAP = 4
const LISTBOX_MAX_HEIGHT = 224
const LISTBOX_MIN_HEIGHT = 96
const VIEWPORT_PADDING = 8

export function SelectField({
  label,
  hint,
  className,
  children,
  value,
  onChange,
  disabled = false,
  name,
  id,
  searchable = false,
  searchPlaceholder = 'Search…',
  ...props
}) {
  const generatedId = useId()
  const selectId = id || `select-${generatedId}`
  const listboxId = `${selectId}-listbox`
  const rootRef = useRef(null)
  const buttonRef = useRef(null)
  const listboxRef = useRef(null)
  const searchInputRef = useRef(null)
  const [open, setOpen] = useState(false)
  const [listboxPosition, setListboxPosition] = useState(null)
  const [searchQuery, setSearchQuery] = useState('')

  const options = useMemo(() => collectOptions(children), [children])
  const selectedValue = value == null ? '' : String(value)
  const selectedOption = options.find((option) => option.value === selectedValue) || options[0] || null
  const selectedLabel = selectedOption ? selectedOption.label : ''
  const isOpen = open && !disabled

  const filteredOptions = useMemo(() => {
    if (!searchable || !searchQuery) return options
    const lower = searchQuery.toLowerCase()
    return options.filter((o) => o.label.toLowerCase().includes(lower))
  }, [options, searchable, searchQuery])

  useEffect(() => {
    if (!isOpen) setSearchQuery('')
  }, [isOpen])

  useEffect(() => {
    if (isOpen && searchable && listboxPosition) {
      searchInputRef.current?.focus()
    }
  }, [isOpen, searchable, listboxPosition])

  useEffect(() => {
    if (!isOpen) return
    const handlePointerDown = (event) => {
      const target = event.target
      if (rootRef.current?.contains(target)) return
      if (listboxRef.current?.contains(target)) return
      setOpen(false)
    }
    const handleEscape = (event) => {
      if (event.key !== 'Escape') return
      setOpen(false)
      buttonRef.current?.focus()
    }
    window.addEventListener('pointerdown', handlePointerDown)
    window.addEventListener('keydown', handleEscape)
    return () => {
      window.removeEventListener('pointerdown', handlePointerDown)
      window.removeEventListener('keydown', handleEscape)
    }
  }, [isOpen])

  useEffect(() => {
    if (!isOpen) return

    const updateListboxPosition = () => {
      if (!buttonRef.current) return
      const nextPosition = calculateListboxPosition(buttonRef.current.getBoundingClientRect())
      setListboxPosition((current) => {
        if (
          current
          && current.top === nextPosition.top
          && current.left === nextPosition.left
          && current.width === nextPosition.width
          && current.maxHeight === nextPosition.maxHeight
        ) {
          return current
        }
        return nextPosition
      })
    }

    updateListboxPosition()
    window.addEventListener('resize', updateListboxPosition)
    window.addEventListener('scroll', updateListboxPosition, true)
    return () => {
      window.removeEventListener('resize', updateListboxPosition)
      window.removeEventListener('scroll', updateListboxPosition, true)
    }
  }, [isOpen, options.length])

  const handleButtonClick = () => {
    if (disabled || options.length === 0) return
    setOpen((prev) => !prev)
  }

  const handleButtonKeyDown = (event) => {
    if (disabled || options.length === 0) return
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp' || event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      setOpen(true)
    }
  }

  const emitChange = (nextValue) => {
    onChange?.({
      target: { value: nextValue, name },
      currentTarget: { value: nextValue, name },
    })
  }

  const selectOption = (option) => {
    if (option.disabled) return
    emitChange(option.value)
    setOpen(false)
    buttonRef.current?.focus()
  }

  return (
    <label className={cn('block', className)} ref={rootRef}>
      {label ? <div className="mb-1 text-sm font-medium" id={`${selectId}-label`}>{label}</div> : null}
      <div className="relative">
        <button
          id={selectId}
          ref={buttonRef}
          type="button"
          role="combobox"
          aria-haspopup="listbox"
          aria-controls={listboxId}
          aria-expanded={isOpen}
          aria-labelledby={label ? `${selectId}-label ${selectId}` : undefined}
          disabled={disabled}
          className={cn(
            'h-11 w-full rounded-xl border border-[rgb(var(--border))] bg-[rgb(var(--bg))] px-3 pr-10 text-left text-sm text-[rgb(var(--fg))] outline-none focus:ring-2 focus:ring-[rgb(var(--primary))] disabled:cursor-not-allowed disabled:opacity-70',
            isOpen ? 'ring-2 ring-[rgb(var(--primary))]' : '',
          )}
          onClick={handleButtonClick}
          onKeyDown={handleButtonKeyDown}
          {...props}
        >
          <span className="truncate">{selectedLabel}</span>
        </button>
        {name ? <input type="hidden" name={name} value={selectedValue} /> : null}
        <svg
          className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[rgb(var(--muted))]"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.75"
          aria-hidden="true"
        >
          <path d="M6 9l6 6 6-6" />
        </svg>
      </div>
      {isOpen && listboxPosition && typeof document !== 'undefined'
        ? createPortal(
          <ul
            id={listboxId}
            ref={listboxRef}
            role="listbox"
            aria-labelledby={label ? `${selectId}-label` : undefined}
            className="fixed z-[70] overflow-auto rounded-xl border border-[rgb(var(--border))] bg-[rgb(var(--card))] p-1 shadow-[var(--shadow)]"
            style={{
              top: `${listboxPosition.top}px`,
              left: `${listboxPosition.left}px`,
              width: `${listboxPosition.width}px`,
              maxHeight: `${listboxPosition.maxHeight}px`,
            }}
          >
            {searchable && (
              <li role="presentation" className="sticky top-0 pb-1 mb-1 border-b border-[rgb(var(--border))] bg-[rgb(var(--card))]">
                <input
                  ref={searchInputRef}
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder={searchPlaceholder}
                  className="w-full rounded-lg px-3 py-1.5 text-sm outline-none bg-[rgb(var(--bg))] text-[rgb(var(--fg))] placeholder:text-[rgb(var(--muted))]"
                />
              </li>
            )}
            {filteredOptions.map((option, index) => {
              const isSelected = option.value === selectedValue
              return (
                <li key={`${option.value}-${index}`} role="presentation">
                  <button
                    type="button"
                    role="option"
                    aria-selected={isSelected}
                    disabled={option.disabled}
                    className={cn(
                      'w-full rounded-lg px-3 py-2 text-left text-sm',
                      option.disabled ? 'cursor-not-allowed text-[rgb(var(--muted))] opacity-70' : 'cursor-pointer',
                      isSelected
                        ? 'bg-[rgb(var(--primary))] text-[rgb(var(--primary-contrast))]'
                        : 'text-[rgb(var(--fg))] hover:bg-[rgb(var(--bg))]',
                    )}
                    onClick={() => selectOption(option)}
                  >
                    {option.label}
                  </button>
                </li>
              )
            })}
          </ul>,
          document.body,
        )
        : null}
      {hint ? <div className="mt-1 text-xs text-[rgb(var(--muted))]">{hint}</div> : null}
    </label>
  )
}

function calculateListboxPosition(buttonRect) {
  const viewportHeight = window.innerHeight
  const viewportWidth = window.innerWidth
  const spaceAbove = buttonRect.top - VIEWPORT_PADDING
  const spaceBelow = viewportHeight - buttonRect.bottom - VIEWPORT_PADDING
  const openUpwards = spaceBelow < 140 && spaceAbove > spaceBelow
  const availableSpace = openUpwards ? spaceAbove : spaceBelow
  const maxHeight = clamp(availableSpace, LISTBOX_MIN_HEIGHT, LISTBOX_MAX_HEIGHT)

  const unclampedTop = openUpwards
    ? buttonRect.top - maxHeight - LISTBOX_GAP
    : buttonRect.bottom + LISTBOX_GAP
  const top = clamp(unclampedTop, VIEWPORT_PADDING, viewportHeight - VIEWPORT_PADDING - maxHeight)
  const left = clamp(buttonRect.left, VIEWPORT_PADDING, viewportWidth - VIEWPORT_PADDING - buttonRect.width)

  return {
    top: Math.round(top),
    left: Math.round(left),
    width: Math.round(buttonRect.width),
    maxHeight: Math.round(maxHeight),
  }
}

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max)
}

function collectOptions(children) {
  const options = []
  React.Children.forEach(children, (child) => {
    if (!React.isValidElement(child)) return
    if (child.type === React.Fragment) {
      options.push(...collectOptions(child.props.children))
      return
    }
    if (child.type !== 'option') return
    options.push({
      value: child.props.value == null ? '' : String(child.props.value),
      label: flattenOptionLabel(child.props.children),
      disabled: Boolean(child.props.disabled),
    })
  })
  return options
}

function flattenOptionLabel(value) {
  if (value == null || typeof value === 'boolean') return ''
  if (typeof value === 'string' || typeof value === 'number') return String(value)
  if (Array.isArray(value)) return value.map((item) => flattenOptionLabel(item)).join('')
  if (React.isValidElement(value)) return flattenOptionLabel(value.props.children)
  return ''
}
