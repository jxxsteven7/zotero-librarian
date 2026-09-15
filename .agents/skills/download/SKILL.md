---
name: download
description: Add papers to the Zotero library from links or PDFs (fetch, classify, save, verify, log). Use when the user gives paper links or asks to add / download / save a paper.
---

# download — add papers to Zotero

The judgement is done by the scripts (`taxonomy.toml` rules + the local model, or you when `ZC_LLM=agent`); you run one
command, relay its report, and handle only what it marks. Never read the PDF or grep the full text yourself.

Arguments: one or more links or local PDF paths, space-separated (arXiv / DOI / OpenReview / PDF / project page / a
paper page with citation meta such as JMLR). A file with one link per line (a reading list, a bibliography): `--from-file FILE`
instead of the links. Ask which papers if none were given. On Windows use `python` instead of `python3`.

## Steps

1. Run (the command waits up to 150 s per paper for the server sync — allow a 10-minute
   tool timeout, and don't poll):

   ```
   python3 zl.py add <links...>
   ```

   For each paper it fetches metadata + PDF + full text, checks for duplicates, classifies (collection + tags with
   evidence), saves through the Zotero desktop app, waits for the cloud sync and verifies, commits the audit log,
   and finally prints a `| key | title | collection | tags | PDF | notes |` table.

2. Read the output and act only where needed (usually nowhere):
   - **saved**: glance at the evidence lines under "assign"; an obviously wrong tag (evidence is related work or a
     baseline) -> `python3 zl.py untag <key> <tag> --why <reason>`. Otherwise leave it.
   - **candidates** (listed, not assigned): put them in the report for the user to decide; one whose evidence clearly
     meets the definition in `taxonomy.toml` may be added right away with `python3 zl.py tag <key> a,b` — say so.
   - **PAUSE** (not saved; the exact command to finish is printed):
     - *collection undecided*: read the printed abstract, decide the collection, run the printed
       `python3 zl.py save <slug> --collection "..."` line (`--drop a,b` removes suggested tags).
     - *adjudication pending* (`ZC_LLM=agent`, an **ADJUDICATE** block): for each listed candidate decide from its
       definition, the evidence snippets and the setup excerpt whether the paper's *own* method or experiments meet
       the definition (a baseline, related work or a data-collection rig does not count). Run the printed line with
       `--confirm tag1,tag2` for the ones that do, `--confirm none` otherwise. Several papers -> one `save` line each.
   - **duplicate**: skipped by default; say which item already exists. `--force` only if the user insists.
   - **x** (error): the link was not recognized or metadata failed; tell the user why and ask for an arXiv/DOI link,
     the paper page, or the PDF.
   - **venue still `arXiv <- default`**: the script already checked the arXiv comment, PDF first page, Semantic Scholar,
     Crossref and the project page — don't search again; note "no acceptance found". If the user asks, search the web
     and fix with `python3 zl.py set <key> title="[date] [Venue] Title"`.
   - **sync unconfirmed**: the Zotero client hasn't uploaded the item yet; `python3 zl.py verify <key>` later. No polling.
   - The user says "read first": add `--first` (status:to-read-first).

3. **Report**: relay the printed table as is (don't rewrite it), then at most two or three sentences: candidates to
   confirm, flags that need the user's decision. The log and git are already handled by the script.

## Related commands

- Look before saving: `python3 zl.py fetch <link>` (full card) -> `python3 zl.py suggest <slug>` -> `python3 zl.py save <slug> ...`.
- Re-verify existing arXiv items: `python3 zl.py dump && python3 zl.py recheck [--dates] [--search]`; `--write` after approval.

## Don't

- Write to sqlite, or upload PDFs through the Web API (attachment sync is WebDAV; the clients would never see them).
- Change titles / tags of existing items on your own, create collections, or invent tags outside `taxonomy.toml`.
- Print the API key from `.env`.
