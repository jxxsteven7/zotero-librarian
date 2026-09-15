"""Loads taxonomy.toml — collections, tag vocabulary, classification rules, venue abbreviations.
Everything that is specific to *this* library lives in that file; the code only interprets it."""
import re
import tomllib

from .config import TAXONOMY_PATH

with open(TAXONOMY_PATH, "rb") as _f:
    T = tomllib.load(_f)

LIB = T.get("library", {})
DEFAULT_STATUS = LIB.get("default_status", "to-read")
TITLE_PREFIX = bool(LIB.get("title_prefix", True))
KEEP_BARE_TAGS = set(LIB.get("keep_bare_tags", []))
NEGATIVE_CONTEXT = re.compile(LIB["negative_context"], re.I) if LIB.get("negative_context") else None

COLLECTION_RULES = T["collections"]                       # ordered list of dicts
COLLECTIONS = tuple(c["name"] for c in COLLECTION_RULES)
DEFAULT_COLLECTION = next((c["name"] for c in COLLECTION_RULES if c.get("default")), COLLECTIONS[-1])
SURVEY_HOME = next((c["name"] for c in COLLECTION_RULES if c.get("survey_home")), None)

FAMILY_RULES = T["families"]
STATUS = FAMILY_RULES["status"]
READ_AXIS = tuple(STATUS["read_axis"])
FAMILIES = tuple(f for f in FAMILY_RULES if f not in ("status", "type"))     # the judgement families (not status / type)
VOCAB = {f: (set(v["values"]) if isinstance(v.get("values"), list) else set(v.get("values", {}))) for f, v in FAMILY_RULES.items()}

# tag -> rule dict (patterns, weak, sure, maybe, head, ...) for the families the classifier scores
RULES = {}
for _fam, _spec in FAMILY_RULES.items():
    if _fam == "status" or not isinstance(_spec.get("values"), dict): continue
    for _val, _r in _spec["values"].items():
        RULES[f"{_fam}:{_val}"] = dict(_r, family=_fam, value=_val, description=_r.get("description", ""))

LLM = T.get("llm", {})
ADJUDICATE = set(LLM.get("adjudicate_families", FAMILIES))   # families where the adjudicator may promote a candidate; default: all
VENUES = T.get("venues", [])
VENUE_MISC = T.get("venues_misc", {})


def check_tags(tags):
    """Warn (don't block) on tags outside the vocabulary — the user may have approved a new value. Returns the warnings."""
    warns = []
    for t in tags:
        if t in KEEP_BARE_TAGS: continue
        m = re.fullmatch(r"([a-z]+):([a-z0-9.\-]+)", t)
        if not m: warns.append(f"tag {t!r} is not family:value (written anyway — please check)"); continue
        if m.group(1) not in VOCAB: warns.append(f"tag family {m.group(1)!r} is not in taxonomy.toml")
        elif m.group(2) not in VOCAB[m.group(1)]: warns.append(f"{t!r} is not in taxonomy.toml (only use values the user approved)")
    for w in warns: print("  ! " + w)
    return warns


_ORDER = {f: i for i, f in enumerate(FAMILY_RULES)}


def sort_tags(tags):
    """Family order as in taxonomy.toml, status last."""
    return sorted(set(tags), key=lambda t: (_ORDER.get(t.split(":")[0], 99), t))


def with_status(tags, have=()):
    """Every item carries exactly one reading status: add the default unless the item or the new tags already have one."""
    if any(t.startswith("status:") for t in list(have) + list(tags)): return list(tags)
    return sort_tags(list(tags) + ["status:" + DEFAULT_STATUS])


def policy_text():
    """The taxonomy rendered as plain text for the LLM prompt (descriptions are the policy)."""
    out = ["COLLECTIONS (file the paper in exactly one; the first matching rule wins):"]
    for c in COLLECTION_RULES:
        out.append(f"- {c['name']}: {c['description']}")
    out.append("\nTAG FAMILIES (assign only values whose definition the paper's own method/experiments satisfy; leave a family empty if unsure):")
    for fam, spec in FAMILY_RULES.items():
        if fam == "status": continue
        vals = spec.get("values", {})
        head = f"- {fam}: {spec.get('description', '')}" + (f" (at most {spec['max']})" if spec.get("max") else "")
        out.append(head)
        for v, r in (vals.items() if isinstance(vals, dict) else []):
            out.append(f"    {fam}:{v} — {r.get('description', '')}")
    return "\n".join(out)
