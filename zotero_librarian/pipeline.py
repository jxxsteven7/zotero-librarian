"""End-to-end flows.

add    link -> fetch -> classify (rules + local LLM) -> save through the desktop connector -> verify on the server ->
       append the audit log -> print a report row.  Used by the download skill.
tidy   organize items that were dropped into Zotero by hand (no status tag yet): fill missing metadata from arXiv /
       Crossref, format the title, set URL / short title, classify, file into a collection — all through the Web API.
verify one item: server state + local sync state.
Things a human must decide are marked "PAUSE" (collection boundary) and the item is skipped, with the exact command to
finish it. With ZC_LLM=agent the same pause carries the ADJUDICATE block; the agent finishes with `--confirm`."""
import os, re
from datetime import date

from . import classify, connector, fetch, llm, localdb, taxonomy as tx, zapi
from .config import DATA_DIR, INBOX
from .pdf import pdf_text, project_urls, project_url_score
from .published import lookup_published
from .sources import ARXIV_ID, meta_arxiv, meta_crossref, meta_page
from .titles import fmt_date, short_title, split_prefix

HEADER = "| key | title | collection | tags | PDF | notes |\n|---|---|---|---|---|---|"


def _text(slug):
    p = os.path.join(INBOX, slug + ".txt")
    return open(p, encoding="utf-8").read() if os.path.exists(p) else ""


def suggest_for(m, text=None, confirm=None):
    return llm.suggest(m["title"], m.get("abstract", ""), _text(m["slug"]) if text is None else text, has_pdf=bool(m.get("pdf_src")) if text is None else bool(text), confirm=confirm)


def brief(m, sg):
    """Shorter than the fetch card: no full abstract (the script already judged it), just what a reviewer needs."""
    a = ", ".join((x["firstName"] + " " + x["lastName"]).strip() for x in m["authors"][:3]) + (" ..." if len(m["authors"]) > 3 else "")
    print(f"=== {m['slug']}  ({m['source']}: {m['id']})")
    print(f"  title     : {m['proposed_title']}   short: {m.get('short_title')}")
    print(f"  authors   : {a}")
    print(f"  date      : {m.get('date') or '?'} <- {m.get('date_src')}   venue: {m.get('venue')} <- {m.get('venue_src')}")
    print(f"  URL       : {m.get('project_url') or (m.get('url') or '-') + ' (no project page found)'}")
    print(f"  PDF       : {'ok <- ' + m['pdf_src'] if m.get('pdf_src') else 'not obtained ' + '; '.join(m.get('pdf_tried', []))[:200]}")
    if m.get("duplicate"): print(f"  ! duplicate: already in the library as {m['duplicate']['key']} | {m['duplicate']['title']}")
    print(f"  abstract  : {m.get('abstract', '')[:300]}...")
    print(classify.fmt(sg)); l = llm.fmt_llm(sg)
    if l: print(l)


def decide(sg, collection=None, tags=None, drop=None, also=None, first=False):
    """Merge the script's suggestion with command-line overrides -> (collection, also, tags)."""
    coll = collection or sg["collection"]
    if coll not in tx.COLLECTIONS: raise RuntimeError(f"collection must be one of {tx.COLLECTIONS}")
    tags = [t for t in sg["sure"] if t not in set(drop or [])] + [t for t in (tags or []) if t]
    tags = tx.sort_tags(tags + (["status:" + tx.READ_AXIS[0]] if first else []))
    return coll, (also or sg["also"]), tags


def paused(sg): return any(f.startswith("BOUNDARY") for f in sg["flags"])


def pause_cmd(head, sg, coll, also, need_coll, need_adj):
    """The PAUSE message + the exact command that finishes the item once the human / agent has decided."""
    why = []
    if need_coll: why.append("collection undecided: " + "; ".join(f for f in sg["flags"] if "BOUNDARY" in f))
    if need_adj: why.append("adjudication pending: " + ", ".join(sg["agent_request"][0]))
    cmd = head + (f' --collection "{coll}"' if need_coll else "") + (f' --also "{also}"' if need_coll and also else "") + \
          (f"  --confirm none   # or --confirm {','.join(sg['agent_request'][0])} (only the ones you confirm)" if need_adj else "")
    print(f"  PAUSE: {'; '.join(why)} — not saved. Decide, then run (add --drop a,b to remove suggested tags):\n     {cmd}\n")
    return "; ".join(why)


def verify(key, wait=150, quiet=False):
    """Server (Web API) + local (sqlite) state of one item; waits up to `wait` seconds for the client to sync a new item."""
    env = zapi.env_or_die()
    it = zapi.wait_remote(env, key, wait=wait, step=10)                      # wait=0: a single check
    if not it:
        if not quiet: print(f"  sync      : x not on the server after {wait}s (is Zotero auto-sync on? check later with `python3 zl.py verify {key}`)")
        return None
    names = {v: k for k, v in zapi.remote_collections(env)[0].items()}
    d = it["data"]; kids = [(c["data"].get("title"), c["data"].get("linkMode")) for c in zapi.children(env, key)]
    synced, ver = localdb.sync_state(key)
    info = dict(version=it["version"], title=d["title"], tags=sorted(t["tag"] for t in d["tags"]), collections=[names.get(c, c) for c in d["collections"]],
                url=d.get("url", ""), short=d.get("shortTitle", ""), children=kids, local_synced=synced, local_version=ver)
    if not quiet:
        print(f"  sync      : ok server v{info['version']} | collections {info['collections']} | tags {info['tags']}")
        print(f"              URL {info['url']} | short {info['short']} | children {[k[0] for k in kids]} | local synced={synced}")
    return info


def report_row(got, sg, info, note_extra=""):
    notes = []
    if sg["maybe"]: notes.append("candidates: " + "; ".join(f"`{t}` ({w})" for t, w in sg["maybe"].items()))
    notes += [f for f in sg["flags"] if "status tag only" not in f]
    if "!" in (got.get("date_src") or "") or "!" in (got.get("venue_src") or ""): notes.append(f"date/venue flagged: {got.get('date_src')} / {got.get('venue_src')}")
    if note_extra: notes.append(note_extra)
    sync = "ok" if info else "unconfirmed"
    return (f"| `{got['key']}` | {got['title']} | {got['collection']}" + (f" + {got['also']}" if got.get("also") else "") +
            f" | {', '.join(t for t in got['tags_written'] if t not in tx.KEEP_BARE_TAGS)} | {'yes' if got['pdf_ok'] else 'no'} | sync {sync}. " + ("; ".join(notes) or "—") + " |")


def finish(slug, m, sg, coll, also, tags, venue=None, date_=None, name=None, url=None, short=None, force=False, wait=150):
    """Save + verify + report row. Shared by add and save (the connector already appended the audit log)."""
    got = connector.save(slug, coll, tags, also=also, venue=venue, date_=date_, name=name, force=force, url=url, short=short)
    got.update(date_src=m.get("date_src"), venue_src=m.get("venue_src"))
    info = verify(got["key"], wait=wait) if wait else None
    return got, report_row(got, sg, info)                                  # printed once, in the caller's table


def add(links, collection=None, tags=None, drop=None, also=None, first=False, force=False, wait=150, dry_run=False,
        venue=None, date_=None, name=None, url=None, short=None, confirm=None):
    if confirm is not None and len(links) != 1: raise SystemExit("--confirm answers one paper's ADJUDICATE block: one link (or use `zl.py save <slug> --confirm ...`)")
    rows = []
    for link in links:
        try: m = fetch.fetch_one(link)
        except Exception as e:
            print(f"=== {link}\n  x {e}\n"); rows.append(f"| — | {link} | — | — | — | x {str(e)[:120]} |"); continue
        sg = suggest_for(m, confirm=confirm)
        brief(m, sg)
        if m.get("duplicate") and not force:
            d = m["duplicate"]; print("  -> duplicate, skipped (--force to add anyway)\n"); fetch.clear(m["slug"])
            rows.append(f"| `{d['key']}` | {d['title']} | — | — | — | duplicate, already in the library, skipped |"); continue
        coll, also_, tags_ = decide(sg, collection, tags, drop, also, first)
        if dry_run:
            print(f"  [dry-run] would save: {coll}" + (f" + {also_}" if also_ else "") + f" | {', '.join(tags_)}\n"); continue
        need_coll, need_adj = not collection and paused(sg), confirm is None and llm.pending(sg)
        if need_coll or need_adj:
            why = pause_cmd(f"python3 zl.py save {m['slug']}", sg, coll, also_, need_coll, need_adj)
            rows.append(f"| PAUSE | {m['proposed_title']} | {coll}{'?' if need_coll else ''} | {', '.join(tags_)} | {'yes' if m.get('pdf_src') else 'no'} | {why} |"); continue
        got, row = finish(m["slug"], m, sg, coll, also_, tags_, venue, date_, name, url, short, force, wait)
        rows.append(row)
    print("\n" + HEADER + "\n" + "\n".join(rows))
    return rows


def save(slug, collection=None, tags=None, drop=None, also=None, first=False, force=False, wait=150,
         venue=None, date_=None, name=None, url=None, short=None, confirm=None):
    """Save something already fetched (after a PAUSE, or after `zl.py fetch`). Without --tags the script's suggestion is used."""
    m = fetch.load(slug); sg = suggest_for(m, confirm=confirm)
    if confirm is None and llm.pending(sg): print(classify.fmt(sg)); print(llm.fmt_llm(sg)); raise SystemExit(f"  x ZC_LLM=agent: answer the ADJUDICATE block with --confirm <tags>|none")
    coll, also_, tags_ = decide(sg, collection, tags, drop, also, first)
    got, row = finish(slug, m, sg, coll, also_, tags_, venue, date_, name, url, short, force, wait)
    print("\n" + HEADER + "\n" + row)
    return got


# ---------------------------------------------------------------------------------------------------------------------
# tidy — items the user dropped into Zotero by hand
# ---------------------------------------------------------------------------------------------------------------------
def _arxiv_id_of(r, text):
    for blob in (r.get("doi") or "", r.get("url") or "", r.get("extra") or ""):
        if "arxiv" in blob.lower():
            g = re.search(ARXIV_ID, blob)
            if g: return g.group(1)
    g = re.search(r"arXiv:" + ARXIV_ID, (text or "").split("\f")[0])
    return g.group(1) if g else None


def untidy_items(rows, only=None):
    """Items with no status tag: those are the ones nobody has organized yet. With `only`, the named items regardless."""
    out = []
    for r in rows:
        if only and r["key"] not in only: continue
        if not only and any(t.startswith("status:") for t in r["tags"]): continue
        if r["type"] in ("attachment", "note", "annotation"): continue
        out.append(r)
    return out


def plan_item(r, confirm=None):
    """Everything tidy would write for one item: metadata fixes, title, url, short title, tags, collection."""
    text = pdf_text(os.path.join(DATA_DIR, r["pdfs"][0])) if r.get("pdfs") and os.path.exists(os.path.join(DATA_DIR, r["pdfs"][0])) else ""
    fields = {}; notes = []
    m = None; aid = _arxiv_id_of(r, text)
    if aid:
        try: m = meta_arxiv(aid)
        except Exception as e: notes.append(f"arXiv metadata failed ({e})")
    elif r.get("doi"):
        try: m = meta_crossref(r["doi"])
        except Exception as e: notes.append(f"Crossref metadata failed ({e})")
    elif r.get("url") and "arxiv.org" not in r["url"]:
        try: m = meta_page(r["url"])
        except Exception as e: notes.append(f"page metadata failed ({e})")
    old_date, old_venue, title = split_prefix(r["title"]); abstract = r.get("abstract", "")
    if m:
        if not title or len(title) < 8 or title.lower().endswith(".pdf"): title = m["title"]
        if not abstract: abstract = m["abstract"]; fields["abstractNote"] = abstract
        if not r.get("authors"): fields["creators"] = m["authors"]
        if m["source"] == "arxiv" and not r.get("doi"): fields["DOI"] = m["item"]["DOI"]
        if m["source"] == "arxiv": lookup_published(m, text or None)
        date_ = fmt_date(m["date"]); venue = m.get("venue") or "????"; src = f"{m['date_src']} / {m['venue_src']}"
    else:
        date_ = fmt_date((r.get("date") or "")[:10]); venue = "????"; src = "item date; no arXiv id / DOI / page -> venue unknown"
        notes.append("no arXiv id / DOI: date from the item, venue left as ????")
    if old_date and (date_ in ("????", "") or len(old_date) > len(date_)): date_ = old_date          # never make an existing prefix worse
    if old_venue and (venue in ("????", "arXiv") or old_venue == venue): venue = old_venue
    if not text and not abstract: notes.append("no PDF text and no abstract: nothing to classify from")
    sg = llm.suggest(title, abstract, text, has_pdf=bool(text), confirm=confirm)
    new_title = f"[{date_}] [{venue}] {title}" if tx.TITLE_PREFIX else r["title"]
    if new_title != r["title"]: fields["title"] = new_title
    urls = project_urls(m or {"abstract": abstract}, text or None, pdf=os.path.join(DATA_DIR, r["pdfs"][0]) if r.get("pdfs") else None)
    proj = next((u for u in urls if project_url_score(u, text or None)), None)
    cur_url = r.get("url") or ""
    same = lambda u: re.sub(r"^https?://(www\.)?", "", u).rstrip("/").lower()
    if proj and same(proj) != same(cur_url): fields["url"] = proj
    elif not cur_url and m: fields["url"] = m["url"]
    if not r.get("shortTitle"): fields["shortTitle"] = short_title(title)
    coll, also, tags = decide(sg)
    have = set(r["tags"]); add_tags = [t for t in tags if t not in have]
    colls = [c for c in ([coll] + ([also] if also else [])) if c not in r["collections"]]
    return dict(key=r["key"], old_title=r["title"], title=new_title, fields=fields, tags=add_tags, collections=colls, sg=sg, src=src,
                notes=notes, abstract=abstract, has_text=bool(text))


def tidy(only=None, write=True, wait=0, collection=None, confirm=None, limit=None, create_collections=False):
    """Items without a status tag. On a library nobody has organized yet that is every item — the first run.
    `limit`: only the first N (sample a plan with --dry-run). `create_collections`: create the taxonomy's collections
    that the library lacks (the only way the scripts ever create a collection)."""
    if confirm is not None and len(only or ()) != 1: raise SystemExit("--confirm answers one item's ADJUDICATE block: use --only <key> --confirm ...")
    rows = localdb.load(refresh=True)
    todo = untidy_items(rows, only)
    if limit: todo = todo[:limit]
    if not todo: print("nothing to tidy: every item already carries a status tag"); return []
    env = zapi.env_or_die(); ck, _ = zapi.remote_collections(env)
    missing = [c for c in tx.COLLECTIONS if c not in ck]
    if missing and create_collections and write:
        for c in missing: ck[c] = zapi.create_collection(env, c); print(f"created collection {c!r} ({ck[c]}); the Zotero client picks it up on its next sync")
    elif missing:
        print(f"! collections from taxonomy.toml missing in the library: {', '.join(missing)}" + ("" if not write else " — nothing written; rerun with --create-collections (or create them in Zotero)"))
        if write: return []
    print(f"{len(todo)} item(s) to tidy" + (" [dry-run]" if not write else "") + "\n")
    out = []
    for r in todo:
        p = plan_item(r, confirm); sg = p["sg"]
        print(f"=== {p['key']} | {p['old_title'][:80]}")
        print(f"  title     : {p['title']}   ({p['src']})")
        for k, v in p["fields"].items():
            if k != "title": print(f"  {k:<10}: {str(v)[:100]}")
        print(classify.fmt(sg)); l = llm.fmt_llm(sg)
        if l: print(l)
        for n in p["notes"]: print(f"  ! {n}")
        coll = collection or sg["collection"]
        need_coll, need_adj = not collection and paused(sg), confirm is None and llm.pending(sg)
        if need_coll or need_adj:
            why = pause_cmd(f"python3 zl.py tidy --only {p['key']}", sg, coll, sg["also"], need_coll, need_adj)
            out.append(f"| PAUSE | {p['title']} | {coll}{'?' if need_coll else ''} | {', '.join(p['tags'])} | {'yes' if r['pdfs'] else 'no'} | {why} |"); continue
        if not write:
            print(f"  [dry-run] would write: {coll} | +{', '.join(p['tags'])} | fields {list(p['fields'])}\n"); continue
        st, it = zapi.get_item(env, p["key"])
        if st != 200: print(f"  x not on the server ({st}); sync Zotero first\n"); continue
        d = it["data"]; patch = {}
        for k, v in p["fields"].items():
            if k == "creators" and d.get("creators"): continue
            if d.get(k, "") != v: patch[k] = v
        want_c = [ck[c] for c in ([coll] + ([sg["also"]] if sg["also"] else [])) if c in ck and ck[c] not in d["collections"]]
        if want_c: patch["collections"] = d["collections"] + want_c
        have = {t["tag"] for t in d["tags"]}; new_tags = [t for t in p["tags"] if t not in have]
        if new_tags: patch["tags"] = d["tags"] + [{"tag": t, "type": 0} for t in new_tags]
        if patch: zapi.patch(env, p["key"], it["version"], patch)
        zapi.log(f"## {date.today()} — tidy", f"- {p['key']} | {p['title']} | +collection: {', '.join(c for c in [coll, sg['also']] if c)} | +tags: {', '.join(new_tags)} | fields: {', '.join(k for k in patch if k not in ('tags', 'collections'))} | {p['src']}")
        info = verify(p["key"], wait=wait, quiet=True) if wait else None
        got = dict(key=p["key"], title=p["title"], collection=coll, also=sg["also"], tags_written=new_tags, pdf_ok=bool(r["pdfs"]), date_src=p["src"], venue_src="")
        row = report_row(got, sg, info if wait else True, note_extra="; ".join(p["notes"]))
        print("\n" + row + "\n"); out.append(row)
    print("\n" + HEADER + "\n" + "\n".join(out))
    return out
