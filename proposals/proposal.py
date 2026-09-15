"""Batch proposal data for `zc.py apply` (approval mode).

`zc.py add` and `zc.py tidy` cover day-to-day filing; this file is for library-wide operations the user approves as a batch:
  P          key -> (collections, method, embod, tech, base, modality, status, note)   items to (re)file
  RETAG      old tag -> new tag, applied to every item in the library carrying the old tag (vocabulary renames)
  UNTAG      key -> [tags to remove]      correct a wrongly assigned tag
  UNCOLLECT  key -> [collections to leave]
  EXTRA_TAGS key -> [extra tags]          e.g. type:survey
  RENAMES    key -> new title
  NEW_TAGS   [(tag, reason, items)]       proposed additions to taxonomy.toml, listed in the proposal for approval
`python3 zc.py proposal` renders proposals/proposal.md (not in git) for the user to review; `zc.py apply --dry-run / --plan / --apply` executes.
The first full pass over this library (2026-09-11, 122 items) has been applied; its data lives in git history and the log.
"""
from zotero_librarian import localdb
from zotero_librarian.config import PROPOSAL_MD
from zotero_librarian.taxonomy import FAMILIES

rows = {r["key"]: r for r in localdb.load()}

P = {
    # "KEY": (["Dex-Manipulation"], ["rl"], ["dex-hand", "single-arm"], [], [], ["point-cloud"], "to-read", "note"),
}
RETAG = {}        # e.g. {"embod:dual-arm": "embod:bimanual"}
UNTAG = {}        # e.g. {"N84MPX5T": ["base:pi0.5"]}
UNCOLLECT = {}    # e.g. {"H4WFCLBL": ["AI Foundation"]}
EXTRA_TAGS = {}   # e.g. {"DY3EK5IJ": ["type:survey"]}
RENAMES = {}
NEW_TAGS = []     # e.g. ("method:grasp-synthesis", "grasp pose generation papers have no fitting method", "4LMBA5EH, 76P65UU8")


def md():
    out = ["# Batch proposal", "", "| # | key | title | collections | " + " | ".join(FAMILIES) + " | status | note |",
           "|---|---|---|---|" + "---|" * len(FAMILIES) + "---|---|"]
    for i, (k, (c, *fams, s, n)) in enumerate(P.items(), 1):
        t = rows.get(k, {}).get("title", "?")
        out.append(f"| {i} | `{k}` | {t[:60]} | {', '.join(c)} | " + " | ".join(", ".join(f) for f in fams) + f" | {s} | {n} |")
    if RETAG: out += ["", "## Vocabulary renames", ""] + [f"- `{a}` -> `{b}`" for a, b in RETAG.items()]
    if UNTAG: out += ["", "## Tags to remove", ""] + [f"- `{k}`: {', '.join(v)}" for k, v in UNTAG.items()]
    if UNCOLLECT: out += ["", "## Collections to leave", ""] + [f"- `{k}`: {', '.join(v)}" for k, v in UNCOLLECT.items()]
    if NEW_TAGS: out += ["", "## Proposed new tags", "", "| tag | reason | items |", "|---|---|---|"] + [f"| `{t}` | {w} | {i} |" for t, w, i in NEW_TAGS]
    return "\n".join(out) + "\n"


def run(argv=()):
    open(PROPOSAL_MD, "w", encoding="utf-8").write(md())
    print(f"{len(P)} rows -> {PROPOSAL_MD}; retag {len(RETAG)}, untag {len(UNTAG)}, uncollect {len(UNCOLLECT)}, renames {len(RENAMES)}")
    missing = set(P) - set(rows)
    if missing: print("keys not in the library:", missing)
