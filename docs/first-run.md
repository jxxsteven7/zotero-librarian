# First run on a library that is already there

You don't start from an empty Zotero. The same command that handles a paper you dragged in by hand — `zl.py tidy` —
organizes the whole existing library on its first run: it takes every item that has no `status:` tag yet (which, in
a library nobody has organized with this tool, is every item) and gives it the full treatment: missing metadata from
arXiv / Crossref / the page, the title convention, URL = project page, Short Title, tags with evidence, a collection.
There is no separate "one-click organize" — this is it, and it is the same code path as everyday use, so what it does
on day one is exactly what it will keep doing.

## What it organizes by — the two files that are the policy

- **`taxonomy.toml`** is the whole classification policy and it is yours to edit: the collections (in the order
  they are tried, with the conditions to win one), the tag families and values with a one-line definition each
  (that definition is what the adjudicating model reads), the regex patterns and thresholds behind every tag, the
  venue abbreviations, and the library settings (`default_status`, `title_prefix`). The shipped file is the author's
  robot-learning taxonomy; replace the collections and values with your field's. The code knows nothing about the
  domain. How the rules and thresholds work: [classifier.md](classifier.md).
- **`AGENTS.md`** is the policy for the agent: what may be written, through which path, what needs the human.

Nothing else decides anything. If a paper lands in the wrong place, the fix is a pattern or a threshold in
`taxonomy.toml`, measured with `tools/eval_classify.py` — not a prompt.

## Step by step

1. **Edit `taxonomy.toml`** (or keep the shipped one to see how it behaves first). Collection names must be exactly
   the names you want in Zotero. If you don't want titles rewritten as `[YYYY-MMDD] [Venue] Title`, set
   `title_prefix = false` in `[library]` — every other convention still applies.
2. **`python3 zl.py setup`** — besides the machine checks it tells you which of the taxonomy's collections don't
   exist in your library yet. In Zotero itself, turn off *Settings > General > Automatically tag items with keywords
   and subject headings* on every client (`extensions.zotero.automaticTags`, a per-client setting): otherwise the
   connector adds publisher keywords as bare tags next to the vocabulary.
3. **Choose the adjudicator for the bulk run.** `ZC_LLM=ollama` (free, ~2 s per paper) or `ZC_LLM=off` (rules only,
   borderline tags listed as candidates). `ZC_LLM=agent` pauses for every paper that has candidates, which is fine
   for one paper a day and tedious for three hundred.
4. **Sample the plan, nothing written:** `python3 zl.py tidy --dry-run --limit 20`. Read the twenty: are the
   collections right, do the evidence lines under "assign" justify the tags? Adjust patterns or thresholds, run again.
   `--dry-run` without `--limit` prints the plan for the whole library.
5. **Run it:** `python3 zl.py tidy --create-collections`. The missing collections are created through the Web API
   (the only time the scripts ever create one); every item is written through the Web API with optimistic locking and
   appended to `logs/zotero-organize.log.md`; the Zotero client syncs the changes down within a minute. Items whose
   collection is genuinely ambiguous are printed as `PAUSE` with the exact command to finish each one
   (`zl.py tidy --only KEY --collection "..."`) — decide those from the printed abstract.
6. **Afterwards** every item carries a `status:` tag, so `tidy` from now on only touches new hand-added items, and
   `/download` handles new links. Correct single tags with `zl.py tag / untag`, batch corrections with `zl.py apply`.

Two things the first run never does: it doesn't delete or move away anything (collections you already had stay, tags you
already had stay — the scripts only add), and it doesn't rewrite a title that already has a `[date] [venue]` prefix
into something worse (a known venue is never replaced by `????`).

## Measuring after the first run

`tools/eval_classify.py` compares the classifier with the tags the library carries. Right after an automatic first
run that comparison is circular — the library's tags *are* the classifier's output. It becomes meaningful once you
have corrected items by hand: then it tells you where the rules disagree with your judgement, which is where to tune.
