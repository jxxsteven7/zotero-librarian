# /tidy — organize items that were dropped into Zotero by hand

For papers the user added directly in Zotero (dragged a PDF in, used the browser connector...). Those items have no
`status:` tag yet; `zc.py tidy` finds them and does what `/download` does, through the Web API: fills missing metadata
(arXiv / Crossref / page meta), formats the title, sets the URL (project page) and Short Title, classifies, files them
into a collection, logs and commits.

`$ARGUMENTS` (optional): item keys to restrict to, e.g. `ABCD1234,EFGH5678`.

## Steps

1. ```
   python3 zc.py tidy [--only KEYS]
   ```
   Add `--dry-run` first if the user wants to see the plan before anything is written. Zotero must have synced the
   items to the server (it does within a minute of adding them); an item "not on the server" just needs a moment.

2. Handle the output exactly like `/download`: **PAUSE** rows (collection uncertain) -> decide from the printed
   abstract and run the `python3 zc.py tidy --only <key> --collection "..."` line; candidates -> report them;
   obviously wrong tags -> `python3 zc.py untag`.

3. Relay the printed table; two or three sentences at most on what needs the user's decision.

Notes: an existing `[date] [venue]` prefix is never made worse (a known venue is not replaced by `????`); an item
without arXiv id / DOI / page metadata keeps its item date and gets `[????]` as venue — mention it so the user can
fix it with `python3 zc.py set <key> title="..."`.
