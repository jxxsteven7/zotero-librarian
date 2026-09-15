# How papers are classified

Rules first, an adjudicator second, the human last. Everything the classifier may assign is in `taxonomy.toml`.

## The taxonomy is yours (taxonomy.toml)

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

Every key the file accepts, and the scoring behind them, is in [taxonomy.md](taxonomy.md).

Then measure: `python3 tools/eval_classify.py` scores the classifier against the items you already tagged by hand
(precision / recall per family, the most over- and under-assigned tags, `--errors` for every disagreement). On the
author's library of 138 reviewed papers (2026-09-15, v0.6 classifier):

| classifier | collection accuracy | tag precision | tag recall |
|---|---|---|---|
| rules only | 136 / 138 | 0.90 | 0.77 |
| rules + local LLM adjudicating (qwen3.5:9b, default policy) | 135 / 137 | 0.88 | 0.83 |
| rules + local LLM adjudicating (qwen3.5:27b) — measured on 129 papers before v0.6 | 127 / 129 | 0.88 | 0.80 |
| rules + a perfect adjudicator (ceiling for `ZC_LLM=agent`) — same 129 | 127 / 129 | 0.91 | 0.82 |
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

`zl.py setup` reports which adjudicator is active and whether it is reachable; `tools/eval_classify.py --llm` measures
a model on your library (answers are cached, so comparing merge policies is free after the first run).
