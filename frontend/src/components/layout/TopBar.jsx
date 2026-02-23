import React, { useMemo } from 'react'
import { useLocation } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { ThemeToggle } from '../pickers/ThemeToggle.jsx'
import { LanguagePicker } from '../pickers/LanguagePicker.jsx'
import { getAppConfig } from '../../utils/appConfig.js'

function getTitle(pathname, t) {
  if (pathname === '/' || pathname === '') return t('nav.home')
  if (pathname.startsWith('/remotes')) return t('nav.remotes')
  if (pathname === '/agents') return t('nav.agents')
  if (pathname.startsWith('/agent/')) return t('agents.pageTitle')
  if (pathname.startsWith('/settings')) return t('nav.settings')
  return t('app.name')
}

export function TopBar() {
  const { t } = useTranslation()
  const location = useLocation()

  const appIconSrc = useMemo(() => {
    const { publicBaseUrl } = getAppConfig()
    return `${publicBaseUrl}logos/app-icon-1024.png`
  }, [])

  return (
    <div className="sticky top-0 z-30 border-b border-[rgb(var(--border))] bg-[rgb(var(--card))]">
      <div className="h-14 px-4 md:px-6 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 min-w-0">
          <img
            src={appIconSrc}
            alt=""
            aria-hidden="true"
            className="h-10 w-10 shrink-0 md:hidden"
          />
          <div className="font-semibold text-xl truncate md:hidden">{t('app.name')}</div>
          <div className="font-semibold truncate md:block hidden">{getTitle(location.pathname, t)}</div>
        </div>

        <div className="flex items-center gap-2">
          <ThemeToggle />
          <LanguagePicker />
        </div>
      </div>
    </div>
  )
}
