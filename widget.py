import os
import subprocess
import threading
import time
import re
import difflib
import io
import soundfile as sf
import whisper
import webview
import speech_recognition as sr
import AppKit
import requests
from voice import speak, is_speaking, stop_speaking, get_current_speaking_text, get_recent_spoken_phrases, get_last_spoke_time, set_persona, get_current_persona, VOICE_JARVIS, VOICE_ZOE

print("[SYS]: Initializing on-device offline Whisper STT...", flush=True)
try:
    offline_whisper = whisper.load_model("tiny.en")
    print("[SYS]: Offline Whisper STT ready for zero-network speech recognition.", flush=True)
except Exception as _we:
    print(f"[SYS Warning]: Whisper loading error: {_we}", flush=True)
    offline_whisper = None

def transcribe_audio_offline(audio_data) -> str:
    """Transcribes audio 100% locally on-device without internet."""
    if not offline_whisper:
        return ""
    try:
        wav_bytes = audio_data.get_wav_data(convert_rate=16000, convert_width=2)
        audio_np, _ = sf.read(io.BytesIO(wav_bytes), dtype='float32')
        res = offline_whisper.transcribe(audio_np, fp16=False, language='en')
        return res.get('text', '').strip()
    except Exception as e:
        print(f"[Offline STT Error]: {e}", flush=True)
        return ""

def speak_response(text: str, voice: str = None):
    """Speaks text using high-definition neural voice with dynamic persona."""
    speak(text, voice)

speak_feminine = speak_response

window = None
idle_timer = None
idle_lock = threading.Lock()
is_active_session = False
deactivation_cooldown_until = 0.0

def hide_window_auto():
    global window, is_active_session
    with idle_lock:
        is_active_session = False
    if window:
        print("[SYS]: Idle timeout. Assistant in ambient standby...", flush=True)
        try:
            window.evaluate_js("setActive(false);")
        except Exception:
            pass

def reset_idle_timer(duration: float = 25.0):
    """Keeps the widget alive and resets the idle countdown (waiting for user input)."""
    global window, idle_timer, is_active_session
    was_active = False
    with idle_lock:
        was_active = is_active_session
        is_active_session = True
        if idle_timer and idle_timer.is_alive():
            try:
                idle_timer.cancel()
            except Exception:
                pass
        idle_timer = threading.Timer(duration, hide_window_auto)
        idle_timer.daemon = True
        idle_timer.start()
    if not was_active:
        threading.Thread(target=lambda: requests.post("http://127.0.0.1:8090/api/reset_session", timeout=2), daemon=True).start()
    if window:
        window.show()
        try:
            window.evaluate_js("setActive(true);")
        except Exception:
            pass

def dismiss_session():
    """Immediately ends the active session and hides the widget on explicit user request."""
    global window, idle_timer, is_active_session, deactivation_cooldown_until
    with idle_lock:
        is_active_session = False
        deactivation_cooldown_until = time.time() + 4.5
        if idle_timer and idle_timer.is_alive():
            try:
                idle_timer.cancel()
            except Exception:
                pass
    if window:
        try:
            window.evaluate_js("setActive(false);")
        except Exception:
            pass
        window.hide()
    threading.Thread(target=lambda: requests.post("http://127.0.0.1:8090/api/reset_session", timeout=2), daemon=True).start()

def open_dashboard_window():
    """Opens the MK-V HUD dashboard in true native fullscreen kiosk mode."""
    print("[SYS]: Launching MK-V Dashboard in true fullscreen kiosk mode...", flush=True)
    try:
        cmd = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "--user-data-dir=/tmp/jarvis_chrome_hud",
            "--kiosk",
            "--no-first-run",
            "--no-default-browser-check",
            "http://127.0.0.1:8090"
        ]
        subprocess.Popen(cmd)
    except Exception as e:
        print(f"[Dashboard Launch Error]: {e}", flush=True)
        subprocess.Popen(["open", "-na", "Google Chrome", "--args", "--app=http://127.0.0.1:8090", "--start-fullscreen"])

JARVIS_WAKE_WORDS = [
    "hey jarvis", "jarvis", "yo jarvis", "hi jarvis", "hello jarvis",
    "ok jarvis", "okay jarvis"
]

ZOE_WAKE_WORDS = [
    "hey zoe", "zoe", "hey zoey", "zoey", "yo zoe", "hi zoe",
    "hello zoe", "ok zoe", "okay zoe", "zooey"
]

WAKE_WORDS = JARVIS_WAKE_WORDS + ZOE_WAKE_WORDS

def detect_persona_from_speech(text: str) -> str:
    """Detects whether user is speaking to Jarvis or Zoe."""
    t = text.lower().strip()
    words = re.sub(r'[^\w\s]', '', t).split()
    if any(k in t for k in ["switch to jarvis", "use jarvis voice", "speak like jarvis", "jarvis voice"]):
        return "jarvis"
    if any(k in t for k in ["switch to zoe", "use zoe voice", "speak like zoe", "zoe voice", "call zoe", "talk to zoe"]):
        return "zoe"
    zoe_tokens = {"zoe", "zoey", "zooey"}
    jarvis_tokens = {"jarvis", "jarv", "javis"}
    if any(w in words for w in zoe_tokens) or any(w in t for w in ZOE_WAKE_WORDS):
        return "zoe"
    if any(w in words for w in jarvis_tokens) or any(w in t for w in JARVIS_WAKE_WORDS):
        return "jarvis"
    return None

STOP_WORDS = [
    "stop", "wait", "hold on", "quiet", "be quiet", "shut up",
    "pause", "shh", "silence", "cancel", "never mind", "nevermind",
    "enough", "halt"
]

DEACTIVATE_WORDS = [
    "deactivate", "deactivate systems", "deactivate now",
    "power down", "shut down", "shutdown", "turn off",
    "go to sleep", "sleep", "dismiss", "cancel", "never mind",
    "nevermind", "stop listening", "goodbye", "bye", "exit", "standby"
]

FAST_COMMANDS = [
    "mute", "unmute", "dashboard", "finder", "safari", "chrome", "open ", "launch ",
    "tabs", "spotify", "music", "playlist", "wifi", "wi-fi", "wi fi", "bluetooth",
    "turn off wifi", "turn on wifi", "turn off wi-fi", "turn on wi-fi", "disconnect wifi",
    "ip address", "ip", "address", "network", "time", "date"
]

class WidgetApi:
    def on_click(self):
        """Single-click on Arc Reactor: manual activation!"""
        print(f"[Manual UI]: Hologram clicked - activating ({get_current_persona()})!", flush=True)
        reset_idle_timer(25.0)
        import random
        greetings = ["Yes, Alfred?", "Online.", "Ready."]
        speak_response(random.choice(greetings))

    def on_deactivate(self):
        """Double-click or right-click on Arc Reactor: manual deactivation!"""
        print("[Manual UI]: Deactivation requested via widget.", flush=True)
        dismiss_session()
        speak_response("Deactivating systems.")

def ipc_listener():
    """Listens for manual activation and deactivation signals from CLI or shortcuts."""
    pipe_path = "/tmp/jarvis_pipe"
    while True:
        try:
            if not os.path.exists(pipe_path):
                try:
                    os.mkfifo(pipe_path)
                except Exception:
                    pass
            with open(pipe_path, "r") as fifo:
                for line in fifo:
                    cmd = line.strip().lower()
                    if cmd in ("activate", "wake", "show", "on", "start"):
                        print("[IPC]: Manual activation signal received!", flush=True)
                        reset_idle_timer(25.0)
                        import random
                        greetings = ["Yes, Alfred?", "Online.", "Ready."]
                        speak_response(random.choice(greetings))
                    elif cmd in ("deactivate", "sleep", "hide", "off", "stop"):
                        print("[IPC]: Manual deactivation signal received!", flush=True)
                        dismiss_session()
                        speak_response("Deactivating systems.")
                    elif cmd in ("toggle", "t"):
                        if is_active_session:
                            print("[IPC]: Manual toggle -> deactivating!", flush=True)
                            dismiss_session()
                            speak_response("Deactivating systems.")
                        else:
                            print("[IPC]: Manual toggle -> activating!", flush=True)
                            reset_idle_timer(25.0)
                            import random
                            greetings = ["Yes, Alfred?", "Online.", "Ready."]
                            speak_response(random.choice(greetings))
                    elif cmd == "dashboard":
                        open_dashboard_window()
        except Exception:
            time.sleep(0.5)

def has_wake_word(text: str) -> bool:
    t = text.lower().strip()
    t_clean = re.sub(r'[^\w\s]', '', t)
    words = t_clean.split()
    if not words:
        return False

    # 1. Exact phrase or substring match
    for w in WAKE_WORDS:
        if re.search(rf'\b{re.escape(w)}\b', t_clean):
            return True

    # 2. Individual word match
    target_names = {
        "jarvis", "zoe", "zoey", "zooey", "zo", "z", "zoya", "zoie", "zowie", "xoe", "soey", "travis", "jarv", "javis", "jar"
    }
    if any(w in target_names for w in words):
        return True

    # 3. Two-word pattern: (hey/hi/hello/yo/ok/okay/a) + (z/zo/zoe/joe/so/jarv/jar/etc.)
    salutations = {"hey", "hi", "hello", "yo", "ok", "okay", "a"}
    short_names = {"z", "zo", "zoe", "zoey", "zooey", "joe", "so", "jar", "jarv", "javis", "java"}
    for i in range(len(words) - 1):
        if words[i] in salutations and words[i+1] in short_names:
            return True

    return False

ACTION_STARTERS = [
    "open ", "launch ", "play ", "start ", "search ", "find ", "tell ", "what ", "who ",
    "how ", "why ", "when ", "where ", "can you ", "could you ", "deactivat", "activat",
    "stop", "pause", "resume", "mute", "unmute", "volume", "tabs", "spotify", "dashboard",
    "finder", "safari", "chrome", "terminal", "code", "vs code", "vscode", "close ",
    "turn off ", "turn on ", "turn of ", "disconnect ", "connect ", "switch off ", "switch on ",
    "wifi", "wi-fi", "wi fi", "bluetooth"
]

def is_speaker_echo(heard_text: str, speaking_text: str = "") -> bool:
    """
    Returns True if the heard text is an acoustic echo of any response
    spoken by the assistant in the last 15 seconds.
    Uses multi-tier matching:
    1. Exact / substring match
    2. Character SequenceMatcher overall ratio >= 0.50
    3. Contiguous sequence slice match >= 0.50 of heard text
    4. Word-set overlap >= 0.50 (with at least 2 words, or 1 word if it's a long unique word >= 5 chars)
    """
    if not heard_text:
        return False

    h = heard_text.lower().strip()

    # Never consider wake words or stop words as echo!
    if has_wake_word(h):
        return False
    if any(re.search(rf'\b{re.escape(sw)}\b', h) for sw in STOP_WORDS):
        return False

    h_clean = re.sub(r'[^\w]', '', h)
    if not h_clean or len(h_clean) < 3:
        return False

    recent = get_recent_spoken_phrases(15.0)
    current = speaking_text or get_current_speaking_text()
    if current:
        recent.append(current)

    h_words = set(re.sub(r'[^\w\s]', '', h).split())

    for phrase in recent:
        p = phrase.lower().strip()
        p_clean = re.sub(r'[^\w]', '', p)
        if not p_clean or len(p_clean) < 3:
            continue

        # 1. Exact match or substring match
        if h_clean in p_clean or p_clean in h_clean:
            return True

        # 2. Fuzzy similarity (catches STT mishearings like 'systems on mine' vs 'systems online')
        sim = difflib.SequenceMatcher(None, h_clean, p_clean).ratio()
        if sim >= 0.50:
            return True

        # 3. Longest contiguous matching slice relative to heard text length
        matcher = difflib.SequenceMatcher(None, h_clean, p_clean)
        longest = matcher.find_longest_match(0, len(h_clean), 0, len(p_clean))
        if len(h_clean) > 0 and (longest.size / len(h_clean)) >= 0.50 and longest.size >= 5:
            return True

        # 4. Word-set overlap (catches partial STT transcriptions or pronoun shifts like "you'll" vs "I'll")
        p_words = set(re.sub(r'[^\w\s]', '', p).split())
        overlap = h_words.intersection(p_words)
        if len(h_words) > 0:
            word_ratio = len(overlap) / len(h_words)
            if word_ratio >= 0.50 and (len(overlap) >= 2 or (len(overlap) == 1 and any(len(w) >= 5 for w in overlap))):
                return True

    return False

def clean_wake_words(text: str) -> str:
    """Strips wake words and interruption fillers to get pure user directive."""
    cleaned = text.lower().strip()

    # Speech normalization: fix common phonetics / missing double f
    cleaned = re.sub(r'\bturn of\b', 'turn off', cleaned)
    cleaned = re.sub(r'\bshut of\b', 'shut off', cleaned)
    cleaned = re.sub(r'\bswitch of\b', 'switch off', cleaned)
    cleaned = re.sub(r'\bpower of\b', 'power off', cleaned)

    for w in sorted(WAKE_WORDS, key=len, reverse=True):
        cleaned = re.sub(rf'^{re.escape(w)}(?:[,\s]+|$)', '', cleaned).strip()

    # Strip patterns like "hey z", "hey zo", "hey zoe", "hi zoe", etc.
    cleaned = re.sub(r'^(hey|hi|hello|yo|ok|okay)\s+(z|zo|zoe|zoey|zooey|jarvis|jarv|jar|javis)[,\s]*', '', cleaned).strip()

    # Strip conversational barge-in / politeness fillers
    fillers = [
        "i am telling you to", "am telling you to", "i tell you to", "am telling to",
        "i told you to", "i want you to", "can you", "could you", "would you", "will you",
        "please", "tell me", "wait", "hold on", "actually", "no wait", "stop"
    ]
    for filler in fillers:
        cleaned = re.sub(rf'^{re.escape(filler)}[,\s]+', '', cleaned).strip()

    # Strip trailing fillers like "instead", "please"
    cleaned = re.sub(r'[,\s]+instead$', '', cleaned).strip()
    cleaned = re.sub(r'[,\s]+please$', '', cleaned).strip()
    return cleaned

def is_assistant_deactivation_request(raw_text: str, directive: str) -> bool:
    """
    Carefully distinguishes genuine assistant deactivation / standby commands
    from hardware, subsystem, or application commands (like Wi-Fi, Bluetooth, volume, etc.).
    """
    t = raw_text.lower().strip()
    d = directive.lower().strip()

    # Subsystem targets: if any of these are mentioned, this is NEVER assistant deactivation!
    subsystem_targets = [
        "wifi", "wi-fi", "wi fi", "internet", "network", "connection", "hotspot", "router",
        "bluetooth", "blue tooth", "bt",
        "music", "song", "track", "spotify", "playlist", "audio", "sound", "volume",
        "screen", "display", "monitor",
        "mac", "computer", "pc", "laptop",
        "tab", "tabs", "window", "windows", "chrome", "safari", "finder", "app", "application",
        "dark mode", "light mode"
    ]
    if any(target in t for target in subsystem_targets) or any(target in d for target in subsystem_targets):
        return False

    # Pure assistant deactivation phrases
    pure_deactivate = {
        "deactivate", "deactivate systems", "deactivate now", "deactivate please",
        "power down", "power down systems", "shut down", "shutdown",
        "go to sleep", "sleep", "standby", "go to standby",
        "dismiss", "cancel", "never mind", "nevermind", "stop listening",
        "goodbye", "bye", "exit", "turn off", "turn off assistant", "turn yourself off"
    }
    if d in pure_deactivate or t in pure_deactivate:
        return True

    # Starts with explicit deactivation verbs
    for p in ["deactivate", "power down", "go to sleep", "go to standby", "standby"]:
        if t == p or t.startswith(f"{p} ") or d == p or d.startswith(f"{p} "):
            return True

    # Explicit named assistant deactivations
    if any(p in t for p in ["turn off jarvis", "turn off zoe", "shut down jarvis", "shut down zoe"]):
        return True

    return False

last_handled_directive = ""
last_handled_time = 0.0

def handle_speech_command(raw_text: str):
    """Processes verified speech commands with maximum speed."""
    global is_active_session, last_handled_directive, last_handled_time

    text_lower = raw_text.lower().strip()
    directive = clean_wake_words(raw_text).strip()

    # Deduplication guard: ignore repeated speech commands within 3.5 seconds
    if directive and directive == last_handled_directive and time.time() - last_handled_time < 3.5:
        print(f"[Deduplication]: Suppressed duplicate directive '{directive}' within {time.time() - last_handled_time:.1f}s", flush=True)
        return

    # Filter isolated background noise or micro-mumbles
    if len(directive) <= 2 or directive in ("down", "there", "name", "of it", "um", "uh", "ah", "hmm", "and"):
        return

    last_handled_directive = directive
    last_handled_time = time.time()

    # Dynamic persona sync
    detected = detect_persona_from_speech(raw_text)
    if detected:
        set_persona(detected)

    # Check explicit persona switch command
    if any(k in text_lower for k in ["switch to jarvis", "use jarvis voice", "speak like jarvis", "jarvis voice", "iron man voice", "ironman voice"]):
        set_persona("jarvis")
        speak_response("Switched to J.A.R.V.I.S.")
        return
    elif any(k in text_lower for k in ["switch to zoe", "use zoe voice", "speak like zoe", "zoe voice", "female voice", "call zoe", "talk to zoe"]):
        set_persona("zoe")
        speak_response("Switched to Zoe.")
        return

    # Check for genuine assistant deactivation / sleep / dismiss commands
    if is_assistant_deactivation_request(raw_text, directive):
        print(f"[Directive]: Assistant deactivation requested ('{raw_text}')", flush=True)
        dismiss_session()
        speak_response("Deactivating systems.")
        return

    # Check for explicit activation command
    if directive in ("activate", "activate systems", "turn on", "wake up"):
        reset_idle_timer(25.0)
        speak_response("Systems active.")
        return

    print(f"\n[Directive]: '{directive}'")

    # If the user only called the wake word (e.g. "Hey Jarvis" or "Zoe") with no directive
    if not directive:
        reset_idle_timer(25.0) # Stay active and wait 25 seconds for user speech
        import random
        greetings = ["Yes, Alfred?", "Online.", "Ready."]
        speak_response(random.choice(greetings))
        return

    # User gave a real directive: extend idle timer so widget stays up
    reset_idle_timer(25.0)

    # FAST-PATH: Mute / Unmute / Volume
    if directive in ("mute", "mute system", "mute audio"):
        speak_response("Muted.")
        requests.post("http://127.0.0.1:8090/api/action", json={"intent": "mute"})
        reset_idle_timer(25.0)
        return
    elif directive in ("unmute", "unmute system", "unmute audio"):
        speak_response("Unmuted.")
        requests.post("http://127.0.0.1:8090/api/action", json={"intent": "unmute"})
        reset_idle_timer(25.0)
        return

    # FAST-PATH: Dashboard HUD
    if any(k in directive for k in ["open dashboard", "show dashboard", "dashboard", "open hud", "hud"]):
        speak_response("Opening dashboard.")
        time.sleep(0.4)
        open_dashboard_window()
        reset_idle_timer(20.0)
        return

    # Forward directive directly to the ultra-fast backend
    try:
        t0 = time.time()
        resp = requests.post(
            "http://127.0.0.1:8090/api/chat",
            json={"prompt": directive, "voice": True},
            timeout=25
        )
        if resp.status_code == 200:
            data = resp.json()
            reply = data.get("response", "Done.")
            print(f"[Response in {time.time() - t0:.2f}s]: {reply}")
            if any(k in reply.lower() for k in ["deactivating systems", "deactivating", "going to standby"]):
                dismiss_session()
                speak_response(reply)
                return
            speak_response(reply)
            reset_idle_timer(25.0)
        else:
            speak_response("Server error.")
            reset_idle_timer(15.0)
    except Exception as e:
        print(f"[Backend Connection Error]: {e}")
        speak_response("Core offline.")
        reset_idle_timer(15.0)

def start_listener():
    r = sr.Recognizer()
    r.dynamic_energy_threshold = False
    r.pause_threshold = 0.65       # Snappy conversational cadence
    r.non_speaking_duration = 0.25 # Fast trailing silence detection
    r.energy_threshold = 140.0     # Sensitive baseline that detects normal voice without noise
    mic = sr.Microphone()

    print("==================================================", flush=True)
    print("🎙️ J.A.R.V.I.S. / Zoe Full-Duplex Voice Core Online.", flush=True)
    print("Barge-in / Interruptions Enabled. Listening continuously...", flush=True)
    print("==================================================", flush=True)

    with mic as source:
        print("[SYS]: Initializing microphone baseline...", flush=True)
        r.energy_threshold = 140.0
        print(f"[SYS]: Microphone online. Energy threshold locked at {r.energy_threshold:.1f}", flush=True)

        while True:
            try:
                # If deactivation cooldown is active, pause listener to avoid self-triggering
                if time.time() < deactivation_cooldown_until:
                    time.sleep(0.3)
                    continue

                # Full-duplex: continuous microphone capture (never paused during speech)
                audio = r.listen(source, timeout=None, phrase_time_limit=10)

                # Discard audio if deactivation was initiated while audio was being recorded
                if time.time() < deactivation_cooldown_until:
                    continue

                text = ""
                try:
                    text = r.recognize_google(audio).lower().strip()
                except Exception:
                    pass

                # If Google cloud recognition produced no text (e.g. UnknownValueError on short name like 'Zoe' or offline):
                if not text:
                    text = transcribe_audio_offline(audio).lower().strip()
                    if text:
                        print(f"[Offline Whisper Heard]: '{text}'", flush=True)

                if not text:
                    continue

                # Extra check after speech recognition
                if time.time() < deactivation_cooldown_until:
                    continue

                speaking_text = get_current_speaking_text()
                was_speaking = is_speaking() or bool(speaking_text)

                # Acoustic Echo Cancellation: ignore assistant's own voice echo from speakers
                if is_speaker_echo(text, speaking_text):
                    print(f"[Echo Filtered]: '{text}' matches assistant speech", flush=True)
                    continue

                # Acoustic settling guard: if speech just finished within 0.75s and utterance is short or noise
                if (time.time() - get_last_spoke_time() < 0.75) and not has_wake_word(text):
                    print(f"[Acoustic Guard]: Ignored audio captured during speaker settling ('{text}')", flush=True)
                    continue

                print(f"\n[Heard]: '{text}' (active={is_active_session}, was_speaking={was_speaking})", flush=True)

                # Dynamic persona detection from speech
                detected_persona = detect_persona_from_speech(text)
                if detected_persona:
                    set_persona(detected_persona)

                # User barge-in! If assistant is speaking, cut speech immediately in <5ms
                if is_speaking():
                    print("[Full Duplex]: User barge-in detected! Halting assistant speech immediately.", flush=True)
                    stop_speaking()

                wake_detected = has_wake_word(text)
                fast_detected = any(c in text for c in FAST_COMMANDS)
                action_detected = any(text.startswith(act) or f" {act}" in text for act in ACTION_STARTERS)
                stop_detected = any(re.search(rf'\b{re.escape(sw)}\b', text) for sw in STOP_WORDS)

                # If user issued a stop/pause interruption
                if stop_detected:
                    cleaned = clean_wake_words(text)
                    for sw in STOP_WORDS:
                        cleaned = re.sub(rf'^{re.escape(sw)}[,\s]+', '', cleaned).strip()
                        cleaned = re.sub(rf'[,\s]+{re.escape(sw)}$', '', cleaned).strip()

                    if not cleaned or cleaned in STOP_WORDS:
                        print("[Interruption]: Stop/Pause acknowledged.", flush=True)
                        subprocess.Popen(["afplay", "/System/Library/Sounds/Tink.aiff"])
                        reset_idle_timer(25.0)
                        continue

                # STRICT STANDBY WAKE POLICY:
                # If assistant is currently asleep in standby (is_active_session is False),
                # it MUST ONLY WAKE UP on an explicit wake word (e.g. "Hey Jarvis" or "Zoe")!
                # It will NEVER wake up from casual background speech, TV, or random words.
                if not is_active_session:
                    if not wake_detected:
                        # Sleeping: completely ignore casual speech
                        continue
                    # Fresh wake up: play chime
                    subprocess.Popen(["afplay", "/System/Library/Sounds/Tink.aiff"])

                # Reset/extend the active conversation window (20 seconds)
                reset_idle_timer(20.0)

                # DISPATCH ASYNCHRONOUSLY SO LISTENER IS NEVER BLOCKED!
                threading.Thread(target=handle_speech_command, args=(text,), daemon=True).start()
            except Exception as e:
                print(f"[Listener Exception]: {e}", flush=True)
                time.sleep(0.5)

def manual_trigger():
    """Press Enter in the terminal to simulate a wake-word trigger for testing."""
    try:
        while True:
            cmd = input()
            if cmd.strip():
                print(f"\n[Manual Input]: '{cmd}'")
                reset_idle_timer(10.0)
                handle_speech_command(cmd)
            else:
                print("\n[Manual Trigger]: Simulating wake word...")
                import random
                greetings = ["Yes, Alfred?", "Online.", "Ready."]
                speak_response(random.choice(greetings))
    except (EOFError, OSError):
        pass

def on_loaded():
    global window
    if window:
        try:
            app = AppKit.NSApplication.sharedApplication()
            app.setActivationPolicy_(1) # 1 = NSApplicationActivationPolicyAccessory
        except Exception:
            pass
        print("[SYS]: Hologram initialized. Announcing startup status...")
        window.show()
        try:
            window.evaluate_js("setActive(true);")
        except Exception:
            pass
        reset_idle_timer(25.0)
        speak_response("Systems online.")

def trigger_hotkey_activate():
    print("[Hotkey]: Global hotkey -> Activate J.A.R.V.I.S.!", flush=True)
    reset_idle_timer(25.0)
    import random
    witty_greetings = [
        "Yes, Alfred?",
        "Online.",
        "Ready."
    ]
    speak_response(random.choice(witty_greetings))

def trigger_hotkey_deactivate():
    print("[Hotkey]: Global hotkey -> Deactivate J.A.R.V.I.S.!", flush=True)
    dismiss_session()
    speak_response("Deactivating systems.")

def trigger_hotkey_toggle():
    global is_active_session
    print(f"[Hotkey]: Global hotkey -> Toggle J.A.R.V.I.S.! (currently active={is_active_session})", flush=True)
    if is_active_session:
        trigger_hotkey_deactivate()
    else:
        trigger_hotkey_activate()

def start_hotkey_listener():
    """Listens for system-wide keyboard shortcuts in the background."""
    try:
        from pynput import keyboard
        print("[SYS]: Initializing global keyboard hotkeys...", flush=True)
        with keyboard.GlobalHotKeys({
            # Control + Option combinations (zero macOS/Chrome conflicts)
            '<ctrl>+<alt>+j': trigger_hotkey_activate,
            '<ctrl>+<alt>+k': trigger_hotkey_deactivate,
            '<ctrl>+<alt>+<space>': trigger_hotkey_toggle,

            # Control + Shift combinations (alternative)
            '<ctrl>+<shift>+j': trigger_hotkey_activate,
            '<ctrl>+<shift>+k': trigger_hotkey_deactivate,
            '<ctrl>+<shift>+<space>': trigger_hotkey_toggle,
        }) as hotkeys:
            print("[SYS]: Global hotkeys online: Ctrl+Option+Space (Toggle), Ctrl+Option+J (Activate), Ctrl+Option+K (Deactivate)", flush=True)
            hotkeys.join()
    except Exception as e:
        print(f"[Hotkey Init Warning]: {e}", flush=True)

if __name__ == "__main__":
    time.sleep(1)

    threading.Thread(target=start_listener, daemon=True).start()
    threading.Thread(target=manual_trigger, daemon=True).start()
    threading.Thread(target=ipc_listener, daemon=True).start()
    threading.Thread(target=start_hotkey_listener, daemon=True).start()

    api = WidgetApi()
    candidates = [
        os.path.join(os.path.dirname(__file__), "ui", "widget.html"),
        os.path.join(os.path.dirname(__file__), "widget.html"),
        os.path.abspath("widget.html")
    ]
    html_target = next((c for c in candidates if os.path.exists(c)), os.path.abspath("widget.html"))
    html_path = 'file://' + os.path.abspath(html_target)
    window = webview.create_window(
        "J.A.R.V.I.S. Hologram",
        url=html_path,
        width=220,
        height=220,
        frameless=True,
        transparent=True,
        on_top=True,
        js_api=api
    )

    window.events.loaded += on_loaded
    webview.start(private_mode=False)