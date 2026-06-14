import React from 'react'
import { cn } from './cn.js'

export function Badge({ variant = 'neutral', className, ...props }) {
  const variants = {
    neutral: 'bg-[rgb(var(--bg))] text-[rgb(var(--muted))] border border-[rgb(var(--border))]',
    success: 'bg-[rgb(var(--success))] text-white',
    warning: 'bg-[rgb(var(--warning))] text-black',
    danger: 'bg-[rgb(var(--danger))] text-white',
    primary: 'bg-[rgb(var(--primary))] text-[rgb(var(--primary-contrast))]',
  }

  return <span className={cn('inline-flex items-center rounded-full px-2 py-1 text-[11px] font-semibold', variants[variant], className)} {...props} />
}