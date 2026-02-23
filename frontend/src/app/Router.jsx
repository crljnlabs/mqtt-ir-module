import React from 'react'
import { createBrowserRouter } from 'react-router-dom'
import { AppShell } from './AppShell.jsx'
import { HomePage } from '../pages/HomePage.jsx'
import { RemotesPage } from '../pages/RemotesPage.jsx'
import { RemoteDetailPage } from '../pages/RemoteDetailPage.jsx'
import { SettingsPage } from '../pages/SettingsPage.jsx'
import { AgentsPage } from '../pages/AgentsPage.jsx'
import { AgentPage } from '../pages/AgentPage.jsx'
import { AgentLogsPage } from '../pages/AgentLogsPage.jsx'
import { NotFoundPage } from '../pages/NotFoundPage.jsx'

export function createAppRouter({ basename }) {
  return createBrowserRouter(
    [
      {
        path: '/',
        element: <AppShell />,
        children: [
          { index: true, element: <HomePage /> },
          { path: 'remotes', element: <RemotesPage /> },
          { path: 'remotes/:remoteId', element: <RemoteDetailPage /> },
          { path: 'agents', element: <AgentsPage /> },
          { path: 'agent/:agentId', element: <AgentPage /> },
          { path: 'agent/:agentId/logs', element: <AgentLogsPage /> },
          { path: 'settings', element: <SettingsPage /> },
          { path: '*', element: <NotFoundPage /> },
        ],
      },
    ],
    { basename },
  )
}
