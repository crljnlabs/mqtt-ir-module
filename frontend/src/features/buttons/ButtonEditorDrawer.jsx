import React, { useEffect, useState } from 'react'
import Icon from '@mdi/react'
import { useTranslation } from 'react-i18next'
import { mdiRepeat, mdiTrashCanOutline } from '@mdi/js'

import { Drawer } from '../../components/ui/Drawer.jsx'
import { Button } from '../../components/ui/Button.jsx'
import { EntityEditHeader } from '../../components/ui/EntityEditHeader.jsx'
import { IconPicker } from '../../components/pickers/IconPicker.jsx'
import { DEFAULT_BUTTON_ICON } from '../../icons/iconRegistry.js'

export function ButtonEditorDrawer({ open, button, onClose, onSave, onDelete, onRelearn }) {
  const { t } = useTranslation()
  const [name, setName] = useState('')
  const [icon, setIcon] = useState(null)
  const [iconPickerOpen, setIconPickerOpen] = useState(false)

  useEffect(() => {
    if (!open) {
      setName('')
      setIcon(null)
      setIconPickerOpen(false)
      return
    }
    if (!button) return
    setName(button.name || '')
    setIcon(button.icon ?? null)
  }, [open, button])

  function handleSaveAndClose() {
    if (!name.trim()) { onClose(); return }
    const nameChanged = name.trim() !== button.name
    const iconChanged = (icon ?? null) !== (button.icon ?? null)
    if (nameChanged || iconChanged) {
      onSave(button.id, { name: name.trim(), icon })
    }
    onClose()
  }

  if (!button) return null

  return (
    <>
      <Drawer
        open={open}
        title={`${t('common.edit')} ${t('button.title')}`}
        onClose={handleSaveAndClose}
      >
        <div className="space-y-4">
          <EntityEditHeader
            label={t('button.nameLabel')}
            name={name}
            onNameChange={(e) => setName(e.target.value)}
            onIconClick={() => setIconPickerOpen(true)}
          />

          <hr className="border-[rgb(var(--border))]" />

          <Button
            variant="secondary"
            className="w-full justify-start"
            onClick={() => onRelearn(button)}
          >
            <Icon path={mdiRepeat} size={1} />
            {t('button.relearn')}
          </Button>

          <Button
            variant="danger"
            className="w-full justify-start"
            onClick={() => onDelete(button)}
          >
            <Icon path={mdiTrashCanOutline} size={1} />
            {t('common.delete')}
          </Button>
        </div>
      </Drawer>

      <IconPicker
        open={iconPickerOpen}
        title={t('button.changeIcon')}
        initialIconKey={icon || DEFAULT_BUTTON_ICON}
        onClose={() => setIconPickerOpen(false)}
        onBack={() => setIconPickerOpen(false)}
        onSelect={(key) => {
          setIcon(key)
          setIconPickerOpen(false)
        }}
      />
    </>
  )
}
