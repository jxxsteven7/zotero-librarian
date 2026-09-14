"""Local-LLM classifier (Ollama by default, any OpenAI-compatible server otherwise) layered on top of the rule engine.

The rules extract *evidence* (snippets from title / abstract / full text for every tag that has any hit); the model reads
the taxonomy descriptions plus that evidence and decides. The two are then merged so that:
  * a tag both the model picked and the rules found evidence for      -> assigned
  * a tag the model picked with no textual evidence at all             -> candidate ("no evidence")
  * a tag the rules were sure about but the model rejected             -> candidate ("model disagreed")
  * collection: the model's choice; if it disagrees with the rules, the paper is flagged (the pipeline pauses)
No model configured or reachable -> pure rules, with a note. Configure in .env:
  ZC_LLM=ollama|openai|off   ZC_LLM_MODEL=qwen3.5:9b   ZC_LLM_URL=http://127.0.0.1:11434   ZC_LLM_KEY=... (openai only)
"""
import json, os, re, urllib.request

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
    env = load_env()
    return dict(kind=(env.get("ZC_LLM") or "ollama").lower(), model=env.get("ZC_LLM_MODEL") or "qwen3.5:9b",
                url=(env.get("ZC_LLM_URL") or "http://127.0.0.1:11434").rstrip("/"), key=env.get("ZC_LLM_KEY", ""),
                timeout=int(env.get("ZC_LLM_TIMEOUT") or 180))


def available(cfg=None):
    """(ok, message) — is the configured model reachable? (does not load the model)"""
    cfg = cfg or settings()
    if cfg["kind"] == "off": return False, "ZC_LLM=off"
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


def merge(c, llm, policy="adjudicate"):
    """Combine the rules' working context `c` (classify.analyze) with the model's answer.

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
    S = c["S"]; fam_tags = {f: list(v) for f, v in c["fam_tags"].items()}; maybe = dict(c["maybe"])
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
        else: c["flags"].append(f"{t}: kept on textual evidence although the {note}")
    for t, why in unsure.items():
        if t in valid and t not in {x for ts in fam_tags.values() for x in ts} and t not in maybe: maybe[t] = "model unsure: " + why
    c2 = dict(c, fam_tags=fam_tags, maybe=maybe, flags=list(c["flags"]), rule_sure=rule_sure)
    classify.apply_relations(c2["fam_tags"], c2["maybe"], S, c2["title"], c2["head_txt"], c2["body"])
    sg = classify.finish(c2)
    if llm.get("collection") in tx.COLLECTIONS and llm["collection"] != sg["collection"]:
        sg["flags"].append(f"model would file it under {llm['collection']} (confidence {llm.get('confidence')}): {llm.get('reason', '')}")
    if bad: sg["flags"].append("model proposed values outside the taxonomy (ignored): " + ", ".join(bad))
    sg["llm"] = dict(model=settings()["model"], confidence=llm.get("confidence"), reason=llm.get("reason", ""), collection=llm.get("collection"))
    return sg


def suggest(title, abstract, text, has_pdf=True, cfg=None, cache=None, policy="adjudicate"):
    """Rules first; if a model is configured and reachable, let it adjudicate the borderline tags.
    `cache`: optional path of a JSON file to store / reuse the raw model answer (evaluation runs)."""
    c = classify.analyze(title, abstract, text, has_pdf)
    sg_rules = classify.suggest(title, abstract, text, has_pdf)
    cfg = cfg or settings()
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
    return merge(c, out, policy)


def fmt_llm(sg):
    l = sg.get("llm")
    return f"  model     : {l['model']} (confidence {l.get('confidence')}) — {l.get('reason', '')}" if l else ""
