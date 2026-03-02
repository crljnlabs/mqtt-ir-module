# Website / UI guide

## Pages

### Home (`/`)
Health overview showing RX/TX device paths and service status. Displays the last opened remote as a shortcut (fallback: last updated remote).

### Remotes (`/remotes`)
Create, edit, and delete remotes. Each remote has a name, icon, carrier frequency, duty cycle, and an optional assigned agent.

### Remote detail (`/remotes/:id`)
Buttons grid for a remote. Send press or hold for each button. Start the learning wizard to capture new buttons.

### Agents (`/agents`)
Lists all paired agents (ESP32 and Raspberry Pi). Shows online/offline status, agent type, last seen, and firmware version. From here you can open the pairing window to register new agents.

### Agent detail (`/agents/:id`)
Full agent info: runtime state (firmware version, free heap, reset reason), configuration URL, and MQTT connectivity. Actions:
- **OTA firmware update**: select target version from the Hub catalog, confirm, and track progress.
- **Force delete**: removes the agent record even if it is stuck or offline (requires confirmation).

### Agent logs (`/agents/:id/logs`)
Live streaming log view. Initial state loaded via GET snapshot, then tailed via WebSocket. Displays MQTT-published runtime events: boot/reset, connect/disconnect, IR command results, pairing events, OTA progress.

### Settings (`/settings`)
- Theme and language (persisted in DB)
- Runtime info (Hub ID, agent ID if local agent is active)
- MQTT connection settings (stored encrypted in DB, requires `SETTINGS_MASTER_KEY`)
- ESP32 initial flash via ESP Web Tools (requires HTTPS or localhost)

## Learning wizard

Start from the Remote detail page:
- **Add buttons** — extend the remote without clearing existing buttons.
- **Re-learn remote** — clears all existing buttons (warning modal shown).

Flow:
1. Button setup (name + advanced capture parameters)
2. Capture press
3. Optional capture hold
4. Add another button or finish summary
5. Stop learning session

## Common errors

| Code | Cause | Action |
| --- | --- | --- |
| 408 | No IR signal within timeout | Retry |
| 409 | Session conflict or overwrite conflict | Retry or stop current session from another client |
| 400 | Invalid state (e.g. hold without press) | Follow the UI hint |
| 401 | Write endpoint requires API key | Configure `API_KEY` and proxy header injection or `PUBLIC_API_KEY` |
| 404 | Remote or button not found | Reload the page |

## Notes

- Sending is blocked while a learning session is active.
- Icons for remotes and buttons are stored in the database.
- Agent assignment to a remote controls which agent executes IR commands for that remote.
- OTA updates are available for ESP32 agents only.
