import React, { useState } from 'react'
import Icon from '@mdi/react'
import { useTranslation } from 'react-i18next'
import { Button } from '../../components/ui/Button.jsx'
import { IconButton } from '../../components/ui/IconButton.jsx'
import { findIconPath, DEFAULT_BUTTON_ICON } from '../../icons/iconRegistry.js'
import { mdiDotsHorizontal } from '@mdi/js'
import { ButtonEditorDrawer } from './ButtonEditorDrawer.jsx'
import { Tooltip } from '../../components/ui/Tooltip.jsx'

function SignalTypeBadge({ encoding, protocol }) {
  if (!encoding) return null
  if (encoding === 'protocol') {
    return (
      <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-[rgb(var(--primary))] text-[rgb(var(--primary-contrast))]">
        {protocol || 'Protocol'}
      </span>
    )
  }
  return (
    <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-[rgb(var(--border))] text-[rgb(var(--muted))]">
      Raw
    </span>
  )
}

export function ButtonTile({
  button,
  sendingDisabled,
  onSendPress,
  onSendHold,
  onSave,
  onDelete,
  onRelearn,
}) {
  const { t } = useTranslation()
  const [editorOpen, setEditorOpen] = useState(false)
  const iconKey = button.icon || DEFAULT_BUTTON_ICON

  return (
    <>
      <div className="rounded-2xl border border-[rgb(var(--border))] bg-[rgb(var(--card))] shadow-[var(--shadow)] p-4 flex flex-col gap-3">
        <div className="flex items-start justify-between gap-3">
          <div className="h-12 w-12 rounded-2xl border border-[rgb(var(--border))] bg-[rgb(var(--bg))] flex items-center justify-center">
            <Icon path={findIconPath(iconKey)} size={1.2} />
          </div>

          <IconButton label={t('common.menu')} onClick={() => setEditorOpen(true)}>
            <Icon path={mdiDotsHorizontal} size={1} />
          </IconButton>
        </div>

        <div className="min-w-0 flex items-center gap-2">
          <Tooltip label={button.name} wrapperClassName="min-w-0">
            <div className="font-semibold truncate">{button.name}</div>
          </Tooltip>
          <SignalTypeBadge encoding={button.encoding} protocol={button.protocol} />
        </div>

        <div className="mt-auto grid grid-cols-2 gap-2">
          <Button
            variant="secondary"
            disabled={sendingDisabled || !button.has_press}
            onClick={() => onSendPress(button)}
          >
            {t('button.sendPress')}
          </Button>
          <Button
            variant="secondary"
            disabled={sendingDisabled || !button.has_hold}
            onClick={() => onSendHold(button)}
          >
            {t('button.sendHold')}
          </Button>
        </div>
      </div>

      <ButtonEditorDrawer
        open={editorOpen}
        button={button}
        onClose={() => setEditorOpen(false)}
        onSave={onSave}
        onDelete={(b) => { setEditorOpen(false); onDelete(b) }}
        onRelearn={(b) => { setEditorOpen(false); onRelearn(b) }}
      />
    </>
  )
}
