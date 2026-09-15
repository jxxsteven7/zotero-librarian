#!/usr/bin/env bash
# The README demos, typed out and run for real (Zotero running; the `add` paper must not be in the library yet):
#   bash docs/demo.sh record [add|discover|refs]     -> docs/demo-<name>.cast + .gif (asciinema + agg on PATH)
#   bash docs/demo.sh add|discover|refs               run one demo in this terminal
# stderr (arXiv rate-limit and Semantic Scholar notices) is not shown; nothing else is hidden. `refs` names a key of
# the maintainer's library — replace it with one of yours to re-record.
cd "$(dirname "$0")/.." || exit 1
declare -A CMD=([add]="python3 zl.py add https://arxiv.org/abs/2609.13761"
                [discover]="python3 zl.py discover --days 3 --cat cs.RO --tags embod:dex-hand"
                [refs]="python3 zl.py refs HKWZ6MV2 --top 6")
declare -A ROWS=([add]=40 [discover]=16 [refs]=40)
type_cmd() { printf '\033[1;32m$\033[0m '; for ((i = 0; i < ${#1}; i++)); do printf '%s' "${1:i:1}"; sleep 0.035; done; sleep 0.5; printf '\n'; }
case "$1" in
  record)
    for d in ${2:-add discover refs}; do
      asciinema rec --overwrite -c "bash $0 $d" --window-size 120x${ROWS[$d]} "docs/demo-$d.cast" >/dev/null 2>&1
      agg --font-family "DejaVu Sans Mono" --font-size 14 --theme monokai --idle-time-limit 2.5 --last-frame-duration 6 "docs/demo-$d.cast" "docs/demo-$d.gif" 2>/dev/null
      ls -la "docs/demo-$d.gif"
    done ;;
  add|discover|refs) sleep 0.8; type_cmd "${CMD[$1]}"; ${CMD[$1]} 2>/dev/null; sleep 4 ;;
  *) echo "usage: $0 record [add|discover|refs] | add | discover | refs"; exit 2 ;;
esac
