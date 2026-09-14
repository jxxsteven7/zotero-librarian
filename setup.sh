#!/usr/bin/env bash
# Thin wrapper for the new-machine health check: picks a working Python and runs `zc.py setup`
# (python3 on Linux/macOS; Git Bash on Windows often only has python).
cd "$(dirname "$0")" || exit 1
for py in python3 python py; do
  if command -v "$py" >/dev/null 2>&1 && "$py" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
    exec "$py" zc.py setup "$@"
  fi
done
echo "x Python 3.11+ not found: Ubuntu sudo apt install python3; macOS brew install python; Windows python.org installer with Add to PATH"; exit 1
