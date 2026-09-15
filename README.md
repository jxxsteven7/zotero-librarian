# zotero-librarian

**Your coding agent files papers into Zotero — the scripts do the judging, the agent only runs them.**

[![Claude Code](https://img.shields.io/badge/Claude_Code-%2Fdownload-D97757?style=flat-square&logo=anthropic&logoColor=white)](#works-with)
[![Codex](https://img.shields.io/badge/Codex-%24download-000000?style=flat-square)](#works-with)
[![Kimi Code CLI](https://img.shields.io/badge/Kimi_Code_CLI-%2Fskill%3Adownload-1E6FFF?style=flat-square&logo=kimi&logoColor=white)](#works-with)
[![Ollama](https://img.shields.io/badge/adjudicator-Ollama_%7C_agent_%7C_off-2B2B2B?style=flat-square&logo=ollama&logoColor=white)](docs/classifier.md)
[![Zotero](https://img.shields.io/badge/Zotero-7%2B-CC2936?style=flat-square&logo=zotero&logoColor=white)](https://www.zotero.org)
[![Python](https://img.shields.io/badge/Python-3.11%2B_stdlib_only-3776AB?style=flat-square&logo=python&logoColor=white)](#install)
[![Platforms](https://img.shields.io/badge/Ubuntu_%C2%B7_macOS_%C2%B7_Windows-supported-4C8C2B?style=flat-square&logo=linux&logoColor=white)](#install)
[![License](https://img.shields.io/badge/license-MIT-blue?style=flat-square)](LICENSE)

Give it a link. It fetches metadata and PDF, checks for duplicates, finds the venue and the project page, files the
paper into the right collection, tags it from a controlled vocabulary **with the sentence that justifies each tag**,
saves through your running Zotero, verifies the cloud sync, logs — and prints one table. A local model (or, without a
GPU, the agent) settles only the borderline tags. You read the paper yourself. (Output abridged:)

```
$ python3 zl.py add https://arxiv.org/abs/2607.11481
  title     : [2026-0713] [arXiv] Towards Human-level Dexterous Teleoperation   short: TeleDexter
  URL       : https://bigai-dex.github.io/blog/teledexter/                 PDF: ok
  collection: Dex-Manipulation
  assign    : method:teleop, method:rl, embod:dex-hand, embod:single-arm
      method:teleop     <- title: ...Towards Human-level Dexterous Teleoperation...
      embod:single-arm  <- body x2: ...All real-world experiments are conducted on a Franka FR3 arm equipped with...
  candidates: modality:vision (6 body hits, not in the abstract)
  sync      : ok server v3540 | collections ['Dex-Manipulation'] | tags [...]
| `U3HFYV4Q` | [2026-0713] [arXiv] Towards Human-level Dexterous Teleoperation | Dex-Manipulation | method:teleop, method:rl, embod:dex-hand, embod:single-arm, status:to-read | yes | sync ok |
```

## Why

Reading papers is how understanding is built; a model's summary is someone else's reading. This tool stops before
that point: it does the part that carries no insight but eats the afternoon — finding, deduplicating, naming, filing,
tagging, keeping three machines consistent — so a paper goes from "saw the link" to "in the right place, ready to
read" in one command. Every tag comes with its evidence; the borderline ones are left to you.

## Quick start

```bash
git clone https://github.com/jxxsteven7/zotero-librarian.git ~/zotero-librarian && cd ~/zotero-librarian
cp .env.example .env        # ZOTERO_API_KEY + ZOTERO_LIBRARY_ID (zotero.org/settings/keys); data dir is auto-detected
./setup.sh                  # health check with the fix for every missing piece
claude                      # or codex / kimi — then: /download <link>
```

Needs Python 3.11+ (nothing to pip-install), `pdftotext` (poppler) or `pip install pypdf`, Zotero 7+ with sync on.
Optional: [Ollama](https://ollama.com) + `ollama pull qwen3.5:9b` for free local adjudication (else `ZC_LLM=agent`).

## What it does

| Skill / command | |
|---|---|
| `/download` · `zl.py add <links>` | arXiv, DOI, OpenReview, PDF link or file, project page → fetched, classified, saved, verified. Pauses only when the collection is genuinely ambiguous. |
| `/tidy` · `zl.py tidy` | Papers you dropped into Zotero by hand: metadata, title, URL, short title, tags, collection. |
| `/discover` · `zl.py discover` | Last N days of arXiv / HF papers scored against *your* tags. Nothing saved. |
| `/refs` · `zl.py refs <paper>` | References and citations (Semantic Scholar) split into "have" / "missing"; `--library` maps citations among your own papers. |
| `zl.py recheck` · `tag` · `untag` · `set` · `apply` | Re-verify venues and dates; single-item edits; approval-mode batch changes. |

Conventions: titles `[YYYY-MMDD] [Venue] Title` (v1 date, venue abbreviation, `[arXiv]` until accepted); URL field =
project page; tags `family:value` from `taxonomy.toml`, one reading status per item; PDFs saved by Zotero itself so
they sync everywhere; every write logged locally, nothing ever deleted.

## Works with

| Agent | reads | invoke |
|---|---|---|
| Claude Code | `CLAUDE.md` → `AGENTS.md`, `.claude/skills/` | `/download <link>` |
| Codex CLI | `AGENTS.md`, `.agents/skills/` | `$download <link>` (allow network: `[sandbox_workspace_write] network_access = true`) |
| Kimi Code CLI | `AGENTS.md`, `.agents/skills/` | `/skill:download <link>` |

One rule file, one set of skills in the [Agent Skills](https://agentskills.io) format; `.claude/skills` is a verbatim
copy that `zl.py setup` checks. Use it from any directory with `python3 zl.py install` (launcher `zl` on PATH +
user-level skills for all three agents; `--remove` undoes it). Ubuntu, macOS and Windows (`python zl.py ...`).

## How it decides

Rules from `taxonomy.toml` extract evidence and assign what clears the thresholds; an adjudicator — Ollama, an
OpenAI-compatible server, or the agent itself (`ZC_LLM`) — settles the candidates in `embod` / `tech` / `base`; it never
overrides a rule or the collection. On the author's 129 hand-tagged papers: rules 0.89 precision / 0.75 recall,
rules + qwen3.5:9b 0.87 / 0.81, 127 / 129 collections. Edit the taxonomy for your field, measure with
`tools/eval_classify.py`. Details, all numbers and the config: [docs/classifier.md](docs/classifier.md).

## Layout

```
zl.py  taxonomy.toml  AGENTS.md          entry point · your collections, tags, rules, venues · the agent's rules (CLAUDE.md imports it)
zotero_librarian/                        fetch / classify / llm / pipeline / connector / zapi / ... (stdlib only)
.agents/skills/  .claude/skills/         download · tidy · discover · refs  (source · verbatim copy)
docs/  tools/  CHANGELOG.md              classifier.md, notero.md · eval_classify.py, fix_pdf_names.js · one line per version
.env  cache/  inbox/  logs/              per machine, git-ignored
```

## Contributing

Issues and PRs welcome — taxonomies for other fields most of all. The procedure, step by step, is in
[CONTRIBUTING.md](CONTRIBUTING.md); commit descriptions and reviews follow Google's
[CL descriptions](https://google.github.io/eng-practices/review/developer/cl-descriptions.html) and
[standard of code review](https://google.github.io/eng-practices/review/reviewer/standard.html).

## Status · License

Used daily by its author on one robot-learning library from three machines; Zotero 7 and 10. The connector endpoints
are the ones the official browser connector uses, not a documented API. MIT.
