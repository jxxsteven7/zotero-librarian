---
name: refs
description: Citation neighbourhood of one paper (references and citations from Semantic Scholar, cross-checked with the library) or the citation graph among library papers. Use when the user asks what a paper builds on, who cites it, or what to read first.
---

# refs — citation neighbourhood of a paper, cross-checked with the library

Semantic Scholar references and citations of one paper, split into "already in the library" (reading order by year)
and "not in the library" (ranked by citation count). `--library` instead maps the citation links *between* library
papers (the most-cited-within-library papers are the ones to read first).

Arguments: a library key, an arXiv id / link, or a DOI; or `library`.

```
python3 zl.py refs <key|arXiv|DOI|link> [--top 15]
python3 zl.py refs --library [--top 20]        # ~1 request per library paper, cached in cache/s2/
```

Relay the printed lists; point out which references the user already has and which highly cited ones are missing.
Add with the `download` skill (arXiv id or DOI). Without `S2_API_KEY` in `.env` the API allows about one request per
second; `--library` on a large library takes a few minutes the first time.
