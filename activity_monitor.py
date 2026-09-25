import os
import sqlite3
import subprocess
import threading
import time
import urllib.parse
from datetime import datetime, timedelta

MEMORY_DIR = os.path.expanduser("~/.jarvis_memory")
os.makedirs(MEMORY_DIR, exist_ok=True)
DB_PATH = os.path.join(MEMORY_DIR, "jarvis_memory.db")

def init_db():
    """Initializes the persistent activity & preference SQLite database."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tab_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            timestamp REAL,
            title TEXT,
            url TEXT,
            browser TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS app_activity (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            timestamp REAL,
            app_name TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_preferences (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at REAL
        )
    ''')
    # Seed default top playlist if not set
    cursor.execute("SELECT value FROM user_preferences WHERE key = 'top_spotify_playlist'")
    if not cursor.fetchone():
        cursor.execute("INSERT INTO user_preferences (key, value, updated_at) VALUES (?, ?, ?)", ('top_spotify_playlist', "Today's Top Hits", time.time()))
    # Seed yesterday's tabs if completely empty so Alfred can test restoring tabs immediately
    cursor.execute("SELECT COUNT(*) FROM tab_history")
    if cursor.fetchone()[0] == 0:
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        sample_tabs = [
            ("GitHub - Alfred Projects", "https://github.com", "Google Chrome"),
            ("YouTube - Tech & Music", "https://youtube.com", "Google Chrome"),
            ("Google", "https://google.com", "Google Chrome")
        ]
        for t, u, b in sample_tabs:
            cursor.execute("INSERT INTO tab_history (date, timestamp, title, url, browser) VALUES (?, ?, ?, ?, ?)", (yesterday, time.time() - 86400, t, u, b))

    conn.commit()
    conn.close()

init_db()

# ==========================================
# 1. BROWSER TAB MONITORING & RESTORATION
# ==========================================

def get_open_chrome_tabs() -> list:
    """Uses AppleScript to query all currently open tabs in Google Chrome."""
    script = '''
    if application "Google Chrome" is running then
        tell application "Google Chrome"
            set tabInfo to ""
            repeat with w in windows
                repeat with t in tabs of w
                    set tabInfo to tabInfo & (title of t) & "|||" & (URL of t) & "\n"
                end repeat
            end repeat
            return tabInfo
        end tell
    else
        return ""
    end if
    '''
    try:
        res = subprocess.run(['osascript', '-e', script], capture_output=True, text=True, timeout=2)
        lines = res.stdout.strip().split('\n')
        tabs = []
        for line in lines:
            if "|||" in line:
                title, url = line.split("|||", 1)
                title = title.strip()
                url = url.strip()
                if url and not url.startswith("chrome://") and not url.startswith("http://127.0.0.1:8090"):
                    tabs.append({"title": title, "url": url, "browser": "Google Chrome"})
        return tabs
    except Exception as e:
        print(f"[Tab Monitor Error]: {e}")
        return []

def snapshot_tabs():
    """Saves current open tabs to history database, avoiding immediate duplicates."""
    tabs = get_open_chrome_tabs()
    if not tabs:
        return

    today = datetime.now().strftime("%Y-%m-%d")
    now = time.time()

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("SELECT url FROM tab_history WHERE date = ? AND timestamp > ?", (today, now - 1800))
    recent_urls = {row[0] for row in cursor.fetchall()}

    for tab in tabs:
        if tab['url'] not in recent_urls:
            cursor.execute(
                "INSERT INTO tab_history (date, timestamp, title, url, browser) VALUES (?, ?, ?, ?, ?)",
                (today, now, tab['title'], tab['url'], tab['browser'])
            )
    conn.commit()
    conn.close()

def restore_tabs_from_history(day_offset: int = 1) -> str:
    """
    Opens all unique tabs saved from yesterday (or last recorded active day).
    """
    target_date = (datetime.now() - timedelta(days=day_offset)).strftime("%Y-%m-%d")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("SELECT title, url FROM tab_history WHERE date = ? ORDER BY timestamp ASC", (target_date,))
    rows = cursor.fetchall()

    if not rows:
        cursor.execute("SELECT DISTINCT date FROM tab_history WHERE date < ? ORDER BY date DESC LIMIT 1", (datetime.now().strftime("%Y-%m-%d"),))
        latest_date_row = cursor.fetchone()
        if latest_date_row:
            target_date = latest_date_row[0]
            cursor.execute("SELECT title, url FROM tab_history WHERE date = ? ORDER BY timestamp ASC", (target_date,))
            rows = cursor.fetchall()

    conn.close()

    if not rows:
        return "I don't have any saved browser tabs from yesterday or earlier sessions to restore, Alfred."

    unique_tabs = []
    seen = set()
    for title, url in rows:
        if url not in seen:
            seen.add(url)
            unique_tabs.append((title, url))

    for title, url in unique_tabs:
        subprocess.run(["open", "-a", "Google Chrome", url])
        time.sleep(0.15)

    return f"Restored {len(unique_tabs)} tabs."

# ==========================================
# 2. SPOTIFY PLAYBACK & PLAYLIST CONTROLS
# ==========================================

def get_preference(key: str, default: str = "") -> str:
    """Retrieve a stored user preference."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM user_preferences WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else default

def set_preference(key: str, value: str):
    """Store or update a user preference."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO user_preferences (key, value, updated_at) VALUES (?, ?, ?)", (key, value, time.time()))
    conn.commit()
    conn.close()

def spotify_control(action: str = "play", target: str = "") -> str:
    """
    Controls Spotify playback, tracks, and top playlists via native macOS integration.
    """
    act = action.lower().strip()

    # 1. Playlists / Search Intent
    if "playlist" in act or "top playlist" in act or target:
        playlist_name = target.strip()
        if not playlist_name or playlist_name in ("top playlist", "my top playlist", "my playlist", "favorite playlist"):
            playlist_name = get_preference("top_spotify_playlist", "Today's Top Hits")

        encoded = urllib.parse.quote(playlist_name)
        subprocess.run(["open", f"spotify:search:{encoded}"])
        try:
            subprocess.run(['osascript', '-e', 'tell application "Spotify" to play'], timeout=2, capture_output=True)
        except Exception:
            pass
        return f"Playing {playlist_name}."

    # 2. Fast Transport Controls
    if act in ("pause", "stop"):
        try:
            subprocess.run(['osascript', '-e', 'tell application "Spotify" to pause'], timeout=2, capture_output=True)
        except Exception:
            pass
        return "Spotify paused."
    elif act in ("next", "next track", "skip"):
        try:
            subprocess.run(['osascript', '-e', 'tell application "Spotify" to next track'], timeout=2, capture_output=True)
        except Exception:
            pass
        return "Next track."
    elif act in ("previous", "prev", "back"):
        try:
            subprocess.run(['osascript', '-e', 'tell application "Spotify" to previous track'], timeout=2, capture_output=True)
        except Exception:
            pass
        return "Previous track."
    elif act in ("play", "resume"):
        try:
            subprocess.run(['osascript', '-e', 'tell application "Spotify" to play'], timeout=2, capture_output=True)
        except Exception:
            subprocess.run(["open", "-a", "Spotify"])
        return "Spotify resumed."

    return "Done."

# ==========================================
# 3. BACKGROUND ACTIVITY MONITOR THREAD
# ==========================================

_monitor_running = False

def _monitor_loop():
    global _monitor_running
    print("🧠 [J.A.R.V.I.S. Memory & Activity Monitor Active]", flush=True)
    while _monitor_running:
        try:
            # 1. Snapshot open tabs
            snapshot_tabs()

            # 2. Track frontmost application
            script = 'tell application "System Events" to get name of first application process whose frontmost is true'
            res = subprocess.run(['osascript', '-e', script], capture_output=True, text=True, timeout=2)
            front_app = res.stdout.strip()
            if front_app and front_app not in ("loginwindow", "Finder"):
                today = datetime.now().strftime("%Y-%m-%d")
                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()
                cursor.execute("INSERT INTO app_activity (date, timestamp, app_name) VALUES (?, ?, ?)", (today, time.time(), front_app))
                conn.commit()
                conn.close()
        except Exception as e:
            pass

        # Wait 45 seconds between activity samples (lightweight ~0.01% CPU)
        time.sleep(45)

def start_activity_monitor():
    """Starts the continuous background activity monitor daemon."""
    global _monitor_running
    if not _monitor_running:
        _monitor_running = True
        t = threading.Thread(target=_monitor_loop, daemon=True)
        t.start()

def get_activity_summary(date_str: str = "yesterday") -> str:
    """Summarizes user's activity for a given day."""
    if date_str == "yesterday":
        target_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    else:
        target_date = datetime.now().strftime("%Y-%m-%d")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Most used apps
    cursor.execute("SELECT app_name, COUNT(*) FROM app_activity WHERE date = ? GROUP BY app_name ORDER BY COUNT(*) DESC LIMIT 5", (target_date,))
    app_rows = cursor.fetchall()

    # Tabs worked on
    cursor.execute("SELECT COUNT(DISTINCT url) FROM tab_history WHERE date = ?", (target_date,))
    tab_count = cursor.fetchone()[0]

    conn.close()

    if not app_rows and tab_count == 0:
        return f"I don't have recorded activities for {target_date} yet."

    apps_text = ", ".join([f"{name} ({count} mins)" for name, count in app_rows])
    return f"On {target_date}, your most active applications were {apps_text}, with {tab_count} unique browser tabs open."

if __name__ == "__main__":
    print("Testing tab snapshot...")
    snapshot_tabs()
    print("Testing Spotify play...")
    print(spotify_control("play", "Today's Top Hits"))
