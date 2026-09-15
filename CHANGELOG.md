# Changelog

One line per version. Minor versions (`vX.Y`) are one feature or merged PR each; major versions are tagged by the maintainer.

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
