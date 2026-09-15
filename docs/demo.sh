#!/usr/bin/env bash
# The README demo: one `zl.py add` on a fresh arXiv paper, typed out and run for real (Zotero must be running).
#   asciinema rec --overwrite -c "bash docs/demo.sh" --window-size 108x46 docs/demo.cast
#   agg --font-family "DejaVu Sans Mono" --font-size 14 --rows 46 --theme monokai --idle-time-limit 2.5 --last-frame-duration 6 docs/demo.cast docs/demo.gif
# stderr (arXiv rate-limit and Semantic Scholar notices) is not shown; nothing else is hidden.
cd "$(dirname "$0")/.." || exit 1
PAPER=${1:-https://arxiv.org/abs/2606.08653}
type_cmd() { printf '\033[1;32m$\033[0m '; for ((i = 0; i < ${#1}; i++)); do printf '%s' "${1:i:1}"; sleep 0.035; done; sleep 0.5; printf '\n'; }
sleep 0.8
type_cmd "python3 zl.py add $PAPER"
python3 zl.py add "$PAPER" 2>/dev/null
sleep 4
