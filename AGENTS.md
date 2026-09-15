# zotero-librarian — rules for the agent working in this repository

Keeps a Zotero library organized: four collections, a controlled `family:value` tag vocabulary, `[YYYY-MMDD] [Venue] Title`
titles, project page in the URL field. **The scripts judge; the agent runs them, relays their report and handles only what
they mark for a human.** Tokens are the scarce resource: never read a PDF, grep a full text or re-derive a classification
yourself. This file is read by every agent (Claude Code, Codex, Kimi Code CLI, ...; `CLAUDE.md` only imports it).
Reply in the user's language.

## Where things are

```
zl.py                 the only entry point: python3 zl.py <command> (Windows: python); --help lists everything
taxonomy.toml         collections, tag vocabulary with definitions, rules, venue abbreviations — the source of truth
zotero_librarian/     the package (stdlib only): classify / llm / pipeline / connector / zapi / localdb / setup_check / install ...
.agents/skills/       download · tidy · discover · refs (Agent Skills format; Codex `$download`, Kimi `/skill:download`)
.claude/skills/       verbatim copy for Claude Code (`/download`) — edit .agents/skills, then `zl.py setup --sync-skills`
docs/                 first-run.md (existing library), classifier.md (how it decides), notero.md (optional Notion mirror)
tests/  tools/        unittest on synthetic papers (CI, 3 platforms) · eval_classify.py (the library as ground truth)
logs/                 audit log written by the scripts (local, not in git)
```

| Task | Command |
|---|---|
| add papers (`download` skill) | `zl.py add <links...>` — pauses only when the collection is uncertain or, with `ZC_LLM=agent`, for an ADJUDICATE block |
| organize items added by hand (`tidy` skill) | `zl.py tidy [--dry-run] [--limit N] [--create-collections]` — every item without a status tag |
| edit one item | `zl.py verify <key>` · `tag <key> a,b` · `untag <key> a,b --why ...` · `collect <key> <collection>` · `set <key> url=...` |
| find papers (`discover`, `refs` skills) | `zl.py discover --days 7 --tags a,b` · `zl.py refs <key|arXiv|DOI>` · `zl.py refs --library` |
| re-verify arXiv items | `zl.py dump && zl.py recheck [--dates] [--search]`, then `--write` after approval |
| new machine / before pushing | `./setup.sh` (= `zl.py setup`; `install` puts `zl` on PATH) · `zl.py setup --offline` + `python3 -m unittest discover -s tests` + `python3 tools/check_commits.py` |

## Access rules (hard constraints)

- Read through `zl.py dump` / `localdb` (a read-only copy of the sqlite; works while Zotero runs). **Never write to zotero.sqlite.**
- Existing items are edited only through the Web API (`zapi.py`); `tags` and `collections` are replaced wholesale, so every
  payload starts from the server state and only adds. New items and PDFs go through the desktop connector (Zotero must be
  running for `zl.py add`); a PDF uploaded via the Web API never reaches the clients (WebDAV sync).
- The API key lives in `.env` (mode 600). **Never print it.** Missing: stop and ask.
- `DELETE /items` is permanent. Delete or trash only when the user says so, after the scripts logged a snapshot. Never delete
  notes or collections; collections are created only by `zl.py tidy --create-collections`, never by the agent.
- `prefs.js` only while Zotero is closed (automatic tags off on every client, see `docs/first-run.md`). Every write is logged
  by the scripts to `logs/` — don't write the log by hand.

## Repository rules

- English everywhere, commit messages included. **One feature = one commit** titled `vX.Y: <what changed>` that bumps
  `__version__` (`zotero_librarian/__init__.py`) and adds the line to `CHANGELOG.md`; Y grows by one per feature / merged PR,
  the maintainer bumps X and tags major versions. Fixes that are not a feature are plain commits (CI checks both: `tools/check_commits.py`). Never commit `.env`,
  `cache/`, `inbox/`, `logs/`.
- Commit and PR descriptions follow Google's *Writing good CL descriptions*
  (https://google.github.io/eng-practices/review/developer/cl-descriptions.html; adapted, © Google, CC BY 3.0): first line
  a short imperative summary that stands alone in `git log`, blank line, then **what** and **why** — problem, approach,
  limitations, numbers — readable without following links. Re-read it before merging; changes drift during review.
- Review follows Google's *The Standard of Code Review* (https://google.github.io/eng-practices/review/reviewer/standard.html):
  approve once the change clearly improves the code's overall health, even if imperfect; facts and data over opinions; this
  file and consistency with existing code settle style; `Nit:` marks optional remarks; the maintainer breaks ties.
- Agent-neutral: `.agents/skills/` is the source, `.claude/skills/` its verbatim copy (`setup` fails otherwise). A skill uses
  only what every agent has — "run this command, relay the table, handle PAUSE rows" — no agent-specific frontmatter or tools.
- Platform-neutral: Ubuntu, macOS, Windows, Python 3.11+, standard library only. Paths, credentials and external programs
  come from `config.py` only; files are UTF-8; docs say `python3` and note Windows uses `python`. CI runs `setup --offline`
  and the tests on all three; the full `setup` must pass on all three before a major version is tagged.

## Collections and tags

`taxonomy.toml` holds the vocabulary, the definitions (the policy the local model reads — keep them precise) and the rules.
Four collections, no new ones, no sub-collections; finer distinctions are tags.

- Judge from the abstract and the experiments, never the title alone. A method / hardware / input counts only if the paper's
  own contribution uses it — baselines, related work and future work don't. Unsure: leave the family empty and say so.
- The scripts output **assigned** (written), **candidates** (listed, not written) and **flags**. A candidate is added with
  `zl.py tag` after the user agrees; one whose evidence clearly meets the definition may be added directly, said so in the report.
- Borderline candidates are adjudicated by `ZC_LLM` in `.env`: `ollama` / `openai` (a local model, free), `agent` (the script
  prints an ADJUDICATE block and pauses; answer with `--confirm a,b` or `--confirm none` on the printed command — only the
  candidates asked about), or `off`.
- No values outside `taxonomy.toml`. A new value needs the user's approval and a definition + patterns there. No bare tags
  except `keep_bare_tags` (written by plugins such as Notero) — never remove those, nor their link attachments.
- Exactly one status on the read axis (`to-read-first > to-read > skimmed > read`); new items get `to-read`; status never
  moves backwards without approval; the other status axes are the user's. Existing user-set titles, nickname brackets (`[ALOHA/ACT]`) and markers (✅ ❗) are never changed.

## Titles, venues, URL — what the scripts enforce

Title `[YYYY-MMDD] [Venue] Original title` (off with `[library] title_prefix = false`); the date is the day the paper first
appeared (arXiv v1, else the preprint's v1, else online publication), never moved by acceptance or re-download, written as far
as known (`[2008-11]`, `[1987]`). Venue = abbreviation from `taxonomy.toml`; `[arXiv]` until acceptance is found by the scripts
(arXiv comment -> PDF first page -> Semantic Scholar -> Crossref -> project page). **Never fill a venue from memory.**
URL = project page if one exists, else the arXiv / DOI link; the arXiv id stays in the DOI field; Short Title = nickname >
part before the colon > title. PDF file names carry no prefix (Zotero rename template; `tools/fix_pdf_names.js` repairs old ones).

## Workflows

- `download` skill: `zl.py add` does fetch -> classify -> save -> verify the sync -> log -> table. The agent relays the table,
  lists candidates and flags, and resolves PAUSE rows by running the printed `zl.py save ...` line (`--collection` from the
  printed abstract, `--confirm` for an ADJUDICATE block). No grepping, no polling loops, no hand-written logs.
- `tidy` skill: `zl.py tidy` on items without a status tag — same pauses, same report. `discover` / `refs` only print tables.
- Changing the classifier: edit `taxonomy.toml`, add a synthetic case to `tests/`, run `python3 tools/eval_classify.py` (and
  `--llm`) and keep precision from dropping. Details: `docs/classifier.md`.
