# 🤖 J.A.R.V.I.S. / Zoe — Dual-Persona AI Desktop Assistant

An intelligent, full-duplex conversational voice assistant with an on-screen Arc Reactor hologram HUD, built for macOS.

---

## 📁 Project Architecture

```
jarvis/
├── apps/                 # macOS Application Bundles (.app)
│   ├── Activate JARVIS.app    # Wake up / activate hologram
│   ├── Deactivate JARVIS.app  # Send assistant to sleep / standby
│   ├── Toggle JARVIS.app      # Toggle active/standby mode
│   └── J.A.R.V.I.S.app        # Full standalone macOS launcher
├── core / root files:
│   ├── server.py              # FastAPI Core Intelligence & Tool Router
│   ├── widget.py              # WebKit Arc Reactor Hologram & Full-Duplex Voice Engine
│   ├── voice.py               # Edge Neural TTS (British Jarvis & Warm Zoe)
│   └── activity_monitor.py    # System telemetry, browser tab & Spotify tracker
├── ui/                   # Web & Hologram Interfaces
│   ├── index.html             # Iron Man MK-V HUD Web Dashboard
│   └── widget.html            # Arc Reactor floating canvas animation
├── scripts/              # Shell scripts & utilities
│   ├── start.sh               # Master launcher script
│   ├── jarvis_cli.sh          # Terminal controller CLI (`jarvis`)
│   ├── enroll.py              # Voice profile enrollment script
│   └── test_server.py         # Lightweight server test script
├── logs/                 # Centralized logs
│   ├── jarvis.log             # General startup logs
│   ├── server.log             # Core server logs
│   └── widget.log             # Voice listener & speech logs
├── data/                 # Biometric & persistent voice embeddings
│   ├── alfred_voice.npy       # Enrolled user voiceprint
│   └── temp_voice.npy         # Temporary voice audio buffer
└── venv/                 # Python 3.9 virtual environment
```

---

## ⌨️ Global Shortcuts & Control

- **Hotkeys**:
  - `Ctrl + Option + Space`: Toggle J.A.R.V.I.S. (Active ⟷ Standby)
  - `Ctrl + Option + J`: Wake up & Activate
  - `Ctrl + Option + K`: Deactivate / Send to Standby

- **Terminal Aliases**:
  - `j`: Toggle J.A.R.V.I.S.
  - `jon`: Activate J.A.R.V.I.S.
  - `joff`: Deactivate J.A.R.V.I.S.
  - `jstatus`: Check service status
  - `jhud`: Open full-screen MK-V HUD dashboard
