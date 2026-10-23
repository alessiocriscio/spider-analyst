#!/usr/bin/env python3
"""Spider Analyst launcher for macOS, Windows and Linux.

    python3 launch.py            (Windows: py launch.py)

Creates .venv with Python 3.10+, installs requirements when they change, asks once
for the SEC contact, starts the local server and opens it in a Chromium-based
browser (Chrome, Brave, Edge, Arc, ...): the default browser if it is one,
otherwise the first one installed. Set SPIDER_BROWSER to force a browser
(an app name on macOS, an executable path elsewhere).

Standard library only, and written for Python 3.8+ so it also runs under the
macOS system Python; the app itself runs in the 3.10+ virtual environment.
"""
import hashlib
import json
import os
import plistlib
import shutil
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path



def ui(it, en):
    """Terminal messages are always in English."""
    return en

ROOT = Path(__file__).resolve().parent
PORT = int(os.environ.get("SPIDER_PORT", "8765"))
URL = "http://127.0.0.1:%d/" % PORT
WIN = os.name == "nt"
MAC = sys.platform == "darwin"
VENV = ROOT / ".venv"
VPY = VENV / ("Scripts/python.exe" if WIN else "bin/python")
CONFIG = Path.home() / ".spider-analyst" / "config.json"
PY_DOWNLOAD = "https://www.python.org/downloads/"

# Chromium-based browsers, in order of preference
MAC_BROWSERS = [
    ("com.google.chrome", "Google Chrome"), ("com.brave.browser", "Brave Browser"), ("com.microsoft.edgemac", "Microsoft Edge"),
    ("company.thebrowser.browser", "Arc"), ("org.chromium.chromium", "Chromium"), ("com.vivaldi.vivaldi", "Vivaldi"),
    ("com.operasoftware.opera", "Opera"), ("com.google.chrome.canary", "Google Chrome Canary"),
]
WIN_PROGIDS = ("chromehtml", "bravehtml", "msedgehtm", "chromiumhtm", "vivaldihtm", "operastable", "archtml")
WIN_EXES = [
    ("chrome.exe", [r"Google\Chrome\Application\chrome.exe"]),
    ("brave.exe", [r"BraveSoftware\Brave-Browser\Application\brave.exe"]),
    ("msedge.exe", [r"Microsoft\Edge\Application\msedge.exe"]),
]
LINUX_BROWSERS = ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "brave-browser", "microsoft-edge", "vivaldi"]


def say(msg=""):
    print(msg, flush=True)


# ---------------------------------------------------------------- Python and virtual environment

def _is_310(cmd):
    try:
        return subprocess.run(cmd + ["-c", "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)"],
                              capture_output=True, timeout=20).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def find_python():
    """A command (as a list) that runs Python 3.10 or newer, or None."""
    if sys.version_info >= (3, 10):
        return [sys.executable]
    cands = []
    if WIN:
        cands += [["py", "-3.13"], ["py", "-3.12"], ["py", "-3.11"], ["py", "-3.10"], ["py", "-3"], ["python"]]
    else:
        cands += [["python3.13"], ["python3.12"], ["python3.11"], ["python3.10"],
                  ["/opt/homebrew/bin/python3"], ["/usr/local/bin/python3"], ["python3"]]
    for c in cands:
        if shutil.which(c[0]) and _is_310(c):
            return c
    if shutil.which("uv"):
        return ["uv"]
    return None


def ensure_venv(py):
    if not VPY.exists():
        say(ui("Primo avvio: preparo l'ambiente Python (solo la prima volta)...", "First start: preparing the Python environment (only once)..."))
        if py == ["uv"]:
            subprocess.run(["uv", "venv", str(VENV), "--python", "3.12", "--seed"], check=True)
        else:
            subprocess.run(py + ["-m", "venv", str(VENV)], check=True)
    req = ROOT / "requirements.txt"
    stamp = VENV / ".requirements.sha"
    digest = hashlib.sha256(req.read_bytes()).hexdigest()
    if not stamp.exists() or stamp.read_text().strip() != digest:
        say(ui("Installo le dipendenze (1-2 minuti la prima volta)...", "Installing dependencies (1-2 minutes the first time)..."))
        subprocess.run([str(VPY), "-m", "pip", "install", "-q", "--upgrade", "pip"], check=False)
        subprocess.run([str(VPY), "-m", "pip", "install", "-q", "-r", str(req)], check=True)
        stamp.write_text(digest)


def ask_sec_identity():
    if CONFIG.exists():
        return
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    say()
    say(ui("La SEC chiede a chi scarica i bilanci americani di identificarsi (nome ed email).",
           "The SEC asks whoever downloads US filings to identify themselves (name and email)."))
    say(ui("Resta salvato solo su questo computer, in %s. Lascia vuoto per un'identità generica.",
           "It is stored only on this computer, in %s. Leave empty for a generic identity.") % CONFIG)
    try:
        ua = input(ui("Nome ed email (es. Mario Rossi mario@esempio.it): ", "Name and email (e.g. Jane Doe jane@example.com): ")).strip()
    except EOFError:
        ua = ""
    CONFIG.write_text(json.dumps({"sec_user_agent": ua} if ua else {}, indent=2))


# ---------------------------------------------------------------- server

def server_up():
    try:
        with urllib.request.urlopen(URL + "api/status", timeout=1) as r:
            return r.status == 200
    except OSError:
        return False


# ---------------------------------------------------------------- Chromium browser

def _mac_default_browser():
    p = Path.home() / "Library/Preferences/com.apple.LaunchServices/com.apple.launchservices.secure.plist"
    try:
        data = plistlib.loads(p.read_bytes())
    except (OSError, plistlib.InvalidFileException, ValueError):
        return ""
    for h in data.get("LSHandlers", []):
        if h.get("LSHandlerURLScheme") in ("https", "http"):
            return (h.get("LSHandlerRoleAll") or "").lower()
    return ""


def _open_mac():
    forced = os.environ.get("SPIDER_BROWSER")
    if forced:
        return subprocess.run(["open", "-a", forced, URL]).returncode == 0
    default = _mac_default_browser()
    ids = [b for b, _ in MAC_BROWSERS]
    order = ([default] if default in ids else []) + [b for b in ids if b != default]
    for bundle in order:
        if subprocess.run(["open", "-b", bundle, URL], capture_output=True).returncode == 0:
            return True
    return False


def _win_default_is_chromium():
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\https\UserChoice")
        progid = str(winreg.QueryValueEx(key, "ProgId")[0]).lower()
        return any(progid.startswith(p) for p in WIN_PROGIDS)
    except OSError:
        return False


def _win_exe(name, rel_paths):
    try:
        import winreg
        for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            try:
                key = winreg.OpenKey(hive, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\%s" % name)
                path = winreg.QueryValue(key, None)
                if path and Path(path.strip('"')).exists():
                    return path.strip('"')
            except OSError:
                pass
    except ImportError:
        pass
    for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)"), os.environ.get("LOCALAPPDATA")):
        for rel in rel_paths:
            if base and (Path(base) / rel).exists():
                return str(Path(base) / rel)
    return None


def _open_windows():
    forced = os.environ.get("SPIDER_BROWSER")
    if forced:
        subprocess.Popen([forced, URL])
        return True
    if _win_default_is_chromium():
        os.startfile(URL)  # noqa: S606 (Windows only)
        return True
    for name, rels in WIN_EXES:            # Edge ships with Windows 10/11, so this almost always succeeds
        exe = _win_exe(name, rels)
        if exe:
            subprocess.Popen([exe, URL])
            return True
    return False


def _open_linux():
    forced = os.environ.get("SPIDER_BROWSER")
    for name in ([forced] if forced else []) + LINUX_BROWSERS:
        exe = shutil.which(name) if name else None
        if exe:
            subprocess.Popen([exe, URL], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
    return False


def open_browser():
    try:
        ok = _open_mac() if MAC else _open_windows() if WIN else _open_linux()
    except OSError:
        ok = False
    if not ok:
        say(ui("Nessun browser Chromium trovato (Chrome, Brave, Edge, Arc): apro il browser predefinito.",
               "No Chromium-based browser found (Chrome, Brave, Edge, Arc): opening the default browser."))
        say(ui("Spider Analyst richiede un browser basato su Chromium; Safari e Firefox non sono supportati.",
               "Spider Analyst needs a Chromium-based browser; Safari and Firefox are not supported."))
        webbrowser.open(URL)


# ---------------------------------------------------------------- main

def main():
    if "--help" in sys.argv or "-h" in sys.argv:
        say(__doc__)
        return 0
    no_browser = "--no-browser" in sys.argv
    if server_up():
        say(ui("Spider Analyst è già in esecuzione su %s", "Spider Analyst is already running at %s") % URL)
        if not no_browser:
            open_browser()
        return 0
    py = find_python()
    if not py:
        say(ui("Serve Python 3.10 o più recente: %s", "Python 3.10 or newer is required: %s") % PY_DOWNLOAD)
        if WIN:
            say(ui('Su Windows, nel programma di installazione spunta "Add python.exe to PATH".',
                   'On Windows, tick "Add python.exe to PATH" in the installer.'))
        else:
            say(ui("Su Mac puoi anche usare:  brew install python", "On a Mac you can also run:  brew install python"))
        webbrowser.open(PY_DOWNLOAD)
        return 1
    try:
        ensure_venv(py)
    except subprocess.CalledProcessError:
        say(ui("Preparazione dell'ambiente non riuscita: controlla la connessione e riprova.",
               "Setting up the environment failed: check the internet connection and try again."))
        return 1
    ask_sec_identity()
    say(ui("Avvio Spider Analyst su %s  (Ctrl+C o chiudere questa finestra lo ferma)",
           "Starting Spider Analyst at %s  (Ctrl+C or closing this window stops it)") % URL)
    proc = subprocess.Popen([str(VPY), str(ROOT / "server.py")], cwd=str(ROOT))
    for _ in range(80):
        if server_up() or proc.poll() is not None:
            break
        time.sleep(0.25)
    if proc.poll() is not None:
        say(ui("Il server non è partito (la porta %d è occupata? Cambiala con SPIDER_PORT).",
               "The server did not start (is port %d in use? set SPIDER_PORT to change it).") % PORT)
        return 1
    if not no_browser:
        open_browser()
    try:
        return proc.wait()
    except KeyboardInterrupt:
        say(ui("\nChiusura...", "\nStopping..."))
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        return 0


if __name__ == "__main__":
    sys.exit(main())
