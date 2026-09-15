"""Rule-based classifier: turns taxonomy.toml patterns into evidence-backed collection / tag suggestions.

    suggest(title, abstract, text) -> dict(collection, also, sure, maybe, flags, evidence)

Three output tiers:
  sure  — meets the "substantively used" bar; `zl.py add` assigns these directly
  maybe — borderline (few body mentions, or suppressed by an exclusion rule); listed for the user, not assigned
  flags — things a human should glance at (collection boundary, no embodiment found, abstract-only judgement...)
Principles: a title/abstract mention is the paper speaking for itself; body mentions must be frequent (related work and
baselines mention everything once or twice). The reference list is cut first, otherwise every cited "Diffusion Policy" hits.
Thresholds were tuned on the library's own reviewed items (tools/eval_classify.py); re-run it after editing the rules.
The LLM classifier (llm.py) consumes the evidence this module extracts, so keep the patterns broad and the thresholds strict.
"""
import copy, re, shutil

from . import taxonomy as tx

REFS_RE = re.compile(r"\n\s*(references|bibliography)\s*\n", re.I)
_rx_cache = {}


def _alternatives(pat):
    """Split a regex on its top-level `|` (parentheses and escapes respected)."""
    out, depth, cur, i = [], 0, "", 0
    while i < len(pat):
        ch = pat[i]
        if ch == "\\": cur += pat[i:i + 2]; i += 2; continue
        if ch == "(": depth += 1
        elif ch == ")": depth -= 1
        if ch == "|" and depth == 0: out.append(cur); cur = ""
        else: cur += ch
        i += 1
    return out + [cur]


def _rx(pat):
    """Each top-level alternative is case-insensitive unless it contains an upper-case letter (a proper noun or acronym:
    `Panda`, `RL`, `DDPM`), which is matched as written. So `reinforcement learning|\\bRL\\b` catches both a Title Case
    title and the acronym without letting `rl` inside a word match."""
    if pat not in _rx_cache:
        cs = lambda a: re.search(r"\\b[A-Z]|[A-Z]{2}|[A-Z][a-z]", a)
        _rx_cache[pat] = re.compile("|".join(a if cs(a) else f"(?i:{a})" for a in _alternatives(pat)))
    return _rx_cache[pat]


APPENDIX_RE = re.compile(r"^\s*(appendix|appendices|supplementary|supplemental)\b", re.I)
APPENDIX_LETTER_RE = re.compile(r"^\s*[A-Z]\.?\s*$|^\s*[A-Z]\.\d+\s*$|^\s*[A-Z]\.?\s+[A-Z][^,.;:]{2,60}\s*$")   # "A", "A.1", "A Dataset Details"
REFLINE_RE = re.compile(r"\b(19|20)\d\d\b|arxiv|doi\.org|\bpp\.|\bIn Proc|\bURL\b", re.I)


def cut_refs(text):
    """Drop the reference list: from the last 'References' heading to the appendix that follows it, if any. NeurIPS / CoRL
    style puts the appendix after the references, and the robot setup is usually there; an appendix before the list is kept."""
    if not text: return ""
    hits = list(REFS_RE.finditer(text))
    if not hits: return text
    cut = hits[-1].start()
    if cut <= len(text) * 0.3: return text                          # a heading that early is a table of contents, not the list
    lines = text[cut:].split("\n")
    for i, line in enumerate(lines[2:], 2):                         # 0-1 are the heading itself
        if not (APPENDIX_RE.match(line) or APPENDIX_LETTER_RE.match(line)): continue
        if sum(1 for l in lines[i + 1:i + 9] if REFLINE_RE.search(l)) >= 2: continue   # a reference entry that happens to look like a heading
        return text[:cut] + "\n" + "\n".join(lines[i:])
    return text[:cut]


def snip(text, m, n=70):
    a, b = max(0, m.start() - n), min(len(text), m.end() + n)
    return re.sub(r"\s+", " ", text[a:b]).strip()


def score_tag(tag, title, abstract, body):
    """dict(head=title/abstract hits, body=weighted body hits, ev=[(where, snippet)])."""
    r = tx.RULES[tag]; head = title + "\n" + abstract
    head_hits = 0; body_hits = 0.0; ev = []
    for pat, w in [(p, 1.0) for p in r.get("patterns", [])] + [(p, 0.5) for p in r.get("weak", [])]:
        rx = _rx(pat)
        for m in rx.finditer(head):
            if w < 1: continue                                                  # weak words in the abstract are not the paper speaking
            if tx.NEGATIVE_CONTEXT and tx.NEGATIVE_CONTEXT.search(head[max(0, m.start() - 60):m.start()]): continue   # "without depth or point-cloud inputs"
            head_hits += 1
            if len(ev) < 2: ev.append(("abstract" if m.start() > len(title) else "title", snip(head, m)))
        ms = list(rx.finditer(body))
        if tx.NEGATIVE_CONTEXT:                                                 # named in related work ("prior work uses parallel-jaw grippers")
            ms = [m for m in ms if not tx.NEGATIVE_CONTEXT.search(body[max(0, m.start() - 60):m.start()])]
        body_hits += len(ms) * w
        if ms and len(ev) < 2: ev.append((f"body x{len(ms)}", snip(body, ms[0])))
    return dict(head=head_hits, body=body_hits, ev=ev)


def _level(tag, s):
    r = tx.RULES[tag]
    if (s["head"] and r.get("head", True)) or s["body"] >= r.get("sure", 999): return "sure"
    if s["head"] or s["body"] >= r.get("maybe", 999): return "maybe"
    return None


def _collection_score(c, head_txt, body):
    h = sum(len(_rx(p).findall(head_txt)) for p in c.get("patterns", []))
    b = sum(len(_rx(p).findall(body)) for p in c.get("patterns", []))
    return h, b


def suggest(title, abstract, text, has_pdf=True):
    """Rules only: analyze() -> apply_relations() -> finish(). The LLM path (llm.py) starts from the same analyze() context."""
    return finish_rules(analyze(title, abstract, text, has_pdf))


def finish_rules(c):
    """The rules' verdict from an analyze() context, which is left untouched (llm.merge needs the pre-relation state)."""
    c = copy.deepcopy(c)
    apply_relations(c["fam_tags"], c["maybe"], c["S"], c["title"], c["head_txt"], c["body"])
    return finish(c)


def analyze(title, abstract, text, has_pdf=True):
    """Score every tag and apply per-tag thresholds; returns the working context (before cross-tag relations)."""
    title, abstract = title or "", abstract or ""
    body = cut_refs(text or ""); head_txt = title + "\n" + abstract
    S = {t: score_tag(t, title, abstract, body) for t in tx.RULES if not t.startswith("type:")}
    maybe, flags = {}, []
    fam_tags = {f: [] for f in tx.FAMILIES}

    # ---- type (title, or "we introduce ... X" in the abstract) ----
    types = []
    for tag, r in ((t, r) for t, r in tx.RULES.items() if t.startswith("type:")):
        if (r.get("title") and re.search(r["title"], title, re.I)) or \
           (r.get("introduce") and re.search(r"\bwe (introduce|present|release)\b[^.]{0,30}\b(" + r["introduce"] + ")", abstract, re.I)):
            types.append(tag)

    # ---- score every family ----
    for fam in tx.FAMILIES:
        spec = tx.FAMILY_RULES[fam]
        for tag in (t for t in S if t.startswith(fam + ":")):
            r = tx.RULES[tag]; s = S[tag]
            if spec.get("context"):                                           # base: name must co-occur with a fine-tuning verb
                name = r["patterns"][0]
                if not s["head"] and not s["body"]: continue
                if re.search(name, title, re.I): maybe[tag] = "the model in the title is the paper's own model, not a base"; continue
                ctx = _rx(r"(" + spec["context"] + r")[^.]{0,60}(" + name + r")|(" + name + r")[^.]{0,60}(" + spec["context"] + r")")
                hm, bm = list(ctx.finditer(head_txt)), list(ctx.finditer(body)); s["ctx"] = len(hm) * 3 + len(bm)
                if hm: fam_tags[fam].append(tag); s["ev"] = [("abstract, fine-tuning context", snip(head_txt, m)) for m in hm[:2]]
                elif len(bm) >= 2: maybe[tag] = f"{len(bm)} fine-tuning mentions in the body but none in the abstract — real fine-tune or a baseline?"; s["ev"] = [("body, fine-tuning context", snip(body, bm[0]))]
                else: maybe[tag] = "model named, but no fine-tuning / frozen context (architecturally similar or a baseline: no base tag)"
                continue
            lv = _level(tag, s)
            if s["head"] and r.get("head", True) is False:                    # a head hit alone is not enough for this tag (teleop): needs contribution context
                if (r.get("title_requires") and re.search(r["title_requires"], title, re.I)) or (r.get("head_requires") and re.search(r["head_requires"], head_txt, re.I)):
                    lv = "sure"
                elif r.get("title_maybe") and re.search(r["title_maybe"], title, re.I):
                    lv = "maybe"; maybe[tag] = f"'{r['title_maybe']}' in the title — may or may not be this paper's contribution, please decide"
                else:
                    lv = "maybe"; maybe[tag] = "mentioned in the abstract, but reads like context (e.g. data collection), not a contribution"
            if lv == "sure": fam_tags[fam].append(tag)
            elif lv == "maybe" and tag not in maybe: maybe[tag] = f"{s['body']:g} weighted body hits, not in the abstract — could be related work or a baseline"

    return dict(title=title, abstract=abstract, body=body, head_txt=head_txt, has_pdf=has_pdf, S=S, fam_tags=fam_tags, maybe=maybe, flags=flags, types=types)


def apply_relations(fam_tags, maybe, S, title, head_txt, body):
    """excludes / implies / excluded_by / weak_with / per-family max — shared by the rule and LLM paths."""
    all_sure = {t for ts in fam_tags.values() for t in ts}
    for tag in sorted(all_sure):
        r = tx.RULES[tag]
        for ex in r.get("excludes", []):
            ex = {"tag": ex} if isinstance(ex, str) else ex
            other = ex["tag"]; fam = other.split(":")[0]
            if other not in fam_tags.get(fam, []): continue
            if ex.get("unless") and (re.search(ex["unless"], head_txt, re.I) or len(re.findall(ex["unless"], body, re.I)) >= ex.get("min", 1)): continue
            if ex.get("unless_title") and re.search(ex["unless_title"], title, re.I): continue
            fam_tags[fam].remove(other); maybe[other] = f"suppressed by {tag} ({tx.RULES[other].get('description', '')[:60]})"
        for other in r.get("implies", []):
            fam = other.split(":")[0]
            if other not in fam_tags[fam]: fam_tags[fam].append(other); maybe.pop(other, None)
    all_sure = {t for ts in fam_tags.values() for t in ts}
    for fam in tx.FAMILIES:
        for tag in list(fam_tags[fam]):
            r = tx.RULES[tag]
            if any(x in all_sure for x in r.get("excluded_by", [])):
                fam_tags[fam].remove(tag); maybe[tag] = "the paper itself is an action model / controller (" + r.get("description", "")[:70] + ")"
            elif r.get("weak_with") and not S[tag]["head"] and any(x in all_sure for x in r["weak_with"]):
                fam_tags[fam].remove(tag); maybe[tag] = "no abstract mention and the paper uses " + "/".join(x.split(":")[1] for x in r["weak_with"] if x in all_sure) + " — cameras may only feed that"
        mx = tx.FAMILY_RULES[fam].get("max")
        if mx and len(fam_tags[fam]) > mx:
            ranked = sorted(fam_tags[fam], key=lambda t: -(S[t]["head"] * 100 + S[t]["body"]))
            for t in ranked[mx:]: maybe[t] = f"at most {mx} {fam} tags; this ranked #{ranked.index(t) + 1}"
            fam_tags[fam] = ranked[:mx]



def finish(c):
    """Collection decision, survey/benchmark/strip rules, flags -> the suggestion dict."""
    title, abstract, body, head_txt, has_pdf = c["title"], c["abstract"], c["body"], c["head_txt"], c["has_pdf"]
    S, fam_tags, maybe, flags, types = c["S"], c["fam_tags"], dict(c["maybe"]), list(c["flags"]), list(c["types"])
    evidence = {}
    all_sure = {t for ts in fam_tags.values() for t in ts}
    cscore = {c["name"]: _collection_score(c, head_txt, body) for c in tx.COLLECTION_RULES}
    def total(c):
        h, b = cscore[c["name"]]; s = 3 * h
        for pat, bonus in c.get("tag_bonus", {}).items():
            if any(re.fullmatch(pat.replace("*", ".*"), t) for t in all_sure): s += bonus
        if c.get("title_patterns") and any(_rx(p).search(title) for p in c["title_patterns"]): s += 6
        return s
    coll = None; winner = None
    if c.get("lock_collection"):                                                # adjudicated tags must not move the paper (llm.merge)
        coll = c["lock_collection"]; winner = next(x for x in tx.COLLECTION_RULES if x["name"] == coll)
    for c in () if coll else tx.COLLECTION_RULES:
        if c.get("default"): continue
        if any(t not in all_sure for t in c.get("requires", [])): continue
        if c.get("not_in_title") and any(_rx(p).search(title) for p in c["not_in_title"]): continue
        s = total(c); others = max((total(o) for o in tx.COLLECTION_RULES if o is not c and not o.get("default")), default=0)
        ok = s >= c.get("min_score", 3) and (c.get("max_other") is None or others <= c["max_other"])
        if not ok and c.get("body_fallback") and all(cscore[o["name"]][0] == 0 for o in tx.COLLECTION_RULES) and cscore[c["name"]][1] >= c["body_fallback"]:
            ok = all(cscore[o["name"]][1] <= 3 for o in tx.COLLECTION_RULES if o is not c)      # thin abstract: let the body decide
        if ok: coll, winner = c["name"], c; break
    if not coll:
        coll = tx.DEFAULT_COLLECTION; winner = next(c for c in tx.COLLECTION_RULES if c["name"] == coll)
        hits = [c["name"] for c in tx.COLLECTION_RULES if not c.get("default") and cscore[c["name"]][0]]
        if hits: flags.append(f"BOUNDARY: default collection, but the abstract also matches {'/'.join(hits)} vocabulary — confirm the collection")
    if winner.get("boundary_with"):
        other = next(c for c in tx.COLLECTION_RULES if c["name"] == winner["boundary_with"])
        bp = other.get("boundary_patterns") or other.get("title_patterns") or other.get("patterns", [])
        if any(_rx(p).search(abstract) for p in bp) and all(t in all_sure for t in other.get("requires", [])):
            if winner.get("boundary_pause", True): flags.append(f"BOUNDARY: {coll} vs {other['name']} — the abstract also matches {other['name']} vocabulary; confirm the collection")
            else: flags.append(f"also touches {other['name']} — consider --also \"{other['name']}\" if it does both")
    also = None
    if winner.get("status_only"):
        fam_tags = {f: [] for f in tx.FAMILIES}; maybe = {}; types = [t for t in types if t == "type:survey"]
        flags.append(f"{coll}: status tag only, by rule")
    for fam in winner.get("strip", []):
        for t in fam_tags[fam]: maybe[t] = f"{coll} items don't get {fam} tags (hardware words there are usually simulation environments)"
        fam_tags[fam] = []; maybe = {t: w for t, w in maybe.items() if not (fam == "base" and t.startswith("base:"))}
    for ttag in types:                                                          # survey / benchmark: strip families, keep head-only methods
        r = tx.RULES[ttag]
        for fam in r.get("strip", []): fam_tags[fam] = []
        for fam in r.get("head_only", []): fam_tags[fam] = [t for t in fam_tags[fam] if S[t]["head"]]
        if r.get("strip"): maybe = {t: w for t, w in maybe.items() if t.split(":")[0] not in r["strip"]}; flags.append(f"{ttag.split(':')[1]}: only type + {'/'.join(r.get('head_only', []))} named in the title/abstract are tagged")
    if "type:survey" in types and coll != tx.SURVEY_HOME and tx.SURVEY_HOME: also = tx.SURVEY_HOME
    if not winner.get("status_only") and not winner.get("default") and "embod" in fam_tags and not fam_tags["embod"]: flags.append("no embodiment found — embod left empty (uncertain)")
    if not winner.get("status_only") and "method" in fam_tags and not fam_tags["method"]: flags.append("no method found — left empty" + (" (classic ML papers often carry none)" if winner.get("default") else ""))
    if not has_pdf: flags.append("no full text — judged from the abstract only; tags may be missing, add them with `zl.py tag` once the PDF is in")

    sure = types + [t for f in tx.FAMILIES for t in fam_tags[f]]
    for t in sure: evidence[t] = S[t]["ev"][:2] if t in S else []
    for t in maybe: evidence[t] = S[t]["ev"][:1] if t in S else []
    return dict(collection=coll, also=also, sure=sure, maybe=maybe, flags=flags, evidence=evidence)


def evidence_pack(sg, limit=2, width=160):
    """Evidence snippets for every tag with any hit (sure or not) — the grounded context handed to the LLM."""
    out = []
    for t, evs in sg["evidence"].items():
        for where, s in evs[:limit]: out.append(f"[{t}] ({where}) ...{s[:width]}...")
    return out


def _cut(s, n):
    """Trim a snippet to n characters keeping its middle (snip() centres the match), at word boundaries."""
    if len(s) <= n: return s
    a = (len(s) - n) // 2; s = s[a:a + n]
    return s.split(" ", 1)[-1].rsplit(" ", 1)[0] if s.count(" ") >= 2 else s


def fmt(sg, width=None):
    """Evidence snippets are cut to the terminal width (a human reading the terminal); 150 characters when piped (an agent)."""
    if width is None: width = max(60, shutil.get_terminal_size((196, 40)).columns - 46)
    out = [f"  collection: {sg['collection']}" + (f" + {sg['also']}" if sg["also"] else "")]
    out.append("  assign    : " + (", ".join(sg["sure"]) or "(status only)"))
    for t in sg["sure"]:
        for where, s in sg["evidence"].get(t, []): out.append(f"      {t:<24} <- {where}: ...{_cut(s, width)}...")
    if sg["maybe"]:
        out.append("  candidates: (not assigned — discuss with the user)")
        for t, why in sg["maybe"].items():
            ev = sg["evidence"].get(t) or []
            out.append(f"      {t:<24} {why}" + (f"  <- {ev[0][0]}: ...{_cut(ev[0][1], max(40, width - len(why) - 12))}..." if ev else ""))
    for f in sg["flags"]: out.append(f"  ! {f}")
    return "\n".join(out)
