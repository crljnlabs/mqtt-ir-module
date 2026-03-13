import React from 'react'
import Icon from '@mdi/react'
import { mdiImageEditOutline } from '@mdi/js'
import { useTranslation } from 'react-i18next'
import { TextField } from './TextField.jsx'
import { IconButton } from './IconButton.jsx'

// Shared header used by Remote, Agent, and Button editor drawers.
// Renders the entity-type label + icon-edit button on one row, with the name field below.
export function EntityEditHeader({ label, name, onNameChange, onIconClick }) {
  const { t } = useTranslation()

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <div className="text-sm font-semibold">{label}</div>
        <IconButton label={t('common.icon')} onClick={onIconClick}>
          <Icon path={mdiImageEditOutline} size={1} />
        </IconButton>
      </div>
      <TextField
        value={name}
        onChange={onNameChange}
        placeholder={label}
      />
    </div>
  )
}
