#!/bin/bash
# Spider Analyst: doppio clic per avviare (macOS).
cd "$(dirname "$0")" || exit 1
PORT="${SPIDER_PORT:-8765}"
URL="http://127.0.0.1:$PORT/"

open_browser() {
  if [ -d "/Applications/Google Chrome.app" ]; then open -a "Google Chrome" "$URL"; else open "$URL"; fi
}

# già in esecuzione?
if curl -fs "http://127.0.0.1:$PORT/api/status" >/dev/null 2>&1; then open_browser; exit 0; fi

# Python 3.10 o più recente
PY=""
for c in python3.13 python3.12 python3.11 python3.10 python3 /opt/homebrew/bin/python3 /usr/local/bin/python3; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then PY="$c"; break; fi
done

if [ ! -x .venv/bin/python ]; then
  echo "Primo avvio: preparo l'ambiente Python (una volta sola)…"
  if [ -n "$PY" ]; then
    "$PY" -m venv .venv || exit 1
  elif command -v uv >/dev/null 2>&1; then
    uv venv .venv --python 3.12 --seed || exit 1
  else
    echo
    echo "Serve Python 3.10 o più recente. Installalo da https://www.python.org/downloads/macos/"
    echo "oppure con Homebrew:  brew install python"
    echo "poi fai di nuovo doppio clic su questo file."
    open "https://www.python.org/downloads/macos/"
    read -r -p "Premi Invio per chiudere."
    exit 1
  fi
fi

STAMP=".venv/.requirements.sha"
SUM=$(shasum requirements.txt | cut -d' ' -f1)
if [ "$(cat "$STAMP" 2>/dev/null)" != "$SUM" ]; then
  echo "Installo le dipendenze…"
  .venv/bin/python -m pip install -q --upgrade pip >/dev/null
  .venv/bin/python -m pip install -q -r requirements.txt || { read -r -p "Installazione non riuscita. Premi Invio per chiudere."; exit 1; }
  echo "$SUM" > "$STAMP"
fi

CFG="$HOME/.spider-analyst/config.json"
if [ ! -f "$CFG" ]; then
  mkdir -p "$HOME/.spider-analyst"
  echo
  echo "La SEC chiede a chi scarica i bilanci americani di identificarsi (nome e email)."
  echo "Resta salvato solo su questo Mac, in $CFG. Lascia vuoto per usare un'identificazione generica."
  read -r -p "Nome ed email (es. Mario Rossi mario@esempio.it): " UA
  .venv/bin/python - "$UA" "$CFG" <<'PY'
import json, sys
ua, path = sys.argv[1].strip(), sys.argv[2]
json.dump({"sec_user_agent": ua} if ua else {}, open(path, "w"), indent=2)
PY
fi

echo "Avvio Spider Analyst su $URL  (chiudi questa finestra per fermarlo)"
.venv/bin/python server.py &
SERVER=$!
trap 'kill $SERVER 2>/dev/null' EXIT INT TERM
for _ in $(seq 1 40); do
  curl -fs "http://127.0.0.1:$PORT/api/status" >/dev/null 2>&1 && break
  sleep 0.25
done
open_browser
wait $SERVER
