import React, { useMemo } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import Icon from '@mdi/react'
import { mdiHomeOutline, mdiRemoteTv, mdiCogOutline, mdiAccountGroupOutline } from '@mdi/js'
import { getAppConfig } from '../../utils/appConfig.js'

function isActive(pathname, to) {
  if (to === '/') return pathname === '/'
  if (to === '/remotes') return pathname.startsWith('/remotes') || pathname.startsWith('/marketplace')
  if (to === '/agents') return pathname === '/agents' || pathname.startsWith('/agent/')
  if (to === '/settings') return pathname.startsWith('/settings')
  return pathname === to
}

// When on /logs, resolve the parent nav item from navigation state
function logsParentNav(locationState) {
  const from = locationState?.from || ''
  if (from === '/agents' || from.startsWith('/agent/')) return '/agents'
  return '/settings'
}

function Item({ to, icon, label, active }) {
  return (
    <NavLink
      to={to}
      className={() =>
        [
          'flex items-center gap-3 rounded-xl px-3 py-2 text-sm font-semibold cursor-pointer transition-colors',
          active ? 'bg-[rgb(var(--bg))] border border-[rgb(var(--border))]' : 'hover:bg-[rgb(var(--bg))]',
        ].join(' ')
      }
    >
      <Icon path={icon} size={1} />
      <span>{label}</span>
    </NavLink>
  )
}

export function SidebarNav() {
  const { t } = useTranslation()
  const location = useLocation()

  const onLogs = location.pathname === '/logs'
  const logsParent = onLogs ? logsParentNav(location.state) : null
  const active = (to) => logsParent ? logsParent === to : isActive(location.pathname, to)

  const appIconSrc = useMemo(() => {
    const { publicBaseUrl } = getAppConfig()
    return `${publicBaseUrl}logos/app-icon-1024.png`
  }, [])

  return (
    <aside className="hidden md:flex fixed left-0 top-0 bottom-0 w-64 border-r border-[rgb(var(--border))] bg-[rgb(var(--card))] p-4">
      <div className="w-full flex flex-col gap-3">
        <div className="px-2 flex items-center gap-2">
          <img
            src={appIconSrc}
            alt=""
            aria-hidden="true"
            className="h-10 w-10 shrink-0"
          />
          <div className="font-bold text-xl">{t('app.name')}</div>
        </div>

        <nav className="flex flex-col gap-2">
          <Item to="/" icon={mdiHomeOutline} label={t('nav.home')} active={active('/')} />
          <Item to="/remotes" icon={mdiRemoteTv} label={t('nav.remotes')} active={active('/remotes')} />
          <Item to="/agents" icon={mdiAccountGroupOutline} label={t('nav.agents')} active={active('/agents')} />
          <Item to="/settings" icon={mdiCogOutline} label={t('nav.settings')} active={active('/settings')} />
        </nav>
      </div>
    </aside>
  )
}
