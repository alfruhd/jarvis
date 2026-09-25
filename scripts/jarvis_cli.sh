#!/bin/bash
# J.A.R.V.I.S. Command Line Controller
ACTION="$1"

case "$ACTION" in
    activate|start|on|wake)
        if ! pgrep -f "widget.py" > /dev/null; then
            echo "⚡ Starting J.A.R.V.I.S. Core..."
            /Users/alfruhd/jarvis/start.sh &
            echo "✅ J.A.R.V.I.S. launched."
        else
            echo "activate" > /tmp/jarvis_pipe 2>/dev/null
            echo "🎙️ J.A.R.V.I.S. activated."
        fi
        ;;
    deactivate|stop|off|sleep)
        echo "deactivate" > /tmp/jarvis_pipe 2>/dev/null
        echo "💤 J.A.R.V.I.S. deactivated (standby)."
        ;;
    toggle|t)
        echo "toggle" > /tmp/jarvis_pipe 2>/dev/null
        echo "🔄 J.A.R.V.I.S. toggled."
        ;;
    quit|kill|shutdown)
        echo "🛑 Shutting down J.A.R.V.I.S..."
        pkill -9 -f "widget.py" 2>/dev/null
        pkill -9 -f "server.py" 2>/dev/null
        echo "✅ J.A.R.V.I.S. stopped."
        ;;
    dashboard|hud)
        echo "🖥️ Opening HUD Dashboard..."
        open -na "Google Chrome" --args "--app=http://127.0.0.1:8090" "--start-fullscreen"
        ;;
    status)
        echo "=== J.A.R.V.I.S. System Status ==="
        if pgrep -f "widget.py" > /dev/null; then
            echo "🟢 Hologram Voice Widget: ONLINE (PID $(pgrep -f 'widget.py' | head -1))"
        else
            echo "🔴 Hologram Voice Widget: OFFLINE"
        fi
        if pgrep -f "server.py" > /dev/null; then
            echo "🟢 Neural Core Server: ONLINE (PID $(pgrep -f 'server.py' | head -1))"
        else
            echo "🔴 Neural Core Server: OFFLINE"
        fi
        ;;
    *)
        echo "=============================================="
        echo "🤖 J.A.R.V.I.S. / Zoe Controller"
        echo "=============================================="
        echo "Usage:"
        echo "  jarvis activate    - Wake up and activate voice assistant"
        echo "  jarvis deactivate  - Send assistant to standby (hide hologram)"
        echo "  jarvis toggle      - Toggle between active and standby"
        echo "  jarvis status      - Check online/offline status"
        echo "  jarvis dashboard   - Open MK-V HUD dashboard"
        echo "  jarvis quit        - Fully shut down J.A.R.V.I.S. processes"
        echo "=============================================="
        ;;
esac
