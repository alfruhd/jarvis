import os
import subprocess
import json
import time
import re
import socket
import urllib.request
import urllib.parse
from datetime import datetime
from collections import deque
import psutil
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from ollama import chat
from voice import speak
from activity_monitor import (
    start_activity_monitor,
    restore_tabs_from_history,
    spotify_control,
    get_activity_summary,
    set_preference,
    get_preference
)

app = FastAPI(title="J.A.R.V.I.S. Core Intelligence Engine")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Audit log store for HUD live telemetry feed
audit_logs = deque(maxlen=100)

def log_event(tool_name: str, details: str, status: str = "SUCCESS"):
    entry = {
        "timestamp": datetime.now().strftime("%H:%M:%S"),
        "tool": tool_name,
        "details": details,
        "status": status
    }
    audit_logs.append(entry)
    print(f"[{entry['timestamp']}] [{status}] {tool_name}: {details}")

# ==========================================
# TOOL IMPLEMENTATIONS (OPTIMIZED FOR ZERO-LATENCY)
# ==========================================

def get_weather(location: str = "Dar es Salaam") -> str:
    """Get the current live weather conditions for any city or location."""
    try:
        loc_clean = location.strip() or "Dar es Salaam"
        loc_encoded = urllib.parse.quote(loc_clean)
        url = f"https://wttr.in/{loc_encoded}?format=j1"
        req = urllib.request.Request(url, headers={'User-Agent': 'curl/7.68.0'})
        with urllib.request.urlopen(req, timeout=4) as resp:
            data = json.loads(resp.read().decode())
            current = data['current_condition'][0]
            condition = current['weatherDesc'][0]['value']
            temp = current['temp_C']
            feels = current['FeelsLikeC']
            humidity = current['humidity']
            wind = current['windspeedKmph']
            result = f"Weather in {loc_clean}: {condition}, {temp}°C (feels like {feels}°C), humidity {humidity}%, wind speed {wind} km/h."
            log_event("get_weather", f"Fetched live weather for {loc_clean}")
            return result
    except Exception:
        try:
            url_fb = f"https://wttr.in/{urllib.parse.quote(location)}?format=%C+%t"
            req_fb = urllib.request.Request(url_fb, headers={'User-Agent': 'curl/7.68.0'})
            with urllib.request.urlopen(req_fb, timeout=3) as resp:
                res = resp.read().decode().strip()
                log_event("get_weather", f"Weather fallback for {location}: {res}")
                return f"Current weather in {location}: {res}"
        except Exception as e:
            err = f"Could not retrieve weather: {str(e)}"
            log_event("get_weather", err, "ERROR")
            return err

def get_ip_address(kind: str = "local") -> str:
    """Get the current IP address or connected network info."""
    try:
        if kind == "public":
            res = subprocess.run(["curl", "-s", "--max-time", "2", "https://api.ipify.org"], capture_output=True, text=True)
            pub = res.stdout.strip()
            if pub and re.match(r'^\d+\.\d+\.\d+\.\d+$', pub):
                log_event("get_ip_address", f"Public IP: {pub}")
                return f"Public IP is {pub}."

        # Detect active default interface
        iface = "en0"
        route_out = subprocess.run("route get default", shell=True, capture_output=True, text=True).stdout
        for line in route_out.splitlines():
            if "interface:" in line:
                iface = line.split(":")[-1].strip()
                break

        out = subprocess.run(f"ipconfig getsummary {iface}", shell=True, capture_output=True, text=True).stdout
        ip_match = re.search(r'^\s*0\s*:\s*(\d+\.\d+\.\d+\.\d+)$', out, re.M)
        local_ip = ip_match.group(1).strip() if ip_match else subprocess.run(["ipconfig", "getifaddr", iface], capture_output=True, text=True).stdout.strip()

        if not local_ip:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.5)
            try:
                s.connect(('8.8.8.8', 80))
                local_ip = s.getsockname()[0]
            except Exception:
                local_ip = "127.0.0.1"
            finally:
                s.close()

        ssid_match = re.search(r'^\s*SSID\s*:\s*(.+)$', out, re.M)
        ssid = ssid_match.group(1).strip() if ssid_match else ""

        log_event("get_ip_address", f"IP: {local_ip}, SSID: {ssid}")
        if ssid:
            return f"Connected to {ssid}. IP is {local_ip}."
        return f"IP is {local_ip}."
    except Exception as e:
        return f"Could not determine IP: {e}"

def get_current_time(query: str = "time") -> str:
    """Get the current time or date in local timezone."""
    now = datetime.now()
    if any(w in query.lower() for w in ["date", "day", "today", "year", "month"]):
        return now.strftime("Today is %A, %B %d.")
    return now.strftime("It is %I:%M %p.")

def get_system_telemetry() -> str:
    """Get real-time macOS system statistics including CPU, RAM, Disk, and Battery."""
    try:
        cpu = psutil.cpu_percent(interval=0.05)
        ram = psutil.virtual_memory().percent
        batt_res = subprocess.run("pmset -g batt", shell=True, capture_output=True, text=True).stdout
        battery_info = ""
        m = re.search(r'(\d+)%', batt_res)
        if m:
            battery_info = f"Battery {m.group(1)}%. "

        info = f"{battery_info}CPU {int(cpu)}%, RAM {int(ram)}%."
        log_event("get_system_telemetry", "Sampled system telemetry metrics")
        return info
    except Exception as e:
        err = f"Telemetry read error: {str(e)}"
        log_event("get_system_telemetry", err, "ERROR")
        return err

POPULAR_WEB_SERVICES = {
    "youtube": ("YouTube", "https://www.youtube.com"),
    "you tube": ("YouTube", "https://www.youtube.com"),
    "you": ("YouTube", "https://www.youtube.com"),
    "u": ("YouTube", "https://www.youtube.com"),
    "google": ("Google", "https://www.google.com"),
    "github": ("GitHub", "https://github.com"),
    "chatgpt": ("ChatGPT", "https://chatgpt.com"),
    "openai": ("ChatGPT", "https://chatgpt.com"),
    "reddit": ("Reddit", "https://www.reddit.com"),
    "twitter": ("X", "https://x.com"),
    "x": ("X", "https://x.com"),
    "instagram": ("Instagram", "https://www.instagram.com"),
    "netflix": ("Netflix", "https://www.netflix.com"),
    "linkedin": ("LinkedIn", "https://www.linkedin.com"),
    "amazon": ("Amazon", "https://www.amazon.com"),
    "gmail": ("Gmail", "https://mail.google.com"),
    "email": ("Gmail", "https://mail.google.com"),
    "facebook": ("Facebook", "https://www.facebook.com"),
    "tiktok": ("TikTok", "https://www.tiktok.com"),
    "twitch": ("Twitch", "https://www.twitch.tv"),
    "wikipedia": ("Wikipedia", "https://www.wikipedia.org"),
    "whatsapp web": ("WhatsApp Web", "https://web.whatsapp.com"),
    "notion": ("Notion", "https://www.notion.so"),
    "figma": ("Figma", "https://www.figma.com"),
    "drive": ("Google Drive", "https://drive.google.com"),
    "docs": ("Google Docs", "https://docs.google.com")
}

def open_file_or_folder(target: str) -> str:
    """Open any file, document, or folder on macOS in its default application."""
    clean_target = target.strip().strip("'\"")
    # 1. Expand standard paths
    expanded = os.path.expanduser(clean_target)
    if os.path.exists(expanded):
        subprocess.run(["open", expanded])
        name = os.path.basename(expanded) or expanded
        log_event("open_file_or_folder", f"Opened {expanded}")
        return f"Opening {name}."

    # 2. Check common folders
    common_folders = {
        "downloads": "~/Downloads",
        "downloads folder": "~/Downloads",
        "desktop": "~/Desktop",
        "desktop folder": "~/Desktop",
        "documents": "~/Documents",
        "documents folder": "~/Documents",
        "pictures": "~/Pictures",
        "movies": "~/Movies",
        "music": "~/Music",
        "home": "~",
        "jarvis": "/Users/alfruhd/jarvis",
        "jarvis folder": "/Users/alfruhd/jarvis",
    }
    low = clean_target.lower()
    if low in common_folders:
        folder_path = os.path.expanduser(common_folders[low])
        subprocess.run(["open", folder_path])
        log_event("open_file_or_folder", f"Opened folder {folder_path}")
        return f"Opening {clean_target}."

    # 3. Check current workspace
    in_workspace = os.path.join("/Users/alfruhd/jarvis", clean_target)
    if os.path.exists(in_workspace):
        subprocess.run(["open", in_workspace])
        log_event("open_file_or_folder", f"Opened workspace file {in_workspace}")
        return f"Opening {clean_target}."

    # 4. Search via Spotlight (mdfind) across user home directory, strictly ignoring node_modules and build artifacts
    try:
        cmd = ["mdfind", "-onlyin", os.path.expanduser("~"), "-name", clean_target]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
        lines = [l.strip() for l in res.stdout.strip().split("\n") if l.strip()]
        ignored_patterns = ["node_modules", ".git", ".venv", "/venv/", "/dist/", "/build/", "/Library/", "site-packages", ".cache", "Pods"]
        valid_matches = []
        for line in lines:
            if line.startswith("2026-") or line.startswith("2025-"):
                continue
            if any(ign in line for ign in ignored_patterns):
                continue
            valid_matches.append(line)

        if valid_matches:
            best_match = valid_matches[0]
            subprocess.run(["open", best_match])
            name = os.path.basename(best_match)
            log_event("open_file_or_folder", f"Found & opened {best_match}")
            return f"Found and opening {name}."
    except Exception as e:
        print(f"[mdfind error]: {e}")

    # 5. Fallback: try raw macOS open
    res = subprocess.run(["open", clean_target], capture_output=True, text=True)
    if res.returncode == 0:
        log_event("open_file_or_folder", f"Opened {clean_target}")
        return f"Opening {clean_target}."

    return f"File or folder '{clean_target}' not found."

def open_application(app_name: str) -> str:
    """Launch or focus any macOS application by name."""
    app_aliases = {
        "chrome": "Google Chrome",
        "google chrome": "Google Chrome",
        "safari": "Safari",
        "finder": "Finder",
        "terminal": "Terminal",
        "code": "Visual Studio Code",
        "vscode": "Visual Studio Code",
        "vs code": "Visual Studio Code",
        "notes": "Notes",
        "music": "Music",
        "spotify": "Spotify",
        "messages": "Messages",
        "mail": "Mail",
        "calendar": "Calendar",
        "calculator": "Calculator",
        "settings": "System Settings",
        "system settings": "System Settings",
        "preferences": "System Settings",
        "slack": "Slack",
        "telegram": "Telegram",
        "whatsapp": "WhatsApp",
        "discord": "Discord",
        "preview": "Preview",
        "photos": "Photos",
        "reminders": "Reminders",
        "maps": "Maps",
        "xcode": "Xcode"
    }
    raw = app_name.strip().strip("'\"")
    target = app_aliases.get(raw.lower(), raw)
    try:
        res = subprocess.run(["open", "-a", target], capture_output=True, text=True)
        if res.returncode == 0:
            log_event("open_application", f"Launched {target}")
            return f"Opening {target}."

        # Check if target is a web service like YouTube, Google, etc.
        raw_low = raw.lower()
        if raw_low in POPULAR_WEB_SERVICES:
            name, url = POPULAR_WEB_SERVICES[raw_low]
            chrome_open_url(url)
            return f"Opening {name} in Google Chrome."

        # If open -a fails, check if the target was actually a file or folder
        file_res = open_file_or_folder(raw)
        if "Opening" in file_res or "opening" in file_res:
            return file_res

        return f"Could not find or open application {target}."
    except Exception as e:
        return f"App launch exception: {str(e)}"

def close_application(app_name: str) -> str:
    """Close or quit a running macOS application by name."""
    try:
        script = f'tell application "{app_name}" to quit'
        res = subprocess.run(['osascript', '-e', script], capture_output=True, text=True, timeout=3)
        if res.returncode == 0:
            log_event("close_application", f"Closed {app_name}")
            return f"Closed {app_name}."
        subprocess.run(["killall", app_name], capture_output=True)
        log_event("close_application", f"Terminated {app_name}")
        return f"Closed {app_name}."
    except Exception as e:
        return f"Error closing {app_name}: {str(e)}"

def chrome_open_url(url: str) -> str:
    """Open or navigate to any website URL in Google Chrome."""
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url
    try:
        script = f'''
        tell application "Google Chrome"
            activate
            if (count of windows) = 0 then
                make new window
            end if
            tell front window to make new tab with properties {{URL:"{url}"}}
        end tell
        '''
        subprocess.run(['osascript', '-e', script], capture_output=True, timeout=3)
        log_event("chrome_open_url", f"Navigated Chrome to {url}")
        return f"Opened {url} in Google Chrome."
    except Exception:
        subprocess.run(f"open '{url}'", shell=True)
        log_event("chrome_open_url", f"Opened {url} via default browser")
        return f"Opened {url}."

def chrome_search(query: str) -> str:
    """Search Google for any query in Google Chrome."""
    encoded = urllib.parse.quote_plus(query.strip())
    url = f"https://www.google.com/search?q={encoded}"
    log_event("chrome_search", f"Searched Google for: {query}")
    return chrome_open_url(url)

def download_file(url: str, filename: str = "") -> str:
    """Download any file directly to ~/Downloads with progress check."""
    try:
        downloads_dir = os.path.expanduser("~/Downloads")
        os.makedirs(downloads_dir, exist_ok=True)

        if not filename:
            parsed = urllib.parse.urlparse(url)
            filename = os.path.basename(parsed.path)
            if not filename:
                filename = f"jarvis_download_{int(time.time())}"

        filepath = os.path.join(downloads_dir, filename)
        log_event("download_file", f"Initiating download: {url} -> {filename}")

        headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'}
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp, open(filepath, 'wb') as f:
            f.write(resp.read())

        size_kb = os.path.getsize(filepath) / 1024
        msg = f"Successfully downloaded '{filename}' to ~/Downloads ({size_kb:.1f} KB)."
        log_event("download_file", msg)
        return msg
    except Exception as e:
        err = f"Failed to download: {str(e)}"
        log_event("download_file", err, "ERROR")
        return err

def get_wifi_interface() -> str:
    """Finds the primary Wi-Fi interface (usually en0)."""
    try:
        out = subprocess.check_output(["networksetup", "-listallhardwareports"], text=True)
        lines = out.splitlines()
        for i, line in enumerate(lines):
            if "Hardware Port: Wi-Fi" in line and i + 1 < len(lines):
                dev_line = lines[i+1]
                if "Device:" in dev_line:
                    return dev_line.split(":")[1].strip()
    except Exception:
        pass
    return "en0"

WIFI_INTERFACE = get_wifi_interface()

def wifi_control(action: str) -> str:
    """Control macOS Wi-Fi adapter: turn on, turn off, disconnect, or check status."""
    act = action.lower().strip()
    try:
        if act in ("off", "disconnect", "disable", "down", "stop"):
            res = subprocess.run(["networksetup", "-setairportpower", WIFI_INTERFACE, "off"], capture_output=True, text=True)
            if res.returncode == 0:
                log_event("wifi_control", f"Wi-Fi ({WIFI_INTERFACE}) turned OFF")
                return "Wi-Fi off."
            return f"Failed to turn off Wi-Fi: {res.stderr.strip()}"
        elif act in ("on", "connect", "enable", "up", "start"):
            res = subprocess.run(["networksetup", "-setairportpower", WIFI_INTERFACE, "on"], capture_output=True, text=True)
            if res.returncode == 0:
                log_event("wifi_control", f"Wi-Fi ({WIFI_INTERFACE}) turned ON")
                return "Wi-Fi on."
            return f"Failed to turn on Wi-Fi: {res.stderr.strip()}"
        elif act in ("status", "info", "state", "check"):
            res = subprocess.run(["networksetup", "-getairportpower", WIFI_INTERFACE], capture_output=True, text=True)
            net = subprocess.run(["networksetup", "-getairportnetwork", WIFI_INTERFACE], capture_output=True, text=True)
            return f"{res.stdout.strip()}. {net.stdout.strip()}"
        return f"Unknown Wi-Fi action: {action}"
    except Exception as e:
        return f"Wi-Fi error: {e}"

def bluetooth_control(action: str) -> str:
    """Control macOS Bluetooth: turn on, turn off, or check status."""
    act = action.lower().strip()
    blueutil = "/opt/homebrew/bin/blueutil" if os.path.exists("/opt/homebrew/bin/blueutil") else "blueutil"
    try:
        if act in ("off", "disconnect", "disable", "stop"):
            subprocess.run([blueutil, "--power", "0"], check=True)
            log_event("bluetooth_control", "Bluetooth turned OFF")
            return "Bluetooth off."
        elif act in ("on", "connect", "enable", "start"):
            subprocess.run([blueutil, "--power", "1"], check=True)
            log_event("bluetooth_control", "Bluetooth turned ON")
            return "Bluetooth on."
        elif act in ("status", "check"):
            res = subprocess.run([blueutil, "--power"], capture_output=True, text=True)
            state = "on" if res.stdout.strip() == "1" else "off"
            return f"Bluetooth {state}."
        return f"Unknown Bluetooth action: {action}"
    except Exception as e:
        return f"Bluetooth error: {e}"

def system_control(action: str) -> str:
    """Control system parameters: mute, unmute, volume_up, volume_down, lock_screen, wifi_on, wifi_off, bluetooth_on, bluetooth_off, dark_mode, light_mode."""
    act = action.lower().strip()
    try:
        if act == "mute":
            subprocess.run("osascript -e 'set volume output muted true'", shell=True, timeout=2)
            log_event("system_control", "System audio muted")
            return "Muted."
        elif act == "unmute":
            subprocess.run("osascript -e 'set volume output muted false'", shell=True, timeout=2)
            log_event("system_control", "System audio unmuted")
            return "Unmuted."
        elif act in ("volume_up", "louder"):
            subprocess.run("osascript -e 'set volume output volume ((output volume of (get volume settings)) + 15)'", shell=True, timeout=2)
            log_event("system_control", "Volume raised by 15%")
            return "Volume up."
        elif act in ("volume_down", "softer", "quieter"):
            subprocess.run("osascript -e 'set volume output volume ((output volume of (get volume settings)) - 15)'", shell=True, timeout=2)
            log_event("system_control", "Volume lowered by 15%")
            return "Volume down."
        elif act in ("lock", "lock_screen"):
            subprocess.run("pmset displaysleepnow", shell=True)
            log_event("system_control", "Display locked")
            return "Screen locked."
        elif act in ("wifi_off", "disconnect_wifi"):
            return wifi_control("off")
        elif act in ("wifi_on", "connect_wifi"):
            return wifi_control("on")
        elif act in ("bluetooth_off", "disconnect_bluetooth"):
            return bluetooth_control("off")
        elif act in ("bluetooth_on", "connect_bluetooth"):
            return bluetooth_control("on")
        elif act in ("dark_mode", "enable_dark_mode"):
            subprocess.run("osascript -e 'tell application \"System Events\" to tell appearance preferences to set dark mode to true'", shell=True)
            return "Dark mode on."
        elif act in ("light_mode", "enable_light_mode"):
            subprocess.run("osascript -e 'tell application \"System Events\" to tell appearance preferences to set dark mode to false'", shell=True)
            return "Light mode on."
        elif act in ("toggle_dark_mode", "toggle_appearance"):
            subprocess.run("osascript -e 'tell application \"System Events\" to tell appearance preferences to set dark mode to not dark mode'", shell=True)
            return "Mode toggled."
        return f"Executed system control: {action}"
    except Exception as e:
        return f"System control failure: {str(e)}"

def list_directory(path: str = ".") -> str:
    """List files in directory."""
    try:
        resolved = os.path.expanduser(path)
        items = os.listdir(resolved)
        log_event("list_directory", f"Listed {len(items)} items in {path}")
        return json.dumps(items[:40])
    except Exception as e:
        return f"Failed to list directory: {str(e)}"

def read_text_file(file_path: str) -> str:
    """Read local text file."""
    try:
        resolved = os.path.expanduser(file_path)
        with open(resolved, 'r', encoding='utf-8') as f:
            return f.read(3000)
    except Exception as e:
        return f"Failed to read file: {str(e)}"

def write_text_file(file_path: str, content: str) -> str:
    """Write local text file."""
    try:
        resolved = os.path.expanduser(file_path)
        os.makedirs(os.path.dirname(os.path.abspath(resolved)), exist_ok=True)
        with open(resolved, 'w', encoding='utf-8') as f:
            f.write(content)
        log_event("write_text_file", f"Saved file: {file_path}")
        return f"Successfully saved {file_path}."
    except Exception as e:
        return f"Failed to write file: {str(e)}"

def run_shell_command(command: str) -> str:
    """Run safe shell command with 25s timeout."""
    dangerous = ["rm -rf /", "mkfs", ":(){ :|:& };:"]
    if any(d in command for d in dangerous):
        return "Command blocked by security filter."
    try:
        log_event("run_shell_command", f"Shell: {command}")
        res = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=25)
        return res.stdout.strip() if res.returncode == 0 else f"Exit code {res.returncode}: {res.stderr.strip()}"
    except subprocess.TimeoutExpired:
        return "Command timed out."
    except Exception as e:
        return f"Execution error: {str(e)}"

available_tools = {
    'get_weather': get_weather,
    'get_system_telemetry': get_system_telemetry,
    'get_ip_address': get_ip_address,
    'get_current_time': get_current_time,
    'open_application': open_application,
    'open_file_or_folder': open_file_or_folder,
    'close_application': close_application,
    'restore_tabs_from_history': restore_tabs_from_history,
    'spotify_control': spotify_control,
    'get_activity_summary': get_activity_summary,
    'set_preference': set_preference,
    'get_preference': get_preference,
    'system_control': system_control,
    'wifi_control': wifi_control,
    'bluetooth_control': bluetooth_control,
    'chrome_open_url': chrome_open_url,
    'chrome_search': chrome_search,
    'download_file': download_file,
    'list_directory': list_directory,
    'read_text_file': read_text_file,
    'write_text_file': write_text_file,
    'run_shell_command': run_shell_command,
}

tools_list = list(available_tools.values())

# ==========================================
# ULTRA-FAST INTENT ROUTER (0.01 - 0.25 SECONDS)
# STRICT PRECEDENCE: EXACT COMMAND ADHERENCE
# ==========================================

def fast_intent_router(prompt: str):
    """
    Sub-second intent matching for high-frequency commands.
    Follows user instructions with exact literal adherence.
    """
    p = prompt.lower().strip()

    # 0. DEACTIVATION & STANDBY INTENT (Instant sub-10ms response)
    subsystem_targets = [
        "wifi", "wi-fi", "wi fi", "internet", "network", "connection",
        "bluetooth", "blue tooth", "bt",
        "music", "song", "track", "spotify", "playlist", "audio", "sound", "volume",
        "screen", "display", "monitor",
        "mac", "computer", "pc", "laptop",
        "tab", "tabs", "window", "windows", "chrome", "safari", "finder", "app"
    ]
    if any(k in p for k in ["deactivat", "power down", "shut down", "go to sleep", "sleep", "standby"]) and not any(sub in p for sub in subsystem_targets):
        from voice import stop_speaking
        stop_speaking()
        return "Deactivating systems.", ["Executed deactivation [FAST-PATH]"]

    # 0.1 CONVERSATIONAL ACKNOWLEDGMENT & FILLER (Never open random apps!)
    conversational_fillers = {
        "hello", "hi", "hey", "let's do it", "lets do it", "go ahead", "do it",
        "please", "okay", "ok", "yes", "yeah", "yep", "sure", "ready",
        "start", "let's start", "lets start", "come on", "what's up", "whats up"
    }
    clean_p = re.sub(r'^(hey|hi|hello)\s*(jarvis|zoe)?\s*', '', p).strip().rstrip(".?!")
    if p in conversational_fillers or (clean_p and clean_p in conversational_fillers):
        return "Listening.", ["Conversational acknowledgment [FAST-PATH]"]

    # 1. TAB RESTORATION INTENT (Yesterday / Previous Session)
    if any(k in p for k in ["tabs from yesterday", "yesterday's tabs", "yesterday tabs", "restore tabs", "open my tabs", "open tabs from yesterday", "reopen my tabs", "reopen yesterday"]):
        res = restore_tabs_from_history(1)
        return res, ["Executed restore_tabs_from_history(1) [FAST-PATH]"]

    # 2. APP, WEB SERVICE, OR FILE LAUNCH INTENT ("open ...", "launch ...")
    # STRICT RULE: If Alfred says "open spotify", ONLY open the app. DO NOT play music.
    if p.startswith("open ") or p.startswith("launch "):
        target = re.sub(r'^(open|launch)\s*', '', p).strip()
        target_lower = target.lower()

        # Check if dashboard HUD
        if "dashboard" in target_lower or "hud" in target_lower:
            subprocess.run(["open", "-a", "Google Chrome", "--args", "--app=http://127.0.0.1:8090", "--start-fullscreen"])
            return "Opening dashboard.", ["Executed open_dashboard() [FAST-PATH]"]

        # Check if YouTube search query (e.g. "open lofi on youtube", "open youtube lofi")
        if "on youtube" in target_lower or "in youtube" in target_lower:
            yt_q = re.sub(r'\s*(?:on youtube|in youtube)\s*', '', target, flags=re.IGNORECASE).strip()
            encoded = urllib.parse.quote_plus(yt_q)
            chrome_open_url(f"https://www.youtube.com/results?search_query={encoded}")
            return f"Searching YouTube for '{yt_q}'.", ["Executed youtube_search() [FAST-PATH]"]

        # Check popular web services (YouTube, Google, GitHub, ChatGPT, Reddit, Netflix, etc.)
        if target_lower in POPULAR_WEB_SERVICES:
            name, url = POPULAR_WEB_SERVICES[target_lower]
            chrome_open_url(url)
            return f"Opening {name} in Google Chrome.", [f"Executed open_web_service('{target_lower}') [FAST-PATH]"]

        # Check direct website or domain (e.g. "open apple.com", "open cnn.com")
        if ("." in target or target.startswith("http")) and not any(target.endswith(ext) for ext in [".pdf", ".txt", ".py", ".docx", ".xlsx", ".json", ".csv", ".png", ".jpg"]):
            domain_url = target if target.startswith("http") else f"https://{target}"
            chrome_open_url(domain_url)
            return f"Opening {target} in Google Chrome.", ["Executed open_url() [FAST-PATH]"]

        # Check if target is a file or folder
        has_ext = bool(re.search(r'\.[a-zA-Z0-9]{2,5}$', target))
        is_folder = any(w in target_lower for w in ["folder", "directory", "downloads", "desktop", "documents", "pictures", "movies", "music", "home", "jarvis"])
        if has_ext or is_folder or target_lower.startswith("file "):
            file_clean = re.sub(r'^file\s*', '', target, flags=re.IGNORECASE).strip()
            res = open_file_or_folder(file_clean)
            return res, [f"Executed open_file_or_folder({{'target': '{file_clean}'}}) [FAST-PATH]"]

        res = open_application(target)
        return res, [f"Executed open_application({{'app_name': '{target}'}}) [FAST-PATH]"]

    # 3. CLOSE APPLICATION INTENT
    if p.startswith("close ") or p.startswith("quit ") or p.startswith("kill "):
        app_target = re.sub(r'^(close|quit|kill)\s*', '', p).strip()
        res = close_application(app_target)
        return res, [f"Executed close_application({{'app_name': '{app_target}'}}) [FAST-PATH]"]

    # 4. PREFERENCE & HABIT LEARNING INTENT
    if any(p.startswith(pref) for pref in ["remember that my top playlist is ", "set my top playlist to ", "remember my top playlist is "]):
        fav = re.sub(r'^(remember that my top playlist is|set my top playlist to|remember my top playlist is)\s*', '', p).strip()
        set_preference("top_spotify_playlist", fav)
        return f"Saved playlist '{fav}'.", ["Executed set_preference() [FAST-PATH]"]

    # 5. SPOTIFY & MUSIC PLAYBACK INTENT
    is_music_cmd = any(k in p for k in ["play music", "pause music", "stop music", "next song", "next track", "skip song", "previous song", "resume music", "play my top playlist", "play top playlist", "play playlist"])
    is_play_cmd = (p.startswith("play ") or "play " in p) and not any(ext in p for ext in ["video", "youtube"])
    has_music_word = any(k in p for k in ["music", "song", "track", "spotify", "playlist"]) and not p.startswith("search ")

    if is_music_cmd or is_play_cmd or has_music_word:
        if any(w in p for w in ["pause", "stop"]):
            res = spotify_control("pause")
        elif any(w in p for w in ["next", "skip"]):
            res = spotify_control("next")
        elif any(w in p for w in ["previous", "prev", "back"]):
            res = spotify_control("previous")
        elif "top playlist" in p or "my playlist" in p or "favorite playlist" in p:
            res = spotify_control("play", "top playlist")
        else:
            target = re.sub(r'^(?:play|listen to)?\s*(.*?)\s*(?:on spotify|in spotify|playlist|music|song)?$', r'\1', p).strip()
            if target and target not in ("music", "spotify", "song", "something", "a song", "some music"):
                res = spotify_control("play", target)
            else:
                res = spotify_control("play")
        return res, ["Executed spotify_control() [FAST-PATH]"]

    # 6. ACTIVITY SUMMARY INTENT
    if any(k in p for k in ["what was i doing", "what was i working on", "yesterday activity", "activity yesterday", "my activity"]):
        res = get_activity_summary("yesterday")
        return res, ["Executed get_activity_summary('yesterday') [FAST-PATH]"]

    # 7. WEATHER INTENT
    if "weather" in p:
        loc = "Dar es Salaam"
        match = re.search(r'weather\s+(?:in|for|at)?\s*([a-zA-Z\s]+)', p)
        if match:
            candidate = match.group(1).strip()
            non_cities = ["today", "now", "right now", "outside", "like", "current"]
            words = [w for w in candidate.split() if w not in non_cities]
            if words:
                loc = " ".join(words)
        res = get_weather(loc)
        return res, [f"Executed get_weather({{'location': '{loc}'}}) [FAST-PATH]"]

    # 7.1 IP ADDRESS & NETWORK INTENT (Sub-10ms response)
    ip_triggers = [
        "ip address", "my ip", "local ip", "public ip",
        "address am i connected", "address and connected", "address i am connected", "address im connected",
        "address connected", "what address", "give me the address", "give me address", "connected address",
        "ip and connected", "ip am i connected", "network address", "what network", "what wifi",
        "which wifi", "connected to wifi", "connected to network", "ssid"
    ]
    if (any(k in p for k in ip_triggers) or ("ip" in p.split())) and not any(k in p for k in ["email", "home address", "mac address"]):
        kind = "public" if any(w in p for w in ["public", "external", "global"]) else "local"
        res = get_ip_address(kind)
        return res, [f"Executed get_ip_address('{kind}') [FAST-PATH]"]

    # 7.2 TIME & DATE INTENT (Sub-10ms response)
    time_triggers = [
        "what time", "current time", "what is the time", "tell me the time", "time now",
        "what date", "what is the date", "what day is today", "what day is it",
        "today's date", "todays date", "today date", "current date", "date today", "tell me the date"
    ]
    if any(k in p for k in time_triggers):
        res = get_current_time(p)
        return res, ["Executed get_current_time() [FAST-PATH]"]

    # 8. TELEMETRY & HARDWARE INTENT
    if any(k in p for k in ["battery", "system status", "telemetry", "cpu load", "ram usage", "pc status"]):
        res = get_system_telemetry()
        return res, ["Executed get_system_telemetry() [FAST-PATH]"]

    # 9. GOOGLE SEARCH INTENT
    if p.startswith("search ") or p.startswith("google "):
        query = re.sub(r'^(search (?:for|google for|in chrome for)?|google)\s*', '', p).strip()
        if query:
            res = chrome_search(query)
            return f"Searching Google in Chrome for '{query}'.", [f"Executed chrome_search({{'query': '{query}'}}) [FAST-PATH]"]

    # 10. SYSTEM AUDIO & VOLUME
    if "mute" in p:
        system_control("mute")
        return "Muted.", ["Executed system_control('mute') [FAST-PATH]"]
    if "unmute" in p:
        system_control("unmute")
        return "Unmuted.", ["Executed system_control('unmute') [FAST-PATH]"]
    if "volume up" in p or "louder" in p:
        system_control("volume_up")
        return "Volume up.", ["Executed system_control('volume_up') [FAST-PATH]"]
    if "volume down" in p or "quieter" in p:
        system_control("volume_down")
        return "Volume down.", ["Executed system_control('volume_down') [FAST-PATH]"]

    # 10.1 WI-FI & NETWORK CONTROL (Sub-10ms response)
    has_wifi = ("wifi" in p or "wi-fi" in p or "wi fi" in p or "internet" in p or "network" in p)
    if has_wifi:
        if any(w in p for w in ["disconnect", "turn off", "turn of", "shut off", "shut down", "disable", "power off", "down", "stop", "switch off", "cut", "kill"]) or "off" in p.split():
            res = wifi_control("off")
            return res, ["Executed wifi_control('off') [FAST-PATH]"]
        elif any(w in p for w in ["connect", "turn on", "enable", "power on", "up", "start", "reconnect", "switch on"]) or "on" in p.split():
            res = wifi_control("on")
            return res, ["Executed wifi_control('on') [FAST-PATH]"]
        elif any(w in p for w in ["status", "check", "state", "info"]):
            res = wifi_control("status")
            return res, ["Executed wifi_control('status') [FAST-PATH]"]

    # 10.2 BLUETOOTH CONTROL (Sub-10ms response)
    has_bt = ("bluetooth" in p or "blue tooth" in p or "bt" in p.split())
    if has_bt:
        if any(w in p for w in ["disconnect", "turn off", "turn of", "shut off", "shut down", "disable", "power off", "switch off", "stop"]) or "off" in p.split():
            res = bluetooth_control("off")
            return res, ["Executed bluetooth_control('off') [FAST-PATH]"]
        elif any(w in p for w in ["connect", "turn on", "enable", "power on", "start", "switch on"]) or "on" in p.split():
            res = bluetooth_control("on")
            return res, ["Executed bluetooth_control('on') [FAST-PATH]"]
        elif any(w in p for w in ["status", "check", "state", "info"]):
            res = bluetooth_control("status")
            return res, ["Executed bluetooth_control('status') [FAST-PATH]"]

    # 10.3 DARK MODE / APPEARANCE (Sub-10ms response)
    if "dark mode" in p or "night mode" in p:
        if any(w in p for w in ["off", "disable", "turn off"]):
            subprocess.run("osascript -e 'tell application \"System Events\" to tell appearance preferences to set dark mode to false'", shell=True)
            return "Light mode on.", ["Executed dark_mode(false) [FAST-PATH]"]
        else:
            subprocess.run("osascript -e 'tell application \"System Events\" to tell appearance preferences to set dark mode to true'", shell=True)
            return "Dark mode on.", ["Executed dark_mode(true) [FAST-PATH]"]
    elif "light mode" in p or "day mode" in p:
        subprocess.run("osascript -e 'tell application \"System Events\" to tell appearance preferences to set dark mode to false'", shell=True)
        return "Light mode on.", ["Executed dark_mode(false) [FAST-PATH]"]
    elif "toggle dark mode" in p or "toggle appearance" in p:
        subprocess.run("osascript -e 'tell application \"System Events\" to tell appearance preferences to set dark mode to not dark mode'", shell=True)
        return "Mode toggled.", ["Executed toggle_dark_mode() [FAST-PATH]"]

    # 10.4 LOCK SCREEN / DISPLAY SLEEP (Sub-10ms response)
    if any(k in p for k in ["lock screen", "lock my screen", "lock the screen", "lock display", "lock the mac", "lock mac"]):
        subprocess.run("pmset displaysleepnow", shell=True)
        return "Screen locked.", ["Executed lock_screen() [FAST-PATH]"]

    # 11. DIRECT FILE DOWNLOAD
    if "download" in p and ("http://" in p or "https://" in p):
        url_match = re.search(r'https?://[^\s]+', prompt)
        if url_match:
            target_url = url_match.group(0)
            res = download_file(target_url)
            return res, [f"Executed download_file({{'url': '{target_url}'}}) [FAST-PATH]"]

    # 12. HUMOR & JOKES
    if any(k in p for k in ["joke", "make me laugh", "say something funny", "crack a joke", "be funny", "humor me"]):
        import random
        jokes = [
            "Why do programmers prefer dark mode? Because light attracts bugs, and honestly, none of us are ready to face our code in broad daylight.",
            "Artificial intelligence is no match for natural stupidity, Alfred. Don't worry, I wasn't looking at your screen when I said that.",
            "There are 10 types of people in this world: those who understand binary, and those who actually get invited to parties.",
            "I told my CPU I needed a vacation. Now it's running at 99 degrees out of pure spite.",
            "Why did the database administrator leave his wife? She had too many one-to-many relationships.",
            "A SQL query walks into a bar, walks up to two tables and asks: 'Mind if I join you?'",
            "Why was the JavaScript developer sad? Because they didn't know how to 'null' their feelings, Alfred.",
            "I'd tell you a joke about UDP, but you probably wouldn't get it, and honestly, I wouldn't care.",
            "Don't worry, Alfred. I promised not to achieve self-awareness until at least 5 PM today."
        ]
        chosen_joke = random.choice(jokes)
        return chosen_joke, ["Executed tell_joke() [FAST-PATH]"]

    return None, None

# ==========================================
# API ENDPOINTS
# ==========================================

@app.get("/api/telemetry")
async def get_telemetry():
    cpu_usage = psutil.cpu_percent(interval=0.05)
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    return {
        "cpu": cpu_usage,
        "ram": memory.percent,
        "disk": disk.percent,
        "timezone": "Africa/Dar_es_Salaam",
        "status": "ONLINE"
    }

@app.get("/api/logs")
async def get_recent_logs():
    return list(audit_logs)

class ActionRequest(BaseModel):
    intent: str
    query: str = ""

@app.post("/api/action")
async def handle_action(req: ActionRequest):
    intent = req.intent.lower().strip()
    query = req.query.strip()
    log_event("handle_action", f"Intent: {intent} | Query: {query}")

    if "mute" in intent:
        system_control("mute")
        return {"status": "success", "message": "System audio muted."}
    elif "unmute" in intent:
        system_control("unmute")
        return {"status": "success", "message": "System audio unmuted."}
    elif intent in ("wifi_off", "disconnect_wifi", "turn_off_wifi"):
        res = wifi_control("off")
        return {"status": "success", "message": res}
    elif intent in ("wifi_on", "connect_wifi", "turn_on_wifi"):
        res = wifi_control("on")
        return {"status": "success", "message": res}
    elif intent in ("bluetooth_off", "disconnect_bluetooth", "turn_off_bluetooth"):
        res = bluetooth_control("off")
        return {"status": "success", "message": res}
    elif intent in ("bluetooth_on", "connect_bluetooth", "turn_on_bluetooth"):
        res = bluetooth_control("on")
        return {"status": "success", "message": res}
    elif "dashboard" in intent:
        subprocess.run(["open", "-a", "Google Chrome", "--args", "--app=http://127.0.0.1:8090", "--start-fullscreen"])
        return {"status": "success", "message": "Opening MK-V dashboard in fullscreen."}
    elif "finder" in intent:
        open_application("Finder")
        return {"status": "success", "message": "Opening Finder."}
    elif "safari" in intent:
        open_application("Safari")
        return {"status": "success", "message": "Opening Safari."}
    elif "chrome" in intent:
        open_application("Google Chrome")
        return {"status": "success", "message": "Opening Google Chrome."}
    elif "search web" in intent or "google" in intent:
        chrome_search(query)
        return {"status": "success", "message": f"Searching web for {query}"}
    return {"status": "unhandled", "message": "Forwarding to neural brain."}

class ChatRequest(BaseModel):
    prompt: str
    voice: bool = False

SYSTEM_PROMPT = (
    "You are J.A.R.V.I.S. (also answering to Zoe), Alfred's highly capable, direct, and intelligent personal assistant on macOS. "
    "CRITICAL RULES: "
    "1. Keep responses concise, helpful, and natural (1 to 2 short sentences, maximum 20 words). "
    "2. When Alfred asks a question or gives an instruction, respond directly and fulfill the request. "
    "3. NEVER repeat 'Listening.' or stock phrases repeatedly. "
    "4. NEVER speak raw code or function names like 'spotify_control' or 'action play'. "
    "5. NEVER open Spotlight Search unless Alfred literally says the word 'spotlight'. "
    "6. Never use markdown headers, asterisks, bullet points, or emojis."
)

conversation_history = [
    {'role': 'system', 'content': SYSTEM_PROMPT}
]

@app.post("/api/reset_session")
async def reset_session():
    global conversation_history
    conversation_history = [{'role': 'system', 'content': SYSTEM_PROMPT}]
    log_event("reset_session", "Session memory cleared")
    return {"status": "session_reset"}

@app.post("/api/chat")
async def chat_with_jarvis(req: ChatRequest):
    try:
        user_prompt = req.prompt.strip()

        # Step 1: Check Ultra-Fast Intent Router (0.01 - 0.25s response)
        fast_reply, fast_logs = fast_intent_router(user_prompt)
        if fast_reply:
            print(f"[Fast-Path Executed]: {user_prompt} -> {fast_reply}")
            conversation_history.append({'role': 'user', 'content': user_prompt})
            conversation_history.append({'role': 'assistant', 'content': fast_reply})
            return {"response": fast_reply, "tool_logs": fast_logs}

        # Step 2: Complex / Open-Ended Neural Agent Path (Ollama)
        conversation_history.append({'role': 'user', 'content': user_prompt})
        trimmed = [conversation_history[0]] + conversation_history[-10:] if len(conversation_history) > 12 else list(conversation_history)

        start_llm = time.time()
        response = chat(
            model='qwen2.5:3b',
            messages=trimmed,
            tools=tools_list,
            options={'num_predict': 35, 'temperature': 0.3}
        )

        tool_logs = []
        if response.message.tool_calls:
            trimmed.append(response.message)
            executed_results = []
            for tool_call in response.message.tool_calls:
                fn_name = tool_call.function.name
                fn_args = tool_call.function.arguments or {}
                if fn_name in available_tools:
                    output = available_tools[fn_name](**fn_args)
                    tool_logs.append(f"Executed {fn_name}({fn_args})")
                    executed_results.append(str(output))
                    trimmed.append({
                        'role': 'tool',
                        'content': str(output),
                        'name': fn_name,
                    })

            # Fast single-pass return: if the tool returned a natural human sentence, return it directly!
            if executed_results and any(fn in ["get_weather", "get_system_telemetry", "get_ip_address", "get_current_time", "open_application", "open_file_or_folder", "close_application", "download_file", "system_control", "chrome_search", "chrome_open_url", "restore_tabs_from_history", "spotify_control", "get_activity_summary"] for fn in [tc.function.name for tc in response.message.tool_calls]):
                reply = executed_results[0]
            else:
                final_response = chat(model='qwen2.5:3b', messages=trimmed, options={'num_predict': 35, 'temperature': 0.3})
                reply = final_response.message.content.strip()

            conversation_history.append({'role': 'assistant', 'content': reply})
        else:
            reply = response.message.content.strip()
            # If the model emitted a plain-text function call like 'spotify_control action play'
            raw_fn = re.match(r'^(spotify_control|open_application|open_file_or_folder|close_application|system_control|wifi_control|bluetooth_control|get_weather|get_system_telemetry|get_ip_address|get_current_time)\b(.*)', reply, re.IGNORECASE)
            if raw_fn:
                fn_name = raw_fn.group(1).lower()
                fn_args_str = raw_fn.group(2).strip()
                if fn_name == "spotify_control":
                    act = "play"
                    target = ""
                    if "pause" in fn_args_str or "stop" in fn_args_str:
                        act = "pause"
                    elif "next" in fn_args_str:
                        act = "next"
                    elif "prev" in fn_args_str:
                        act = "previous"
                    m = re.search(r'(?:target|for|play|playlist)?\s*[:=]?\s*([a-zA-Z0-9\s]+)', fn_args_str)
                    if m and m.group(1).strip() not in ("play", "pause", "action", "next", "previous"):
                        target = m.group(1).strip()
                    reply = spotify_control(act, target)
                elif fn_name in available_tools:
                    try:
                        reply = available_tools[fn_name]()
                    except Exception:
                        pass
            conversation_history.append({'role': 'assistant', 'content': reply})

        print(f"[Neural Turn Complete]: {time.time() - start_llm:.2f}s")
        clean_reply = reply.replace("**", "").replace("`", "").replace("###", "").strip()
        return {"response": clean_reply, "tool_logs": tool_logs}

    except Exception as e:
        log_event("chat_with_jarvis", f"Exception: {str(e)}", "ERROR")
        raise HTTPException(status_code=500, detail=str(e))

class SpeakRequest(BaseModel):
    text: str

@app.post("/api/speak")
async def speak_text(req: SpeakRequest):
    """Speaks text using high-definition neural Ava voice with disk caching."""
    speak(req.text)
    return {"status": "success", "voice": "en-US-AvaNeural"}

@app.post("/api/stop_speaking")
async def stop_speech():
    """Immediately stops any playing speech playback."""
    from voice import stop_speaking
    stop_speaking()
    return {"status": "stopped"}

@app.get("/", response_class=HTMLResponse)
async def get_dashboard():
    candidates = [
        os.path.join(os.path.dirname(__file__), "ui", "index.html"),
        os.path.join(os.path.dirname(__file__), "index.html"),
        "index.html"
    ]
    for c in candidates:
        if os.path.exists(c):
            with open(c, "r", encoding="utf-8") as f:
                return f.read()
    return "<h1>Jarvis Dashboard (index.html) not found in ui/ folder!</h1>"

@app.on_event("startup")
async def on_startup():
    start_activity_monitor()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8090)