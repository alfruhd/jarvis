#!/bin/bash
export PATH="/Users/alfruhd/jarvis/venv/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"
export PYTHONUNBUFFERED=1
cd /Users/alfruhd/jarvis
source /Users/alfruhd/jarvis/venv/bin/activate

# Allow macOS audio and WindowServer a moment to settle
sleep 2

# 1. Start Ollama runtime if not already active
if ! pgrep -x "ollama" > /dev/null && ! pgrep -f "Ollama.app" > /dev/null; then
    open -a Ollama 2>/dev/null || nohup /usr/local/bin/ollama serve > /dev/null 2>&1 &
    sleep 3
fi

# 2. Free port 8090 if bound
lsof -ti:8090 | xargs kill -9 2>/dev/null

# 3. Clean up lingering old processes
pkill -9 -f "server.py" 2>/dev/null
pkill -9 -f "widget.py" 2>/dev/null

# 4. Prewarm model
curl -s http://localhost:11434/api/generate -d '{"model": "qwen2.5:3b", "keep_alive": "24h"}' > /dev/null 2>&1 &

# 5. Start J.A.R.V.I.S. Core Server
mkdir -p /Users/alfruhd/jarvis/logs
echo "🚀 Starting J.A.R.V.I.S. Core Intelligence Server..." >> /Users/alfruhd/jarvis/logs/jarvis.log
/Users/alfruhd/jarvis/venv/bin/python3 server.py >> /Users/alfruhd/jarvis/logs/server.log 2>&1 &

# Wait for server
for i in {1..25}; do
    if curl -s http://127.0.0.1:8090/docs > /dev/null 2>&1; then
        echo "✅ J.A.R.V.I.S. server online." >> /Users/alfruhd/jarvis/logs/jarvis.log
        break
    fi
    sleep 0.5
done

# 6. Start J.A.R.V.I.S. Hologram & Voice Interface
echo "🎙️ Starting J.A.R.V.I.S. Hologram & Voice Interface..." >> /Users/alfruhd/jarvis/logs/jarvis.log
exec /Users/alfruhd/jarvis/venv/bin/python3 widget.py >> /Users/alfruhd/jarvis/logs/widget.log 2>&1
