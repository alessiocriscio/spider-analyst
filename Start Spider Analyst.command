#!/bin/bash
# Spider Analyst for macOS and Linux: double-click, or run  python3 launch.py
cd "$(dirname "$0")" || exit 1
for c in python3.13 python3.12 python3.11 python3.10 /opt/homebrew/bin/python3 /usr/local/bin/python3 python3; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)' 2>/dev/null; then
    "$c" launch.py "$@"
    status=$?
    [ $status -ne 0 ] && read -r -p "Press Enter to close."
    exit $status
  fi
done
echo "Python 3.10 or newer is required: https://www.python.org/downloads/  (or: brew install python)"
command -v open >/dev/null && open "https://www.python.org/downloads/"
read -r -p "Press Enter to close."
exit 1
