# Windows Setup Guide

## Prerequisites — install once

| Tool | Version | Download |
|------|---------|---------|
| Python | 3.11+ | https://www.python.org/downloads/ — check **"Add Python to PATH"** |
| Node.js | 18+ | https://nodejs.org/ |
| Expo Go (phone) | latest | App Store / Google Play |

## First run

Double-click **`setup.bat`** — it installs everything automatically.

## Every day

Double-click **`start.bat`** — opens two windows:

| Window | What it runs |
|--------|-------------|
| `Sphere Solar - Backend` | FastAPI on `http://localhost:8000` |
| `Sphere Solar - Mobile` | Expo dev server with QR code |

## Using a physical phone

1. Open `mobile\.env` in Notepad.
2. Replace `localhost` with your PC's local IP shown in `start.bat` output.
3. Scan the QR code in the Expo window with the **Expo Go** app.

## API docs (browser)

`http://localhost:8000/docs`

## Stopping

Close the two CMD windows, or press `Ctrl+C` inside each one.

## MQTT broker

The backend connects to the public broker `broker.hivemq.com:1883` by default — no local installation needed. To use a local Mosquitto broker instead, set these environment variables before running `start.bat`:

```
set MQTT_HOST=localhost
set MQTT_PORT=1883
```

Or create a `backend\.env` file:

```
MQTT_HOST=localhost
MQTT_PORT=1883
```

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `python` not recognised | Reinstall Python and check "Add to PATH" |
| `node` not recognised | Reinstall Node.js and restart the terminal |
| Port 8000 already in use | Change `--port 8000` in `start.bat` and update `mobile\.env` |
| Phone can't reach API | Use your LAN IP in `mobile\.env`, not `localhost` |
| `npm install` fails | Delete `mobile\node_modules` and run `setup.bat` again |
