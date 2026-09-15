# zotero-librarian — rules for the agent working in this repository

This repository keeps a Zotero library organized: four collections, a controlled `family:value` tag vocabulary,
`[YYYY-MMDD] [Venue] Title` titles, project pages in the URL field, and a Notion mirror. The scripts do the judging;
the agent (Claude Code, Codex, Kimi Code CLI, ... — this file is read by all of them) runs them, relays their reports,
and handles only what they mark for a human. Tokens are the scarce resource: anything a script or the local model can
do is done there; never read a PDF, grep a full text or re-derive a classification yourself. Reply in the user's language.

## Layout and commands

```
zl.py                       the only entry point: python3 zl.py <command> (Windows: python zl.py); --help lists everything
taxonomy.toml               collections, tag vocabulary with definitions, classification rules, venue abbreviations — the source of truth
AGENTS.md                   this file: how the library is accessed and what the agent may do (CLAUDE.md just imports it)
zotero_librarian/              package, standard library only, Ubuntu / macOS / Windows
  config.py taxonomy.py venues.py     .env + paths + sqlite snapshot; taxonomy loader; venue abbreviations
  classify.py llm.py                  rule engine (evidence + thresholds); local-LLM adjudication on top
  pipeline.py                         add / save / tidy / verify: fetch -> classify -> write -> verify -> log -> report
  fetch.py sources.py pdf.py published.py titles.py   metadata (arXiv / Crossref / OpenReview / citation meta), PDFs, venue lookup, titles
  connector.py zapi.py localdb.py     Zotero desktop connector (new items + PDF); Web API (edits); read-only sqlite
  discover.py citations.py recheck.py batch.py setup_check.py install.py cli.py
.agents/skills/             the skills download / tidy / discover / refs (Agent Skills format; Codex `$download`, Kimi `/skill:download`)
.claude/skills/             identical copy for Claude Code (`/download`); edit .agents/skills and run `zl.py setup --sync-skills`
proposals/proposal.py       approval-mode batch data (RETAG / UNTAG / UNCOLLECT / P)
docs/notero.md              Notion mirror (Notero) configuration
logs/zotero-organize.log.md audit log, appended by the scripts (local to the machine, not in git)
tools/                      eval_classify.py (measure the classifier on the library), fix_pdf_names.js (Zotero Run JavaScript)
inbox/  cache/              staged downloads; library snapshot, full-text and API caches (not in git)
```

| Task | Command |
|---|---|
| add papers (`download` skill) | `zl.py add <links...>` — everything in one go; pauses only when the collection is uncertain (or, with `ZC_LLM=agent`, for the ADJUDICATE block) |
| organize items dropped into Zotero by hand (`tidy` skill) | `zl.py tidy [--dry-run]` — items without a status tag |
| edit one item | `zl.py verify <key>` · `tag <key> a,b` · `untag <key> a,b --why ...` · `collect <key> <collection>` · `set <key> url=... shortTitle=...` |
| re-verify arXiv items | `zl.py dump && zl.py recheck [--dates] [--search]`, then `--write` after approval |
| find papers (`discover`, `refs` skills) | `zl.py discover --days 7 --tags a,b` · `zl.py refs <key|arXiv|DOI>` · `zl.py refs --library` |
| batch (approval mode) | `zl.py dump` -> edit `proposals/proposal.py` -> `zl.py proposal` -> `zl.py apply --dry-run / --plan / --apply` |
| new machine | `./setup.sh` (= `zl.py setup`); `zl.py install` puts `zl` on PATH and the skills in the user-level skill dirs (use from anywhere) |

## Access rules (hard constraints)

- **Read** the library through `zl.py dump` / `localdb` (`config.connect_ro()` copies the sqlite + WAL to a temp dir, so it works while Zotero
  runs and sees current data). **Never write to zotero.sqlite** — Zotero is running and syncing.
- **Write** existing items only through the Zotero Web API (`zapi.py`): `tags` and `collections` are replaced wholesale, so every payload starts
  from the current server state and only adds; the server `version` is the optimistic lock. Local `items.version` can be ahead of the server by
  a few; unsynced local changes show as `synced=0`.
- **New items and PDFs go through the desktop connector** (`connector.py`, 127.0.0.1:23119): attachment sync is WebDAV, so a PDF uploaded through
  the Web API never reaches the clients. Zotero must be running for `zl.py add`.
- The API key lives in `.env` (mode 600). **Never print it** into the conversation or a log. If it is missing, stop and ask.
- `DELETE /items` is permanent (no trash, local PDF removed). Delete or move to trash only when the user says so, after writing a snapshot of
  the affected items to the log. Never delete notes or collections.
- `prefs.js` can only be edited while Zotero is closed. `extensions.zotero.automaticTags` should be off (a per-client setting).
- Every write is logged by the scripts to `logs/zotero-organize.log.md` (local, git-ignored). Don't write the log by hand.

## Repository rules (git, versions, consistency)

- Everything in the repository, commit messages included, is in English.
- **One complete feature = one commit**, titled `vX.Y: <what changed>`, and that commit bumps `__version__` in
  `zotero_librarian/__init__.py` and adds the line to `CHANGELOG.md`. Y grows by one per feature / merged PR; X is bumped by the
  maintainer, who tags the major versions (`git tag vX.0`). Fixes that are not a feature are plain commits without a version.
  Never commit `.env`, `cache/`, `inbox/`, `logs/`.
- **Commit and PR descriptions** follow Google's engineering practices, *Writing good CL descriptions*
  (https://google.github.io/eng-practices/review/developer/cl-descriptions.html): the first line is a short, complete,
  imperative summary that stands alone in `git log` ("Delete X and replace it with Y", never "Fix bug" / "Add functions"),
  then a blank line, then a body that says **what** changed and **why** — the problem, the approach taken, its limitations,
  and the numbers (eval precision / recall, timings) — so that the description is understood without following links.
  Re-read the description before merging: a change often drifts during review and the text must still match it.
- **Review** follows Google's *The Standard of Code Review*
  (https://google.github.io/eng-practices/review/reviewer/standard.html): approve once the change definitely improves the
  overall health of the code, even if it isn't perfect — there is no perfect code, only better code. Technical facts and
  data outweigh opinions; this file is the style authority, and where it is silent, consistency with the existing code
  wins; an optional suggestion is prefixed `Nit:`. Disagreements are settled by discussion, and failing that by the
  maintainer, so a PR never stalls.
- **Agent-neutral**: the skills in `.agents/skills/` are the source; `.claude/skills/` must stay a verbatim copy (`zl.py setup`
  fails the check otherwise; `--sync-skills` copies). A skill uses only what every agent has — "run this command, relay the table,
  handle PAUSE rows"; no agent-specific frontmatter, tools or syntax. Everything an agent needs is in `AGENTS.md`; `CLAUDE.md`
  only imports it.
- **Platform-neutral**: Ubuntu, macOS and Windows, standard library only, Python 3.11+. Paths, credentials and external programs
  come from `config.py` only (no `~`, no `/tmp`, no hard-coded separators elsewhere); text files are read and written as UTF-8;
  docs say `python3` and note that Windows uses `python`. `zl.py setup` must pass on all three before a version is tagged.

## Collections and tags

The vocabulary, the definitions and the classification rules are in **`taxonomy.toml`**; the descriptions there are the policy the
local model reads, so keep them precise. Only four collections, no new ones, no sub-collections — finer distinctions are tags.

- Judge from the abstract and the experiments, never from the title alone. A method / hardware / input counts only if the paper's own
  contribution uses it; related work, baselines and future work do not count. When unsure, leave the family empty and say so.
- The scripts output three tiers: **assigned** (written), **candidates** (listed for the user, not written) and **flags**. Candidates are added
  with `zl.py tag` after the user agrees; a candidate whose evidence clearly meets the definition may be added directly, said so in the report.
- Who adjudicates the borderline candidates is `ZC_LLM` in `.env`: a local model (`ollama` / `openai`, free), the agent (`agent`: the script
  prints an ADJUDICATE block with the candidates, definitions and evidence and pauses; answer with `--confirm a,b` or `--confirm none` on the
  printed command — a few hundred tokens per paper), or nobody (`off`). The candidates asked about are the only ones the answer may contain.
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
  don't fill a venue from memory. `zl.py recheck` re-verifies existing items.
- URL field = project page (github.io / lab site / sites.google) when one exists, else the arXiv abs or DOI link. The arXiv id is kept in the
  DOI field (`10.48550/arXiv.…`), not in the URL. Short Title = the paper's short name (nickname > the part before the colon > the title).
- PDF file names must not carry the title prefix: the library's rename template drops the brackets (a synced setting, already set);
  `tools/fix_pdf_names.js` repairs old files.

## Workflows

- The `download` skill runs `zl.py add`: fetch -> classify -> save -> wait for the server sync and verify -> log -> report table.
  The agent relays the table, lists candidates and flags for the user, and resolves `PAUSE` rows by running the `zl.py save ...` line the
  script printed — with `--collection` decided from the printed abstract, and / or `--confirm` for an ADJUDICATE block. No grepping the
  full text, no polling loops, no hand-written logs.
- The `tidy` skill runs `zl.py tidy` for items the user dropped into Zotero by hand (no status tag): metadata, title, URL, short title, tags,
  collection — same pauses, same report.
- `discover` and `refs` only print tables; the user picks, then `download`.
- Batch changes (vocabulary renames, corrections across many items) stay in approval mode: `proposals/proposal.py` -> `zl.py proposal` ->
  show the table -> `zl.py apply --apply` after approval.
- Changing the classifier: edit `taxonomy.toml`, run `python3 tools/eval_classify.py` (rules) and `--llm` (with the local model) and keep
  precision from dropping; the numbers are in the README.

Notion mirror: `docs/notero.md`.
