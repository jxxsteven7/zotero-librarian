**What changed**

**Why** (link the issue if there is one)

**How you tested it**
- [ ] `python3 zl.py setup` passes
- [ ] platform(s): Ubuntu / macOS / Windows
- [ ] agent(s): Claude Code / Codex / none
- [ ] if `taxonomy.toml` or the classifier changed: `python3 tools/eval_classify.py` before → after: `p 0.xx / r 0.xx` → `p 0.xx / r 0.xx`
- [ ] `.agents/skills` and `.claude/skills` identical (`python3 zl.py setup --sync-skills`)

One feature per pull request. The maintainer sets the version number and the CHANGELOG line on merge.
