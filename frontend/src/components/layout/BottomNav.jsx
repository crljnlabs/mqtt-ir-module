import React from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import Icon from '@mdi/react'
import { mdiHomeOutline, mdiRemoteTv, mdiCogOutline, mdiAccountGroupOutline } from '@mdi/js'

function isActive(pathname, to) {
  if (to === '/') return pathname === '/'
  if (to === '/remotes') return pathname.startsWith('/remotes') || pathname.startsWith('/marketplace')
  if (to === '/agents') return pathname === '/agents' || pathname.startsWith('/agent/')
  if (to === '/settings') return pathname.startsWith('/settings')
  return pathname === to
}

function logsParentNav(locationState) {
  const from = locationState?.from || ''
  if (from === '/agents' || from.startsWith('/agent/')) return '/agents'
  return '/settings'
}

function Tab({ to, icon, label, active }) {
  return (
    <NavLink
      to={to}
      className={() =>
        [
          'flex flex-col items-center justify-center gap-1 flex-1 h-16 cursor-pointer transition-colors hover:bg-[rgb(var(--bg))]',
          active ? 'text-[rgb(var(--primary))]' : 'text-[rgb(var(--muted))]',
        ].join(' ')
      }
    >
      <Icon path={icon} size={1} />
      <span className="text-[11px] font-semibold">{label}</span>
    </NavLink>
  )
}

export function BottomNav() {
  const { t } = useTranslation()
  const location = useLocation()

  const onLogs = location.pathname === '/logs'
  const logsParent = onLogs ? logsParentNav(location.state) : null
  const active = (to) => logsParent ? logsParent === to : isActive(location.pathname, to)

  return (
    <div className="md:hidden fixed bottom-0 inset-x-0 z-40 border-t border-[rgb(var(--border))] bg-[rgb(var(--card))]">
      <div className="flex">
        <Tab to="/" icon={mdiHomeOutline} label={t('nav.home')} active={active('/')} />
        <Tab to="/remotes" icon={mdiRemoteTv} label={t('nav.remotes')} active={active('/remotes')} />
        <Tab to="/agents" icon={mdiAccountGroupOutline} label={t('nav.agents')} active={active('/agents')} />
        <Tab to="/settings" icon={mdiCogOutline} label={t('nav.settings')} active={active('/settings')} />
      </div>
    </div>
  )
}
