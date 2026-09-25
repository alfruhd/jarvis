import os
import re
import time
import hashlib
import subprocess
import threading
import asyncio
from collections import deque
import edge_tts

CACHE_DIR = os.path.expanduser("~/.jarvis_voice_cache")
os.makedirs(CACHE_DIR, exist_ok=True)

# High-Definition Dual-Persona Neural Voices
VOICE_JARVIS = "en-GB-RyanNeural"  # Refined British accent, classic Iron Man Jarvis tone
VOICE_ZOE = "en-US-AvaNeural"     # Natural warm conversational female voice
DEFAULT_NEURAL_VOICE = VOICE_JARVIS

_current_persona = "jarvis"

def set_persona(persona: str):
    global _current_persona
    p = str(persona).lower().strip()
    if any(k in p for k in ["jarvis", "ironman", "iron man", "ryan"]):
        _current_persona = "jarvis"
        print(f"[Persona]: Set to J.A.R.V.I.S. ({VOICE_JARVIS})", flush=True)
    elif any(k in p for k in ["zoe", "female", "ava", "zoey"]):
        _current_persona = "zoe"
        print(f"[Persona]: Set to Zoe ({VOICE_ZOE})", flush=True)

def get_current_persona() -> str:
    return _current_persona

def get_persona_voice() -> str:
    return VOICE_JARVIS if _current_persona == "jarvis" else VOICE_ZOE

_current_proc = None
_proc_lock = threading.Lock()
_current_text = ""
_last_speaking_text = ""
_last_spoke_time = 0.0
_recent_spoken_phrases = deque(maxlen=15)

def stop_speaking():
    """Immediately stops any currently playing speech in under 5ms."""
    global _current_proc, _current_text, _last_spoke_time
    with _proc_lock:
        _current_text = ""
        _last_spoke_time = time.time()
        if _current_proc and _current_proc.poll() is None:
            try:
                _current_proc.kill()
            except Exception:
                pass
            _current_proc = None
    subprocess.run(["pkill", "-9", "-f", "afplay"], stderr=subprocess.DEVNULL)
    subprocess.run(["pkill", "-9", "-f", "say"], stderr=subprocess.DEVNULL)

def is_speaking() -> bool:
    """Returns True if speech is currently playing."""
    global _current_proc
    with _proc_lock:
        return _current_proc is not None and _current_proc.poll() is None

def get_current_speaking_text() -> str:
    """Returns the lowercased text currently or very recently being spoken."""
    global _current_text, _last_speaking_text, _last_spoke_time
    with _proc_lock:
        if _current_text:
            return _current_text.lower()
        if time.time() - _last_spoke_time < 6.0:
            return _last_speaking_text.lower()
        return ""

def get_last_spoke_time() -> float:
    """Returns the timestamp when speech last finished playing."""
    with _proc_lock:
        return _last_spoke_time

def get_recent_spoken_phrases(window_seconds: float = 15.0) -> list:
    """Returns list of recently spoken phrases within window_seconds for echo cancellation."""
    now = time.time()
    with _proc_lock:
        return [p for p, ts in _recent_spoken_phrases if now - ts < window_seconds]

def clean_speech_text(text: str) -> str:
    """Cleans markdown, emojis, asterisks, and code symbols for natural human speech."""
    if not text:
        return ""
    # Strip markdown bold/italics
    t = re.sub(r'[*_`#~]', '', text)
    # Strip URLs
    t = re.sub(r'https?://\S+', '', t)
    # Strip quotes
    t = t.replace('"', '').replace("'", "").replace('\n', ' ')
    # Normalize whitespace
    t = re.sub(r'\s+', ' ', t).strip()
    return t

def _play_file(path: str, spoken_text: str = ""):
    global _current_proc, _current_text, _last_speaking_text, _last_spoke_time
    with _proc_lock:
        if _current_proc and _current_proc.poll() is None:
            try:
                _current_proc.kill()
            except Exception:
                pass
            _current_proc = None
    subprocess.run(["pkill", "-9", "-f", "afplay"], stderr=subprocess.DEVNULL)
    subprocess.run(["pkill", "-9", "-f", "say"], stderr=subprocess.DEVNULL)

    with _proc_lock:
        if spoken_text:
            _current_text = spoken_text
            _last_speaking_text = spoken_text
            _recent_spoken_phrases.append((spoken_text.lower().strip(), time.time()))
        _current_proc = subprocess.Popen(["afplay", path])
    _current_proc.wait()
    with _proc_lock:
        _current_text = ""
        _last_spoke_time = time.time()
        if spoken_text:
            _recent_spoken_phrases.append((spoken_text.lower().strip(), time.time()))

def _play_fallback(text: str):
    global _current_proc, _current_text, _last_speaking_text, _last_spoke_time
    with _proc_lock:
        if _current_proc and _current_proc.poll() is None:
            try:
                _current_proc.kill()
            except Exception:
                pass
            _current_proc = None
    subprocess.run(["pkill", "-9", "-f", "afplay"], stderr=subprocess.DEVNULL)
    subprocess.run(["pkill", "-9", "-f", "say"], stderr=subprocess.DEVNULL)

    fallback_voice = "Daniel" if get_current_persona() == "jarvis" else "Samantha"
    with _proc_lock:
        _current_text = text
        _last_speaking_text = text
        _recent_spoken_phrases.append((text.lower().strip(), time.time()))
        _current_proc = subprocess.Popen(["say", "-v", fallback_voice, text])
    _current_proc.wait()
    with _proc_lock:
        _current_text = ""
        _last_spoke_time = time.time()
        _recent_spoken_phrases.append((text.lower().strip(), time.time()))

def speak_sync(text: str, voice: str = None):
    """Worker that handles neural voice synthesis and synchronous playback."""
    global _current_text, _last_speaking_text, _last_spoke_time
    clean_text = clean_speech_text(text)
    if not clean_text:
        return

    if not voice:
        voice = get_persona_voice()

    with _proc_lock:
        _current_text = clean_text
        _last_speaking_text = clean_text
        _recent_spoken_phrases.append((clean_text.lower().strip(), time.time()))
    print(f"\n[{get_current_persona().upper()} Neural Voice]: {clean_text}", flush=True)

    try:
        # 1. Check disk cache for instant 0ms playback
        cache_key = hashlib.md5(f"{voice}:{clean_text}".encode()).hexdigest()
        cache_path = os.path.join(CACHE_DIR, f"{cache_key}.mp3")

        if os.path.exists(cache_path) and os.path.getsize(cache_path) > 100:
            _play_file(cache_path, clean_text)
            return

        # 2. Synthesize using Microsoft Edge Neural TTS
        try:
            async def _generate():
                communicate = edge_tts.Communicate(clean_text, voice, rate="+5%", pitch="+0Hz")
                await communicate.save(cache_path)

            asyncio.run(_generate())

            if os.path.exists(cache_path) and os.path.getsize(cache_path) > 100:
                _play_file(cache_path, clean_text)
                return
        except Exception as e:
            print(f"[Neural TTS Warning]: {e}. Falling back to system voice.", flush=True)

        # 3. Fallback to native Samantha if offline
        _play_fallback(clean_text)
    finally:
        with _proc_lock:
            _current_text = ""
            _last_spoke_time = time.time()

def speak(text: str, voice: str = None):
    """Speaks text asynchronously using high-definition neural voice."""
    if not voice:
        voice = get_persona_voice()
    threading.Thread(target=speak_sync, args=(text, voice), daemon=True).start()

def prewarm_phrases():
    """Generates audio files in background cache for all frequent phrases."""
    phrases = [
        "Deactivating systems.",
        "Systems online.",
        "Systems active.",
        "Online.",
        "Ready.",
        "Yes, Alfred?",
        "Listening.",
        "Muted.",
        "Unmuted.",
        "Volume up.",
        "Volume down.",
        "Wi-Fi off.",
        "Wi-Fi on.",
        "Bluetooth off.",
        "Bluetooth on.",
        "Screen locked.",
        "Light mode on.",
        "Dark mode on.",
        "Mode toggled.",
        "Opening dashboard.",
        "Spotify paused.",
        "Next track.",
        "Previous track.",
        "Spotify resumed.",
        "Switched to J.A.R.V.I.S.",
        "Switched to Zoe.",
        "Done.",
        "Opening Google Chrome.",
        "Opening Safari.",
        "Opening Finder.",
        "Opening Spotify.",
        "Going to standby.",
        "Task completed."
    ]
    for v in [VOICE_JARVIS, VOICE_ZOE]:
        for p in phrases:
            clean = clean_speech_text(p)
            key = hashlib.md5(f"{v}:{clean}".encode()).hexdigest()
            path = os.path.join(CACHE_DIR, f"{key}.mp3")
            if not os.path.exists(path) or os.path.getsize(path) < 100:
                try:
                    communicate = edge_tts.Communicate(clean, v, rate="+5%", pitch="+0Hz")
                    asyncio.run(communicate.save(path))
                except Exception:
                    pass

if __name__ == "__main__":
    prewarm_phrases()
    print("Testing neural voice...")
    speak_sync("J.A.R.V.I.S. neural voice initialized successfully.")
