# taxonomy.toml — every key, and the scoring it drives

`taxonomy.toml` is the whole classification policy: the collections, the tag vocabulary with a definition per value, the
regex patterns and thresholds the rule engine scores with, and the venue abbreviations. The code interprets it and knows
nothing about the field. This page is the reference; [classifier.md](classifier.md) explains the design and the numbers.

## How a paper is scored

1. **Text.** Title + abstract form the *head*; the full text is the *body* after the reference list is cut (the last
   `References` / `Bibliography` heading past 30 % of the text; an appendix that follows the list is kept, since the robot
   setup usually lives there).
2. **Hits.** Every value's `patterns` (weight 1) and `weak` patterns (weight 0.5) are searched in both. A head hit counts
   only for strong patterns — a weak word in the abstract is not the paper speaking for itself. A hit preceded, within 60
   characters, by the `negative_context` regex is dropped in both head and body ("without depth or point-cloud inputs",
   "prior work uses parallel-jaw grippers").
3. **Level.** A head hit assigns the tag (`sure`), unless the value says `head = false`. Otherwise the weighted body count
   must reach `sure` to assign, or `maybe` to be listed as a candidate. Two evidence snippets per tag are kept and printed.
4. **Relations** between assigned tags: `excludes`, `implies`, `excluded_by`, `weak_with`, the family's `max`.
5. **Collection.** The `[[collections]]` are tried in file order; the first whose conditions hold wins; `default = true`
   is the fallback. Then the collection's `strip` and the `type:*` rules remove families that don't apply.
6. **Adjudication.** Candidates in `[llm] adjudicate_families` are shown to the adjudicator (local model or agent), which
   may promote them; it never removes an assigned tag or moves the paper.

Patterns are Python regexes. Each top-level alternative (split on `|`) is case-insensitive unless it contains an upper-case
letter — `reinforcement learning|\bRL\b` matches "Reinforcement Learning" and "RL" but not "rl" inside a word, and
`\bPanda\b` never matches "panda" the animal. Escape backslashes as `\\b` in TOML basic strings.

## `[library]`

| key | meaning |
|---|---|
| `default_status` | the status every new item gets (`status:to-read`) |
| `title_prefix` | `true`: titles become `[YYYY-MMDD] [Venue] Title`; `false`: no title is ever rewritten |
| `keep_bare_tags` | un-prefixed tags written by plugins (Notero's `notion`); never removed, hidden in reports |
| `negative_context` | regex; a pattern hit within 60 characters after a match is context, not the paper's own work |

## `[llm]`

| key | meaning |
|---|---|
| `adjudicate_families` | families whose candidates the adjudicator may promote; unset = every family. The shipped list (`embod`, `tech`, `base`) is what measured best with a 9B model on the author's library |

## `[[collections]]` — in the order they are tried

| key | meaning |
|---|---|
| `name` | exactly the collection name in Zotero |
| `description` | one line; the adjudicator reads it |
| `patterns` | regexes; head hits count 3 points each, body hits are counted separately |
| `min_score` | head score needed to win (default 3) |
| `max_other` | ...and no other non-default collection may score above this |
| `tag_bonus` | `{ "embod:*" = 6, "method:vla" = 6 }`: points added when an assigned tag matches (`*` wildcard) |
| `title_patterns` | +6 when the title matches any of them |
| `requires` | tags that must be assigned for this collection to be considered (`["embod:humanoid"]`) |
| `not_in_title` | regexes; a title match disqualifies the collection |
| `body_fallback` | no head hit for any collection: win if the body has at least this many hits and every other collection at most 3 |
| `boundary_with` | the neighbouring collection; if its `boundary_patterns` (else `title_patterns`, else `patterns`) also hit the abstract and its `requires` hold, the paper is flagged |
| `boundary_patterns` | what "also does the other thing" looks like in an abstract, used by the neighbour's `boundary_with` |
| `boundary_pause` | `true` (default): the boundary flag pauses the pipeline (a human picks the collection); `false`: a note suggesting `--also` |
| `status_only` | items here carry only a status tag; every family is emptied |
| `strip` | families never assigned in this collection (they become candidates instead) |
| `survey_home` | a `type:survey` filed elsewhere is also added to this collection |
| `default` | the fallback when nothing wins; if another collection still had head hits, the paper is flagged and pauses |

## `[families.<family>]`

| key | meaning |
|---|---|
| `description` | one line for the adjudicator |
| `max` | at most this many values per paper; the overflow (ranked by head hits, then body) becomes candidates |
| `context` | regex of fine-tuning verbs (the `base` family): a value is assigned only where its name co-occurs with this within a sentence of the abstract; two or more body co-occurrences make it a candidate; a name in the title means the paper's own model, never a base |

`status` and `type` are special families (below); every other family is a *judgement* family and gets the flags
"no embodiment found" / "no method found" when it stays empty (only for families named `embod` / `method`).

## `[families.<family>.values.<value>]`

| key | meaning |
|---|---|
| `description` | the definition — the actual policy the adjudicator applies; keep it precise |
| `patterns` | strong regexes (weight 1); for a `context` family the first one is the model's name |
| `weak` | regexes at weight 0.5; never count in the head |
| `sure` | weighted body hits that assign the tag without a head hit (`999` = never from the body alone) |
| `maybe` | weighted body hits that make it a candidate |
| `head` | `false`: a head hit alone is a candidate, not an assignment (e.g. teleop, which abstracts mention as data collection) |
| `head_requires` | with `head = false`: regex on title + abstract that does assign ("we propose ... teleoperation") |
| `title_requires` | with `head = false`: regex on the title that does assign |
| `title_maybe` | with `head = false`: regex on the title that keeps it a candidate with a question for the user |
| `implies` | tags assigned along with this one (`method:vla` implies `modality:vision`, `modality:language`) |
| `excludes` | tags removed when this one is assigned: a string, or `{ tag = ..., unless = regex, min = N, unless_title = regex }` — kept when `unless` matches the abstract or at least `min` times the body, or `unless_title` matches the title |
| `excluded_by` | this tag is dropped when any of the listed tags is assigned |
| `weak_with` | without a head hit, this tag becomes a candidate when any listed tag is assigned (`modality:vision` when the paper uses point clouds: the cameras may only feed those) |

## `[families.type.values.<value>]` — publication type

| key | meaning |
|---|---|
| `title` | regex on the title (`\bsurvey\b|\breview\b`) |
| `introduce` | regex matched after "we introduce / present / release" in the abstract ("we introduce ... benchmark") |
| `strip` | families emptied for this type (a survey talks about everyone's hardware) |
| `head_only` | families that keep only values with a head hit |

`type:survey` is the value `survey_home` looks for.

## `[families.status]`

| key | meaning |
|---|---|
| `read_axis` | the reading-progress values, in order; exactly one per item, never downgraded by the scripts |
| `values` | every allowed status value (the read axis plus presentation / reproduction axes) |

## `[[venues]]` and `[venues_misc]`

| key | meaning |
|---|---|
| `abbr` | what goes in the title's second bracket |
| `match` | regexes tried on free text: journal / conference names, arXiv comments, PDF first pages, project pages |
| `name` | full journal name, matched as a case-insensitive substring of the publication title |
| `accept_context` | (`[venues_misc]`) free text counts as an acceptance statement only if it contains this regex — "Accepted to CoRL 2026", not "we compare with CoRL 2024 baselines" |

## Changing it

- **A new value**: add `[families.<f>.values.<v>]` with a `description` and `patterns`; start with `sure = 999` (head hit
  only) and a `maybe` around 2–3, then look at what `python3 tools/eval_classify.py --errors` lists. Values outside the
  file are never written; the scripts warn on `zl.py tag` with an unknown value.
- **A new venue**: a `[[venues]]` entry with `abbr` and `match` (conferences) or `name` (journals). Until it is there the
  scripts print `full name, no abbreviation !` in the venue source and keep the full name.
- **A pattern that misfires**: check the evidence line the report printed, then tighten the regex or raise the threshold
  in the file. Never in the code.
- **Measure** before and after: `python3 tools/eval_classify.py` (rules) and `--llm` (with the adjudicator) score the
  classifier against the tags your library already carries; `--show KEY` prints one paper's evidence, `--only K1,K2`
  restricts the run. Precision must not drop. A fixed corner case gets a synthetic paper in `tests/test_classify.py`.

## Another field

Copy the file, keep the `[library]`, `[families.status]` and `[venues_misc]` blocks, and replace the rest: the collections
(exact Zotero names, in the order they should be tried, one `default = true`), the judgement families and their values with
definitions and patterns, the `type` values if they differ, the venues of the field. The family names are free — only
`status` and `type` are special, and the flags for empty `embod` / `method` simply don't fire when those families don't
exist. Then run `zl.py tidy --dry-run --limit 20` on your library, tune, measure with `tools/eval_classify.py`, and send it
as `taxonomies/<field>.toml` with the numbers (the [issue template](../.github/ISSUE_TEMPLATE/taxonomy.md) asks for them).
