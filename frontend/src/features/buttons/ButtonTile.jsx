import React, { useState } from 'react'
import Icon from '@mdi/react'
import { useTranslation } from 'react-i18next'
import { Button } from '../../components/ui/Button.jsx'
import { IconButton } from '../../components/ui/IconButton.jsx'
import { findIconPath, DEFAULT_BUTTON_ICON } from '../../icons/iconRegistry.js'
import { mdiDotsHorizontal, mdiPencilOutline, mdiImageEditOutline, mdiTrashCanOutline, mdiRepeat } from '@mdi/js'
import { Drawer } from '../../components/ui/Drawer.jsx'

export function ButtonTile({
  button,
  sendingDisabled,
  onSendPress,
  onSendHold,
  onRename,
  onChangeIcon,
  onDelete,
  onRelearn,
}) {
  const { t } = useTranslation()
  const [menuOpen, setMenuOpen] = useState(false)
  const iconKey = button.icon || DEFAULT_BUTTON_ICON

  return (
    <>
      <div className="rounded-2xl border border-[rgb(var(--border))] bg-[rgb(var(--card))] shadow-[var(--shadow)] p-4 flex flex-col gap-3">
        <div className="flex items-start justify-between gap-3">
          <div className="h-12 w-12 rounded-2xl border border-[rgb(var(--border))] bg-[rgb(var(--bg))] flex items-center justify-center">
            <Icon path={findIconPath(iconKey)} size={1.2} />
          </div>

          <IconButton label={t('common.menu')} onClick={() => setMenuOpen(true)}>
            <Icon path={mdiDotsHorizontal} size={1} />
          </IconButton>
        </div>

        <div className="min-w-0">
          <div className="font-semibold truncate">{button.name}</div>
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

      <Drawer
        open={menuOpen}
        title={button.name}
        onClose={() => setMenuOpen(false)}
      >
        <div className="space-y-2">
          <Button variant="secondary" className="w-full justify-start" onClick={() => { setMenuOpen(false); onRename(button) }}>
            <Icon path={mdiPencilOutline} size={1} />
            {t('button.rename')}
          </Button>

          <Button variant="secondary" className="w-full justify-start" onClick={() => { setMenuOpen(false); onChangeIcon(button) }}>
            <Icon path={mdiImageEditOutline} size={1} />
            {t('button.changeIcon')}
          </Button>

          <Button variant="secondary" className="w-full justify-start" onClick={() => { setMenuOpen(false); onRelearn(button) }}>
            <Icon path={mdiRepeat} size={1} />
            {t('button.relearn')}
          </Button>

          <Button variant="danger" className="w-full justify-start" onClick={() => { setMenuOpen(false); onDelete(button) }}>
            <Icon path={mdiTrashCanOutline} size={1} />
            {t('common.delete')}
          </Button>
        </div>
      </Drawer>
    </>
  )
}
