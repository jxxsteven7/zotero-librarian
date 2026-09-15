# zotero-librarian

Keep a Zotero library organized from your coding agent — [Claude Code](https://claude.com/claude-code),
[Codex](https://developers.openai.com/codex), [Kimi Code CLI](https://github.com/MoonshotAI/kimi-cli) — without
spending tokens on the organizing.

Give it a link. It fetches the metadata and PDF, checks for duplicates, finds the published venue and the project page,
files the paper into the right collection, tags it from a controlled vocabulary **with the evidence for every tag**,
saves it through your running Zotero, waits for the cloud sync, writes an audit log, and reports. Rules live in a
config file; a local model (Ollama) — or, if you have no GPU to spare, the agent itself — makes the borderline calls;
the agent otherwise only reads the report.

```
$ python3 zc.py add https://arxiv.org/abs/2607.11481
=== 2607.11481  (arxiv: 2607.11481)
  title     : [2026-0713] [arXiv] Towards Human-level Dexterous Teleoperation   short: TeleDexter
  authors   : Puhao Li, Zeyuan Chen, Yingying Wu ...
  date      : 2026-07-13 <- arxiv:v1   venue: arXiv <- default
  URL       : https://bigai-dex.github.io/blog/teledexter/
  PDF       : ok <- https://arxiv.org/pdf/2607.11481
  collection: Dex-Manipulation
  assign    : method:teleop, method:rl, embod:dex-hand, embod:single-arm
      method:teleop            <- title: ...Towards Human-level Dexterous Teleoperation...
      method:rl                <- abstract: ...The entire pipeline requires only single-stage RL and, with random action masking and domain randomization, transfers zero-shot...
      embod:dex-hand           <- abstract: ...long-horizon tool use across two dexterous hands, achieving a 75% average success rate...
      embod:single-arm         <- body x2: ...All real-world experiments are conducted on a Franka FR3 arm equipped with a dexterous robot hand...
  candidates: (not assigned — discuss with the user)
      modality:vision          6 weighted body hits, not in the abstract — could be related work or a baseline — the model agrees it applies
      method:policy-learning   at most 2 method tags; this ranked #3
  model     : qwen3.5:9b (confidence 1.0) — The paper introduces a teleoperation system for dexterous hands trained via RL, deployed on a single-arm setup.
saved U3HFYV4Q | [2026-0713] [arXiv] Towards Human-level Dexterous Teleoperation
  sync      : ok server v3540 | collections ['Dex-Manipulation'] | tags ['embod:dex-hand', 'embod:single-arm', 'method:rl', 'method:teleop', 'status:to-read']

| key | title | collection | tags | PDF | notes |
|---|---|---|---|---|---|
| `U3HFYV4Q` | [2026-0713] [arXiv] Towards Human-level Dexterous Teleoperation | Dex-Manipulation | method:teleop, method:rl, embod:dex-hand, embod:single-arm, status:to-read | yes | sync ok. candidates: `modality:vision` (...), `method:policy-learning` (...) |
```

## Why this exists — and why you still read the papers

Reading papers is how understanding is built, and nobody can do that for you; a summary written by a model is someone
else's reading. This tool deliberately stops before that point. It does the part of the work that carries no insight
but eats the afternoon — finding the PDF, checking whether you already have it, working out where it was published,
naming the file, deciding which folder and which tags, keeping the library consistent across machines — so that a paper
goes from "saw the link" to "sitting in the right place with the right tags, ready to read" in one command. The tags are
a reading aid, not a substitute: every one comes with the sentence that justified it, and the borderline ones are
left for you to decide. Then you open the PDF and read it yourself, and the library you end up with is one you actually
know. `discover` and `refs` serve the same purpose upstream: they shorten the search for what to read next, not the reading.

## What it does

| Command | |
|---|---|
| `zc.py add <links...>` | The pipeline above. Accepts arXiv (abs / pdf / bare id / alphaxiv / HF papers), DOI, OpenReview, direct PDF links, local PDFs, project pages, and paper pages with `citation_*` meta (JMLR, PMLR, ACL). Pauses when the collection is genuinely ambiguous and prints the command to finish. |
| `zc.py tidy` | Same treatment for papers you dropped into Zotero by hand: finds items without a status tag, fills metadata, formats the title, sets URL and Short Title, classifies, files. |
| `zc.py discover` | Recent arXiv papers (and Hugging Face daily papers) scored against *your* tags. Nothing saved; pick and `add`. |
| `zc.py refs <paper>` / `--library` | References and citations from Semantic Scholar, split into "already in your library" and "missing, by citation count"; or the citation graph among your own papers. |
| `zc.py recheck` | Re-verify existing arXiv items: accepted somewhere since? Is the title date the v1 date? |
| `zc.py tag / untag / collect / set / verify` | Single-item edits through the Web API, each with optimistic locking and an audit-log line. |
| `zc.py apply` | Approval-mode batch changes (vocabulary renames, corrections across many items). |
| `zc.py setup` | New-machine health check with the fix for every missing piece. |

The skills `download`, `tidy`, `discover`, `refs` are thin wrappers that run these commands and relay the report — the
agent never reads PDFs or greps for hardware names itself. Saving tokens is the design rule: anything a script or a
local model can decide is decided there.

### Conventions it enforces

- **Title** `[YYYY-MMDD] [Venue] Original title` — the date is the day the paper first appeared (arXiv v1, or the
  earlier preprint of a journal paper), the venue is an abbreviation from your table. Preprints stay `[arXiv]` until an
  acceptance is found in the arXiv comment, the PDF's first page, Semantic Scholar, Crossref or the project page.
- **URL field = project page** when one exists (found in the arXiv comment, abstract, PDF text and PDF link
  annotations), otherwise the arXiv / DOI link. **Short Title** = the paper's short name. Both flow into Notion if you
  mirror the library with [Notero](https://github.com/dvanoni/notero) (`docs/notero.md`).
- **Tags** are `family:value` from a controlled vocabulary with written definitions; every item has exactly one reading
  status. A tag is assigned only when the paper's own method or experiments use the thing — not when related work
  mentions it.
- **PDFs are saved by Zotero itself** through the desktop connector endpoint, so they sync like any other attachment
  (including WebDAV setups, where Web-API uploads never reach the clients).
- **Everything is logged** (`logs/zotero-organize.log.md`, local to the machine), and nothing is ever deleted by the scripts.

## Works with Claude Code, Codex, Kimi Code CLI

The agent-facing part is two plain-text things every current coding agent understands: `AGENTS.md` (the rules) and
skills in the [Agent Skills](https://agentskills.io) format under `.agents/skills/`.

| Agent | reads | run a skill | notes |
|---|---|---|---|
| Claude Code | `CLAUDE.md` (imports `AGENTS.md`), `.claude/skills/` | `/download <link>` | `.claude/skills` is a verbatim copy of `.agents/skills`; `zc.py setup` checks they match, `--sync-skills` copies |
| Codex CLI | `AGENTS.md`, `.agents/skills/` | `$download <link>` | the sandbox blocks network by default — allow it (`network_access = true` under `[sandbox_workspace_write]` in `~/.codex/config.toml`) or approve the command |
| Kimi Code CLI | `AGENTS.md`, `.agents/skills/` (and `.claude/skills/`) | `/skill:download <link>` | |
| anything else that reads `AGENTS.md` | | tell it to follow `.agents/skills/download/SKILL.md` | the skill files are ordinary Markdown |

The skills never depend on agent-specific features; each one is "run this command, relay the table, handle PAUSE rows".

## The taxonomy is yours

`taxonomy.toml` defines the collections, the tag families and values (with the one-line definitions the local model
reads), the regex patterns and thresholds the rule engine uses, and the venue abbreviations. The shipped file is a
robot-learning taxonomy (manipulation, humanoids, VLAs, tactile sensing...). Edit it for your field; the code doesn't
know what a gripper is.

```toml
[families.modality.values.tactile]
description = "Tactile / force sensing is policy input."
patterns = ["tactile"]
weak = ["\\bGelSight\\b|\\bFSR\\b|force[- ]torque|contact (force|sensing|sensors?)|touch sens"]
sure = 12.5      # weighted body hits needed to assign without an abstract mention
maybe = 2.5      # ... to list as a candidate
```

Then measure: `python3 tools/eval_classify.py` scores the classifier against the items you already tagged by hand
(precision / recall per family, the most over- and under-assigned tags, `--errors` for every disagreement). On the
author's library of 129 reviewed papers:

| classifier | collection accuracy | tag precision | tag recall |
|---|---|---|---|
| rules only | 127 / 129 | 0.89 | 0.75 |
| rules + local LLM adjudicating (qwen3.5:9b, default policy) | 127 / 129 | 0.87 | 0.81 |
| rules + local LLM adjudicating (qwen3.5:27b) | 127 / 129 | 0.88 | 0.80 |
| rules + a perfect adjudicator (ceiling for `ZC_LLM=agent`) | 127 / 129 | 0.91 | 0.82 |
| qwen3.5:9b alone (no rules) | 116 / 129 | 0.64 | 0.77 |
| qwen3.5:27b alone (no rules) | 121 / 129 | 0.81 | 0.83 |

Three quarters of the tags the rules miss appear as candidates in the report, so the human sees them anyway.
A 3x larger model is much better on its own but adds nothing in the adjudicator role — the rules already supply the
discipline it lacks — so the default stays with the small, fast one. These numbers are in-sample (the thresholds were
tuned on the same items); expect somewhat lower on new papers.

## Who adjudicates: a local model, the agent, or nobody

Classification is rules first: the rule engine turns the paper's title, abstract and full text into evidence snippets
per tag and assigns what clears the thresholds. What is left are *candidates* — tags with some evidence but not enough.
An adjudicator reads the taxonomy definitions plus that evidence and decides them. Measured on the library above,
letting a 9B model *decide* everything was worse than the rules (0.75 precision); letting it adjudicate only `embod`,
`tech` and `base` gained recall at almost no cost — that is the default (`[llm].adjudicate_families` in
`taxonomy.toml`). The adjudicator never overrides a rule-assigned tag or the collection; disagreements are printed.

`ZC_LLM` in `.env` picks the adjudicator:

```
ZC_LLM=ollama                      # ollama | openai | agent | off
ZC_LLM_MODEL=qwen3.5:9b            # any model you have pulled; bigger is better, 9B runs in ~2 s per paper on a desktop GPU
ZC_LLM_URL=http://127.0.0.1:11434  # Ollama default; for openai: the base URL of any OpenAI-compatible server
ZC_LLM_KEY=                        # openai only (hosted APIs)
```

- **Ollama** (default, free): install from [ollama.com](https://ollama.com), `ollama pull qwen3.5:9b` (or any instruct
  model; ~6 GB of RAM or VRAM), done. Structured JSON output and `think: false` are requested, so reasoning models don't
  spend time thinking.
- **OpenAI-compatible** (`ZC_LLM=openai`): LM Studio, vLLM, llama.cpp server, or a hosted API with a key.
- **The agent** (`ZC_LLM=agent`): no local model — for a laptop without a GPU or spare RAM. The script prints an
  `ADJUDICATE` block (each candidate with its definition, the evidence sentences and the experimental-setup excerpt,
  ~1.3 KB) and pauses; the agent answers on the printed command with `--confirm tag1,tag2` or `--confirm none`, and the
  answer goes through the same merge as a model's. Only candidates a model could promote are asked about, so on the
  library above 51 of 129 papers would ask, ~350 tokens each; the other 78 cost nothing. This is the one place the
  agent spends tokens on judgement.
- **Off** (`ZC_LLM=off`): rules only; candidates are listed for you. Also the automatic fallback when the model server
  is unreachable (the report says so).

`zc.py setup` reports which adjudicator is active and whether it is reachable; `tools/eval_classify.py --llm` measures
a model on your library (answers are cached, so comparing merge policies is free after the first run).

## Install

Requirements: Python 3.11+ (standard library only), `pdftotext` (poppler) or `pip install pypdf`, Zotero 7+ desktop
with sync enabled, a Zotero Web API key.

```bash
git clone https://github.com/jxxsteven7/zotero-librarian.git ~/zotero-librarian
cd ~/zotero-librarian
cp .env.example .env      # ZOTERO_API_KEY, ZOTERO_LIBRARY_ID; the data directory is auto-detected (chmod 600 .env)
./setup.sh                # health check: Python / .env / data dir / taxonomy / pdftotext / HTTPS / Zotero / API key / adjudicator / skills
claude                    # or codex, or kimi — open the agent here and use the download skill: /download <link>
```

| Platform | pdftotext | Notes |
|---|---|---|
| Ubuntu | `sudo apt install poppler-utils` | system `python3` 3.12 is fine |
| macOS | `brew install poppler` | python.org installers need `Install Certificates.command` once, or HTTPS fails; Homebrew / conda Python is fine |
| Windows | `winget install --id oschwartz10612.Poppler -e` (or scoop / choco), reopen the terminal | use `python zc.py ...`; Zotero data is usually `C:\Users\you\Zotero` |
| any conda env | `conda install -c conda-forge poppler` | the interpreter that runs the scripts also finds its own env's pdftotext |

`.env`, `cache/` and `inbox/` are git-ignored. Zotero-side settings: turn off `automaticTags` (per client) and, once,
set the attachment rename template so file names don't inherit the title prefix (see `AGENTS.md`).

## How it fits together

```
zc.py                     entry point (the short name predates the rename; `python3 zc.py --help`)
taxonomy.toml             your collections, tags, rules, venues
AGENTS.md                 the agent's rules: how the library is accessed, what it may do, how to use the reports (CLAUDE.md imports it)
zotero_librarian/
  fetch / sources / pdf / published / titles   metadata, PDFs, venue lookup, title format
  classify / llm                               rule engine with evidence; adjudication by a local model or the agent
  connector / zapi / localdb                   Zotero desktop connector (new items + PDF), Web API (edits), read-only sqlite
  pipeline / discover / citations / recheck    the commands
.agents/skills/           download / tidy / discover / refs (Agent Skills format); .claude/skills/ is the copy Claude Code reads
logs/                     audit log (local, git-ignored)
tools/                    eval_classify.py, fix_pdf_names.js
```

Reading the local database while Zotero runs: Zotero 7+ keeps the database in WAL mode and holds an exclusive lock;
`config.connect_ro()` copies the main file plus WAL to a temp directory and opens the copy, so reads are current
and never touch the live file.

## Status

Used daily by its author on one library (robot learning, ~130 papers) from Ubuntu, macOS and Windows. The Zotero
connector endpoints it uses are the ones the official browser connector uses, but they are not a documented public
API; tested with Zotero 7 and 10. Semantic Scholar without a key is rate-limited; arXiv's export API often returns
429 from shared networks, in which case the scripts scrape the abs pages instead.

Contributions welcome — especially taxonomies for other fields, and eval results on other libraries. One feature per
PR; the merge commit is titled `vX.Y: ...`, bumps `__version__` and adds a line to `CHANGELOG.md` (rules for agents
and humans alike are in `AGENTS.md`). Skills live in `.agents/skills/` and must stay agent-neutral; the code must run
on Ubuntu, macOS and Windows with the standard library only.

## License

MIT
