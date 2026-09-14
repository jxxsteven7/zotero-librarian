# zotero-claude — rules for working in this repository

This repository keeps a Zotero library organized: four collections, a controlled `family:value` tag vocabulary,
`[YYYY-MMDD] [Venue] Title` titles, project pages in the URL field, and a Notion mirror. The scripts do the judging;
Claude runs them, relays their reports, and handles only what they mark for a human. Reply in the user's language.

## Layout and commands

```
zc.py                       the only entry point: python3 zc.py <command> (Windows: python zc.py); --help lists everything
taxonomy.toml               collections, tag vocabulary with definitions, classification rules, venue abbreviations — the source of truth
CLAUDE.md                   this file: how the library is accessed and what the agent may do
zotero_claude/              package, standard library only, Ubuntu / macOS / Windows
  config.py taxonomy.py venues.py     .env + paths + sqlite snapshot; taxonomy loader; venue abbreviations
  classify.py llm.py                  rule engine (evidence + thresholds); local-LLM adjudication on top
  pipeline.py                         add / save / tidy / verify: fetch -> classify -> write -> verify -> log -> report
  fetch.py sources.py pdf.py published.py titles.py   metadata (arXiv / Crossref / OpenReview / citation meta), PDFs, venue lookup, titles
  connector.py zapi.py localdb.py     Zotero desktop connector (new items + PDF); Web API (edits); read-only sqlite
  discover.py citations.py recheck.py batch.py setup_check.py cli.py
.claude/skills/             /download /tidy /discover /cite
proposals/proposal.py       approval-mode batch data (RETAG / UNTAG / UNCOLLECT / P)
docs/notero.md              Notion mirror (Notero) configuration
logs/zotero-organize.log.md audit log (every write, appended by the scripts, committed);  logs/NOTES.md  library-specific state and precedents
tools/                      eval_classify.py (measure the classifier on the library), fix_pdf_names.js (Zotero Run JavaScript)
inbox/  cache/              staged downloads; library snapshot, full-text and API caches (not in git)
```

| Task | Command |
|---|---|
| add papers (`/download`) | `zc.py add <links...>` — everything in one go; pauses only when the collection is uncertain |
| organize items dropped into Zotero by hand (`/tidy`) | `zc.py tidy [--dry-run]` — items without a status tag |
| edit one item | `zc.py verify <key>` · `tag <key> a,b` · `untag <key> a,b --why ...` · `collect <key> <collection>` · `set <key> url=... shortTitle=...` |
| re-verify arXiv items | `zc.py dump && zc.py recheck [--dates] [--search]`, then `--write` after approval |
| find papers (`/discover`, `/cite`) | `zc.py discover --days 7 --tags a,b` · `zc.py cite <key|arXiv|DOI>` · `zc.py cite --library` |
| batch (approval mode) | `zc.py dump` -> edit `proposals/proposal.py` -> `zc.py proposal` -> `zc.py apply --dry-run / --plan / --apply` |
| new machine | `./setup.sh` (= `zc.py setup`) |

## Access rules (hard constraints)

- **Read** the library through `zc.py dump` / `localdb` (`config.connect_ro()` copies the sqlite + WAL to a temp dir, so it works while Zotero
  runs and sees current data). **Never write to zotero.sqlite** — Zotero is running and syncing.
- **Write** existing items only through the Zotero Web API (`zapi.py`): `tags` and `collections` are replaced wholesale, so every payload starts
  from the current server state and only adds; the server `version` is the optimistic lock. Local `items.version` can be ahead of the server by
  a few; unsynced local changes show as `synced=0`.
- **New items and PDFs go through the desktop connector** (`connector.py`, 127.0.0.1:23119): attachment sync is WebDAV, so a PDF uploaded through
  the Web API never reaches the clients. Zotero must be running for `zc.py add`.
- The API key lives in `.env` (mode 600). **Never print it** into the conversation or a log. If it is missing, stop and ask.
- `DELETE /items` is permanent (no trash, local PDF removed). Delete or move to trash only when the user says so, after writing a snapshot of
  the affected items to the log. Never delete notes or collections.
- `prefs.js` can only be edited while Zotero is closed. `extensions.zotero.automaticTags` should be off (a per-client setting).
- Every write is logged by the scripts to `logs/zotero-organize.log.md` (`zc.py add` and `tidy` also commit and push that file). Don't write
  the log by hand and don't create separate commits for it.
- Git: commit messages and everything in the repository are in English.

## Collections and tags

The vocabulary, the definitions and the classification rules are in **`taxonomy.toml`**; the descriptions there are the policy the
local model reads, so keep them precise. Only four collections, no new ones, no sub-collections — finer distinctions are tags.

- Judge from the abstract and the experiments, never from the title alone. A method / hardware / input counts only if the paper's own
  contribution uses it; related work, baselines and future work do not count. When unsure, leave the family empty and say so.
- The scripts output three tiers: **assigned** (written), **candidates** (listed for the user, not written) and **flags**. Candidates are added
  with `zc.py tag` after the user agrees; a candidate whose evidence clearly meets the definition may be added directly, said so in the report.
- Values outside `taxonomy.toml` are never invented. A new value needs the user's approval and is then added to `taxonomy.toml`
  (definition + patterns); no bare tags except the ones listed in `keep_bare_tags` (`notion` is written by the Notero plugin — keep it,
  and keep the `Notion` link attachment under each item).
- Every item carries exactly one status on the read axis (`to-read-first > to-read > skimmed > read`); new items get `to-read`. Status
  never moves backwards without the user's approval; the presentation / reproduction axes are the user's.
- Existing user-set titles, nicknames in a third bracket (`[ALOHA/ACT]`) and markers (✅ ❗) are never changed.

## Titles, dates, venues, URL

- Title = `[YYYY-MMDD] [Venue] Original title`. The date is the day the paper first appeared: arXiv v1 submission date; for a journal or
  conference paper with an earlier preprint, the preprint's v1; otherwise the online publication date (PDF first page, then Crossref
  `published-online`; Crossref `created` only if within a year of the print year). Later versions, re-downloads and acceptance never move
  the date. Unknown precision is written as far as it goes (`[2008-11]`, `[1987]`), never invented.
- Venue = abbreviation from `taxonomy.toml` (`[[venues]]`). A preprint is `[arXiv]` until it is accepted; the scripts check arXiv comment ->
  PDF first page -> Semantic Scholar -> Crossref -> project page and write the venue when found. Nothing found means `[arXiv]` stays —
  don't fill a venue from memory. `zc.py recheck` re-verifies existing items.
- URL field = project page (github.io / lab site / sites.google) when one exists, else the arXiv abs or DOI link. The arXiv id is kept in the
  DOI field (`10.48550/arXiv.…`), not in the URL. Short Title = the paper's short name (nickname > the part before the colon > the title).
- PDF file names must not carry the title prefix: the library's rename template drops the brackets (a synced setting, already set);
  `tools/fix_pdf_names.js` repairs old files.

## Workflows

- `/download <links>` runs `zc.py add`: fetch -> classify -> save -> wait for the server sync and verify -> commit the log -> report table.
  Claude relays the table, lists candidates and flags for the user, and resolves `PAUSE` rows (collection uncertain) by reading the printed
  abstract and running the `zc.py save ...` line the script printed. No grepping the full text, no polling loops, no hand-written logs.
- `/tidy` runs `zc.py tidy` for items the user dropped into Zotero by hand (no status tag): metadata, title, URL, short title, tags,
  collection — same pauses, same report.
- `/discover` and `/cite` only print tables; the user picks, then `/download`.
- Batch changes (vocabulary renames, corrections across many items) stay in approval mode: `proposals/proposal.py` -> `zc.py proposal` ->
  show the table -> `zc.py apply --apply` after approval.
- Changing the classifier: edit `taxonomy.toml`, run `python3 tools/eval_classify.py` (rules) and `--llm` (with the local model) and keep
  precision from dropping; the numbers are in the README.

Library-specific state, precedents and open items: `logs/NOTES.md`. Notion mirror: `docs/notero.md`.
