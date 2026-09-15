# Changelog

One line per version: every commit that changes behaviour is a `vX.Y` (AGENTS.md); major versions are tagged by the maintainer.

- **v0.14** (2026-09-15) — the Quick start (both READMEs) and `docs/first-run.md` open with the two prerequisites — Zotero
  signed in to sync, an API key with *Allow library access* + *Allow write access*, the user ID shown next to it — instead of
  a comment inside the code block; `setup` and `.env.example` name those options (there is no "file access" option to tick)
  and say that `setup` looks the user ID up from a valid key.
- **v0.13** (2026-09-15) — macOS test run + code review. `setup` no longer passes a copied `.env.example`: placeholder credentials
  are reported as such (`ZOTERO_API_KEY` one token, `ZOTERO_LIBRARY_ID` numeric), every Web API command stops on them with the
  same message instead of a URL error, and with a real key but no id `setup` prints the user id the key belongs to. A PDF without
  pdftotext / pypdf is judged from the abstract *and flagged so*; the fetch card no longer names a full text that does not exist.
  `tidy` keeps an existing `[date] [venue]` prefix (date only gains precision, only `????` / `arXiv` venues are filled; a
  nickname in the venue slot survives), never writes a second reading status when the server already has one, and rejects an
  unknown `--collection` instead of logging a filing that did not happen. `add` checks `--collection` / `--also` and the
  desktop connector before fetching anything, and a save failure no longer aborts the rest of the list (row + `save` command
  to retry); an item the connector created before a later step failed is logged as `download (incomplete)`, and `save` re-runs
  the duplicate check instead of trusting the inbox record. `tag`: a `status:` tag replaces the reading status, backwards only
  with `--force`; `untag` refuses `keep_bare_tags` and the last reading status. arXiv API: a paper whose title contains
  "Error" is no longer mistaken for the API's error entry; the duplicate check finds an arXiv id in the DOI the tool itself
  writes (`10.48550/arXiv.<id>`) and in `extra`; unpadded page dates (`2019-6-9`) format correctly; Crossref
  `"date-parts": []`, an arXiv entry without a date and `verify` on a child item no longer crash. The taxonomy test checks
  the rule keys the classifier actually reads (`excludes` / `excluded_by` / `weak_with` / `strip` / `head_only`). The
  read-only sqlite snapshot is copied once per library state instead of on every query (4-8 copies per added paper before);
  `refs --library` pauses only after a request that actually went to Semantic Scholar, not after a cache hit.
- **v0.12** (2026-09-15) — Kimi Code CLI dropped from the supported agents (never verified end to end); Claude Code and Codex
  remain, both exercised live through the `download` skill.
- **v0.11** (2026-09-15) — review before open-sourcing: `add` resolves the collection before creating the item (a missing
  collection no longer leaves a half-saved item), skips duplicates before the classifier runs, prints the whole abstract on a
  collection PAUSE; one text analysis per paper instead of two; the negative-context rule applies to every family (same eval
  numbers); `remote_collections` pages past 100; `recheck` reads the live library (no `dump` first); a broken `taxonomy.toml`
  is reported by `setup` instead of a traceback; a missing model server is one short flag; no family names hard-coded in the
  code (`[llm] adjudicate_families` unset = all); dead code and unclosed files removed. docs/taxonomy.md: the file's reference.
- **v0.10** (2026-09-15) — `tidy` now writes the default reading status (it never did through the Web API path, so a tidied
  item stayed "untidy"), prints what it wrote and the sync check, and its table once. tidy demo GIF; all four demos in
  README "What it does", the library screenshot on top.
- **v0.9** (2026-09-15) — `zl.py add --from-file FILE` (one link / arXiv id / DOI per line) and a summary line for a batch
  (saved / paused / duplicate / failed); `discover` and `refs` read the live library instead of the last dump.
- **v0.8** (2026-09-15) — one table for two readers (`table.py`): markdown when piped to an agent, aligned columns cut to
  the terminal for a human; used by `add` / `tidy` / `discover` / `refs`. Three README demos recorded by `docs/demo.sh`.
- **v0.7** (2026-09-15) — readable terminal output: the card prints before the model runs, evidence snippets fit the
  terminal width and keep the matched words, `saved` / `sync` are one line each (details only when the server differs),
  the model's disagreements are one flag, table notes name candidates only. README demo GIF (`docs/demo.sh` records it).
- **v0.6** (2026-09-15) — keep an appendix that follows the reference list (NeurIPS / CoRL layout; the robot setup lives
  there), discount negated modalities in the abstract ("without depth or point-cloud inputs"), RM-75 / 7-DoF manipulator
  patterns. Eval on 132 items: 306/37/97 -> 313/39/90 TP/FP/FN, recall 0.76 -> 0.78, precision 0.89.
- **v0.5** (2026-09-15) — remove the approval-mode batch feature (`proposals/proposal.py`, `zl.py proposal`, `zl.py apply`,
  `batch.py`): library-wide edits declared in a Python file were used once, for the first pass over the original library;
  `add` / `tidy` / `tag` / `untag` / `set` / `recheck --write` cover everything since. Lighter surface for the release.
- **v0.4** (2026-09-15) — CI on Ubuntu / macOS / Windows (`.github/workflows/ci.yml`): `zl.py setup --offline` (repository
  checks only: Python, taxonomy, skills mirror and frontmatter — no Zotero, no network) + `tests/` (rule engine, agent
  adjudication round trip, titles, skills, CLI on synthetic papers, standard-library unittest). A stale `.claude/skills` copy or
  bad skill frontmatter now fails `setup` instead of warning.
- **v0.3** (2026-09-15) — first run on an existing library: `zl.py tidy --create-collections` creates the taxonomy's
  collections, `--limit N` samples the plan, `zl.py setup` reports missing collections; `[library] title_prefix = false`
  leaves titles untouched everywhere (add / tidy / recheck); docs/first-run.md; README trimmed to a front page with
  badges, long sections moved to docs/classifier.md and CONTRIBUTING.md.
- **v0.2** (2026-09-15) — `zl.py install`: launcher `zl` on PATH + user-level skills for Claude Code / Codex / Kimi, so
  `/download` works from any directory (`--remove` undoes it); entry point renamed `zc.py` -> `zl.py`; README: two install
  modes, issue / PR procedure; GitHub issue and PR templates.
- **v0.1** (2026-09-15) — renamed from zotero-claude; first versioned state: `zl.py` add / tidy / discover / refs / recheck / apply, `taxonomy.toml`
  rules with a local-model or agent adjudicator (`ZC_LLM=ollama|openai|agent|off`), `AGENTS.md` + `.agents/skills/` for
  Claude Code / Codex / Kimi Code CLI, local audit log (no longer committed).
