---
name: discover
description: Find recent arXiv / Hugging Face papers scored against the library's taxonomy tags; prints a table, saves nothing. Use when the user asks what is new in a topic or for papers from the last N days.
---

# discover — recent papers scored against the taxonomy

Scans the last N days of arXiv categories (plus Hugging Face daily papers), runs every title + abstract through the
rule classifier, drops what is already in the library, and prints a table with the tags each paper would get.
Nothing is saved; the user picks and then runs `download`.

Arguments: free text, e.g. `7 days cs.RO dexterous hand tactile`, `--days 14 --tags embod:humanoid`,
`--query "in-hand"`. Map it to options:

```
python3 zc.py discover [--days N (7)] [--cat cs.RO,cs.AI (cs.RO)] [--tags a,b] [--all] [--query REGEX] [--source arxiv,hf] [--max 400]
```

- `--tags`: wanted tags from `taxonomy.toml`; papers matching any of them are kept (`--all`: all of them). Free-text
  topics that are not tags become `--query` (a case-insensitive regex on title + abstract).
- The arXiv API is often rate-limited (429); the script then falls back to the RSS feed, which only covers the latest
  announcement day — say so in the report if it happened.
- Relay the table (number, date, arXiv id, title, collection, tags). Suggest at most a handful to add; the user decides.
  Add with the `download` skill and the arXiv id.
