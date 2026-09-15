# Changelog

One line per version. Minor versions (`vX.Y`) are one feature or merged PR each; major versions are tagged by the maintainer.

- **v0.2** (2026-09-15) — `zl.py install`: launcher `zl` on PATH + user-level skills for Claude Code / Codex / Kimi, so
  `/download` works from any directory (`--remove` undoes it); entry point renamed `zc.py` -> `zl.py`; README: two install
  modes, issue / PR procedure; GitHub issue and PR templates.
- **v0.1** (2026-09-15) — renamed from zotero-claude; first versioned state: `zl.py` add / tidy / discover / refs / recheck / apply, `taxonomy.toml`
  rules with a local-model or agent adjudicator (`ZC_LLM=ollama|openai|agent|off`), `AGENTS.md` + `.agents/skills/` for
  Claude Code / Codex / Kimi Code CLI, local audit log (no longer committed).
