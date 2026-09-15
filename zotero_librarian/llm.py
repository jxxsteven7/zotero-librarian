"""Local-LLM classifier (Ollama by default, any OpenAI-compatible server otherwise) layered on top of the rule engine.

The rules extract *evidence* (snippets from title / abstract / full text for every tag that has any hit); the model reads
the taxonomy descriptions plus that evidence and decides. The two are then merged so that:
  * a tag both the model picked and the rules found evidence for      -> assigned
  * a tag the model picked with no textual evidence at all             -> candidate ("no evidence")
  * a tag the rules were sure about but the model rejected             -> candidate ("model disagreed")
  * collection: the model's choice; if it disagrees with the rules, the paper is flagged (the pipeline pauses)
No model configured or reachable -> pure rules, with a note. Configure in .env:
  ZC_LLM=ollama|openai|agent|off   ZC_LLM_MODEL=qwen3.5:9b   ZC_LLM_URL=http://127.0.0.1:11434   ZC_LLM_KEY=... (openai only)
ZC_LLM=agent: no local model — the coding agent that runs the command is the adjudicator. The pipeline prints an
ADJUDICATE block (the promotable candidates with their definitions and evidence) and pauses; the agent answers with
`--confirm a,b` (or `--confirm none`) on the printed command, which goes through the same merge() as a model answer.
Only the candidates a model could promote are asked about, so the agent reads a few hundred tokens, not the paper.
"""
import json, os, re, urllib.request
from difflib import SequenceMatcher

from . import classify, taxonomy as tx
from .config import load_env

SCHEMA = {"type": "object", "required": ["collection", "tags", "confidence", "reason"],
          "properties": {"collection": {"type": "string"}, "also": {"type": ["string", "null"]},
                         "tags": {"type": "array", "items": {"type": "string"}},
                         "uncertain": {"type": "array", "items": {"type": "string"}},
                         "confidence": {"type": "number"}, "reason": {"type": "string"}}}
SYSTEM = ("You are a meticulous research librarian filing one paper into a fixed taxonomy. Use ONLY the collections and tag "
          "values listed. Assign a tag only when the paper's own method or experiments satisfy its definition — a mention in "
          "related work, a baseline, or future work does not count. Prefer fewer, correct tags. Reply with JSON only.")
SETUP_HEADING = re.compile(r"\n\s*(?:\d+(?:\.\d+)*\s+)?(experimental setup|hardware(?: setup| platform)?|real[- ]world (?:experiments?|setup|deployment)|robot (?:setup|platform|system)|implementation details|experiments?)\s*\n", re.I)


def settings():
    """ZC_LLM* from .env; a process environment variable of the same name overrides it (`ZC_LLM=agent python3 zc.py add ...`)."""
    env = load_env(); g = lambda k, d="": os.environ.get(k) or env.get(k) or d
    return dict(kind=g("ZC_LLM", "ollama").lower(), model=g("ZC_LLM_MODEL", "qwen3.5:9b"), url=g("ZC_LLM_URL", "http://127.0.0.1:11434").rstrip("/"),
                key=g("ZC_LLM_KEY"), timeout=int(g("ZC_LLM_TIMEOUT", 180)))


def available(cfg=None):
    """(ok, message) — is the configured model reachable? (does not load the model)"""
    cfg = cfg or settings()
    if cfg["kind"] == "off": return False, "ZC_LLM=off"
    if cfg["kind"] == "agent": return False, "ZC_LLM=agent (the coding agent adjudicates the candidates; costs tokens)"
    try:
        if cfg["kind"] == "ollama":
            tags = json.loads(urllib.request.urlopen(cfg["url"] + "/api/tags", timeout=5).read())
            names = [m["name"] for m in tags.get("models", [])]
            if cfg["model"] not in names and cfg["model"] + ":latest" not in names:
                return False, f"Ollama is up but model {cfg['model']!r} is not pulled (have: {', '.join(names) or 'none'}); run `ollama pull {cfg['model']}`"
            return True, f"ollama {cfg['model']} at {cfg['url']}"
        hdr = {"Authorization": "Bearer " + cfg["key"]} if cfg["key"] else {}
        urllib.request.urlopen(urllib.request.Request(cfg["url"] + "/v1/models", headers=hdr), timeout=5).read()
        return True, f"openai-compatible {cfg['model']} at {cfg['url']}"
    except Exception as e:
        return False, f"{cfg['kind']} at {cfg['url']} not reachable ({e})"


def _chat(cfg, system, user):
    if cfg["kind"] == "ollama":
        body = {"model": cfg["model"], "stream": False, "think": False, "format": SCHEMA,
                "options": {"temperature": 0, "num_ctx": 16384},
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        r = urllib.request.urlopen(urllib.request.Request(cfg["url"] + "/api/chat", data=json.dumps(body).encode(),
                                                          headers={"Content-Type": "application/json"}), timeout=cfg["timeout"])
        return json.loads(r.read())["message"]["content"]
    body = {"model": cfg["model"], "temperature": 0, "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user + "\nReturn a JSON object with keys collection, also, tags, uncertain, confidence, reason."}]}
    hdr = {"Content-Type": "application/json"}
    if cfg["key"]: hdr["Authorization"] = "Bearer " + cfg["key"]
    r = urllib.request.urlopen(urllib.request.Request(cfg["url"] + "/v1/chat/completions", data=json.dumps(body).encode(), headers=hdr), timeout=cfg["timeout"])
    return json.loads(r.read())["choices"][0]["message"]["content"]


def setup_excerpt(body, n=900):
    m = SETUP_HEADING.search(body)
    return re.sub(r"\s+", " ", body[m.end():m.end() + n]).strip() if m else ""


def build_prompt(title, abstract, sg, body):
    ev = classify.evidence_pack(sg)
    parts = [tx.policy_text(), "\nPAPER", f"Title: {title}", f"Abstract: {abstract or '(none)'}"]
    ex = setup_excerpt(body)
    if ex: parts.append(f"Experimental-setup excerpt: {ex}")
    if ev: parts.append("Evidence snippets found in the full text (tag in brackets is only a hint; decide from the text):\n" + "\n".join(ev))
    parts.append("\nDecide: collection (exactly one name from the list; use `also` only for a survey that belongs in two), tags (family:value strings), "
                 "uncertain (tags you considered but could not confirm, each as 'tag: reason'), confidence 0-1 for the collection, reason (one sentence).")
    return "\n".join(parts)


def ask(title, abstract, body, sg, cfg=None):
    cfg = cfg or settings()
    raw = _chat(cfg, SYSTEM, build_prompt(title, abstract, sg, body))
    try: out = json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", raw, re.S); out = json.loads(m.group(0)) if m else {}
    out.setdefault("tags", []); out.setdefault("uncertain", []); out.setdefault("confidence", 0.5); out.setdefault("also", None)
    return out


def merge(c, llm, policy="adjudicate", collection=None):
    """Combine the rules' working context `c` (classify.analyze) with the model's answer. `collection` = the rules' decision,
    kept fixed (a promoted tag would otherwise change the collection score and move the paper).

    policy "adjudicate" (default): the rules' sure tags stay; a model pick is added only where the rules found borderline
    evidence (a candidate) and the family is in taxonomy.toml [llm].adjudicate_families; base tags additionally need
    fine-tuning context. The model can't remove a sure tag — it only notes disagreement. Collection stays with the rules;
    model disagreement is flagged. (Measured on this library with qwen3.5:9b: letting the model decide method/modality
    lowered precision; embod/tech/base gained recall at little cost — hence the default family list.)
    policy "veto": like adjudicate, but a sure tag the model rejects becomes a candidate.
    """
    valid = set(tx.RULES)
    picked = {t for t in llm.get("tags", []) if t in valid and not t.startswith("type:")}
    bad = [t for t in llm.get("tags", []) if t not in valid and not t.startswith("status:")]
    S = c["S"]; fam_tags = {f: list(v) for f, v in c["fam_tags"].items()}; maybe = dict(c["maybe"]); flags = list(c["flags"])
    rule_sure = {t for ts in fam_tags.values() for t in ts}
    unsure = {}
    for u in llm.get("uncertain", []):
        m = re.match(r"\s*([a-z]+:[a-z0-9.\-]+)\s*[:\-—]?\s*(.*)", u)
        if m: unsure[m.group(1)] = m.group(2).strip()
    adjudicate = set(tx.LLM.get("adjudicate_families", ["embod", "tech", "base"]))
    for t in picked - rule_sure:
        fam = t.split(":")[0]
        if t in maybe and fam in adjudicate and (fam != "base" or S.get(t, {}).get("ctx", 0) >= 2):   # borderline evidence + model agrees -> assign
            fam_tags[fam].append(t); maybe.pop(t)
        elif t in maybe:
            maybe[t] = maybe[t] + " — the model agrees it applies"                                # family the model may not decide: stays a candidate
        elif t not in maybe:
            s = S.get(t, {"head": 0, "body": 0})
            maybe[t] = f"model suggested it, but the text barely supports it ({s['head']} abstract / {s['body']:g} body hits)"
    for t in rule_sure - picked:
        note = "model did not pick it" + (": " + unsure[t] if unsure.get(t) else "")
        if policy == "veto": fam_tags[t.split(":")[0]].remove(t); maybe[t] = "strong textual evidence, but the " + note
        else: flags.append(f"{t}: kept on textual evidence although the {note}")
    for t, why in unsure.items():
        if t in valid and t not in {x for ts in fam_tags.values() for x in ts} and t not in maybe: maybe[t] = "model unsure: " + why
    c2 = dict(c, fam_tags=fam_tags, maybe=maybe, flags=flags, rule_sure=rule_sure, lock_collection=collection)
    classify.apply_relations(c2["fam_tags"], c2["maybe"], S, c2["title"], c2["head_txt"], c2["body"])
    sg = classify.finish(c2)
    if llm.get("collection") in tx.COLLECTIONS and llm["collection"] != sg["collection"]:
        sg["flags"].append(f"model would file it under {llm['collection']} (confidence {llm.get('confidence')}): {llm.get('reason', '')}")
    if bad: sg["flags"].append("model proposed values outside the taxonomy (ignored): " + ", ".join(bad))
    sg["llm"] = dict(model=llm.get("model") or settings()["model"], confidence=llm.get("confidence"), reason=llm.get("reason", ""), collection=llm.get("collection"))
    return sg


# ---------------------------------------------------------------------------------------------------------------------
# ZC_LLM=agent — the coding agent answers instead of a local model
# ---------------------------------------------------------------------------------------------------------------------
def promotable(c, sg_rules, policy="adjudicate"):
    """Candidates that would be assigned if the adjudicator confirmed them (same merge() as a model answer, so the
    family list, the base-context requirement and the collection's strip rules all apply). Empty = nothing to ask."""
    cand = [t for t in c["maybe"] if t.split(":")[0] in set(tx.LLM.get("adjudicate_families", ["embod", "tech", "base"]))]
    if not cand: return []
    trial = merge(c, {"tags": list(sg_rules["sure"]) + cand, "collection": sg_rules["collection"]}, policy, sg_rules["collection"])
    return [t for t in trial["sure"] if t not in sg_rules["sure"]]


def agent_request(c, sg_rules, policy="adjudicate"):
    """The ADJUDICATE block for the agent: each promotable candidate with its definition, why it is only a candidate,
    the evidence snippets, and the experimental-setup excerpt. Returns (tags, text); text == "" when there is nothing to ask."""
    tags = promotable(c, sg_rules, policy)
    if not tags: return [], ""
    out = ["  ADJUDICATE (ZC_LLM=agent): assign each candidate only if the paper's OWN method or experiments meet the definition —",
           "  a baseline, related work or data-collection setup does not count. Then rerun with --confirm <tags> or --confirm none."]
    for t in tags:
        out.append(f"      {t:<24} {tx.RULES[t].get('description', '')}")
        out.append(f"      {'':<24} why candidate: {c['maybe'][t]}")
        seen = []
        for where, snippet in c["S"].get(t, {}).get("ev", [])[:2]:
            if any(SequenceMatcher(None, snippet, x).ratio() > 0.6 for x in seen): continue      # two patterns hit the same sentence
            seen.append(snippet); out.append(f"      {'':<24} <- {where}: ...{snippet[:160]}...")
    ex = setup_excerpt(c["body"], 600)
    if ex: out.append(f"      setup excerpt: {ex}")
    return tags, "\n".join(out)


def agent_merge(c, sg_rules, confirm, policy="adjudicate"):
    """Apply the agent's answer. `confirm` is the list of confirmed tags ([] = none). Anything outside the asked set is an error."""
    asked = promotable(c, sg_rules, policy)
    bad = [t for t in confirm if t not in asked]
    if bad: raise RuntimeError(f"--confirm {','.join(bad)}: not among the candidates asked about ({', '.join(asked) or 'none'}); tags the user wants regardless go in --tags")
    sg = merge(c, {"tags": list(sg_rules["sure"]) + list(confirm), "collection": sg_rules["collection"], "model": "agent",
                   "reason": f"confirmed {', '.join(confirm) or 'none'}" + (f"; rejected {', '.join(t for t in asked if t not in confirm)}" if len(confirm) < len(asked) else "")},
               policy, sg_rules["collection"])
    for t in asked:
        if t not in confirm and t in sg["maybe"]: sg["maybe"][t] += " — not confirmed by the agent"
    return sg


def suggest(title, abstract, text, has_pdf=True, cfg=None, cache=None, policy="adjudicate", confirm=None):
    """Rules first; if a model is configured and reachable, let it adjudicate the borderline tags.
    `cache`: optional path of a JSON file to store / reuse the raw model answer (evaluation runs).
    `confirm`: ZC_LLM=agent only — the agent's answer (list of confirmed tags, [] for none). None = not answered yet:
    the result then carries `agent_request` (tags, text) and the pipeline pauses when it is non-empty."""
    c = classify.analyze(title, abstract, text, has_pdf)
    sg_rules = classify.suggest(title, abstract, text, has_pdf)
    cfg = cfg or settings()
    if cfg["kind"] == "agent":
        if confirm is not None: return agent_merge(c, sg_rules, confirm, policy)
        sg_rules["agent_request"] = agent_request(c, sg_rules, policy)
        return sg_rules
    out = None
    if cache and os.path.exists(cache):
        out = json.load(open(cache, encoding="utf-8"))
    else:
        ok, msg = available(cfg)
        if not ok:
            if cfg["kind"] != "off": sg_rules["flags"].append(f"no LLM ({msg}); rules only")
            return sg_rules
        try:
            out = ask(title, abstract, c["body"], sg_rules, cfg)
        except Exception as e:
            sg_rules["flags"].append(f"LLM call failed ({e}); rules only"); return sg_rules
        if cache:
            os.makedirs(os.path.dirname(cache), exist_ok=True)
            json.dump(out, open(cache, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return merge(c, out, policy, sg_rules["collection"])


def fmt_llm(sg):
    l = sg.get("llm")
    if l and l["model"] == "agent": return f"  agent     : {l.get('reason', '')}"
    if l: return f"  model     : {l['model']} (confidence {l.get('confidence')}) — {l.get('reason', '')}"
    return sg.get("agent_request", (None, ""))[1]


def pending(sg):
    """ZC_LLM=agent: the ADJUDICATE block was printed and not answered yet — the pipeline must pause."""
    return bool(sg.get("agent_request", (None, ""))[0])
