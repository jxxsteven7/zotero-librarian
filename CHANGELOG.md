# Changelog

One line per version. Minor versions (`vX.Y`) are one feature or merged PR each; major versions are tagged by the maintainer.

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
