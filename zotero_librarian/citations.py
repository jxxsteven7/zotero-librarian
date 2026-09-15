"""refs — the citation neighbourhood of a paper via Semantic Scholar, cross-referenced with the library.

    zl.py refs <key | arXiv id | DOI | link> [--top 15]     references + citations of one paper; which are already in the library
    zl.py refs --library                                    citation links *between* library papers (reading order, hubs)

Semantic Scholar's public API allows ~1 request/s without a key; set S2_API_KEY in .env for more. Responses are cached
in cache/s2/ so repeated runs are free."""
import json, os, re, sys, time, urllib.error, urllib.parse, urllib.request

from . import localdb, table
from .config import CACHE, load_env
from .http import UA_LOCAL
from .sources import ARXIV_ID, classify_link
from .titles import norm_title

API = "https://api.semanticscholar.org/graph/v1"
FIELDS = "title,year,venue,citationCount,externalIds"
S2DIR = os.path.join(CACHE, "s2")


def _get(path, params=""):
    os.makedirs(S2DIR, exist_ok=True)
    cache = os.path.join(S2DIR, re.sub(r"[^\w.-]+", "_", path + params)[:150] + ".json")
    if os.path.exists(cache):
        with open(cache, encoding="utf-8") as f: return json.load(f)
    hdr = {"User-Agent": UA_LOCAL}
    key = load_env().get("S2_API_KEY")
    if key: hdr["x-api-key"] = key
    for attempt in range(6):
        try:
            r = urllib.request.urlopen(urllib.request.Request(API + path + params, headers=hdr), timeout=60)
            js = json.loads(r.read().decode())
            with open(cache, "w", encoding="utf-8") as f: json.dump(js, f)
            return js
        except urllib.error.HTTPError as e:
            if e.code == 404: return None
            if e.code != 429 or attempt == 5: raise
            time.sleep(3 * (attempt + 1))
    return None


def s2_id_for(r):
    """Semantic Scholar paper id string for a library row: arXiv:... or DOI:..."""
    for blob in (r.get("doi") or "", r.get("url") or "", r.get("extra") or ""):
        if "arxiv" in blob.lower():
            g = re.search(ARXIV_ID, blob)
            if g: return "arXiv:" + g.group(1)
    if r.get("doi"): return "DOI:" + r["doi"]
    return None


def resolve(ident, lib):
    """Library key / arXiv id / DOI / link -> (s2 id, label)."""
    row = next((r for r in lib if r["key"] == ident), None)
    if row: return s2_id_for(row), row["title"]
    kind, x = classify_link(ident)
    if kind == "arxiv": return "arXiv:" + x, ident
    if kind == "doi": return "DOI:" + x, ident
    raise RuntimeError(f"cannot resolve {ident!r}: give a library key, an arXiv id / link or a DOI")


def _index(lib):
    by_arxiv, by_doi, by_title = {}, {}, {}
    for r in lib:
        sid = s2_id_for(r)
        if sid and sid.startswith("arXiv:"): by_arxiv[sid[6:]] = r
        if r.get("doi"): by_doi[r["doi"].lower()] = r
        by_title[norm_title(r["title"])] = r
    return by_arxiv, by_doi, by_title


def _match(p, idx):
    by_arxiv, by_doi, by_title = idx
    ext = p.get("externalIds") or {}
    if ext.get("ArXiv") and ext["ArXiv"] in by_arxiv: return by_arxiv[ext["ArXiv"]]
    if ext.get("DOI") and ext["DOI"].lower() in by_doi: return by_doi[ext["DOI"].lower()]
    return by_title.get(norm_title(p.get("title") or ""))


def one(ident, top=15):
    lib = localdb.load(refresh=True); idx = _index(lib)
    sid, label = resolve(ident, lib)
    if not sid: raise RuntimeError(f"{label!r} has no arXiv id / DOI to look up")
    me = _get(f"/paper/{urllib.parse.quote(sid)}", f"?fields={FIELDS}")
    if not me: raise RuntimeError(f"Semantic Scholar has no record for {sid}")
    refs = (_get(f"/paper/{urllib.parse.quote(sid)}/references", f"?fields={FIELDS}&limit=500") or {}).get("data", [])
    cites = (_get(f"/paper/{urllib.parse.quote(sid)}/citations", f"?fields={FIELDS}&limit=500") or {}).get("data", [])
    refs = [x["citedPaper"] for x in refs if x.get("citedPaper") and x["citedPaper"].get("title")]
    cites = [x["citingPaper"] for x in cites if x.get("citingPaper") and x["citingPaper"].get("title")]
    print(f"=== {me['title']} ({me.get('year')}, {me.get('venue') or 'no venue'}, cited {me.get('citationCount', 0)} times)  [{sid}]")
    for name, items, key in (("REFERENCES", refs, "in"), ("CITED BY", cites, "out")):
        matched = [(p, _match(p, idx)) for p in items]
        inlib = [(p, r) for p, r in matched if r]; others = sorted([p for p, r in matched if not r], key=lambda p: -(p.get("citationCount") or 0))
        print(f"\n{name}: {len(items)} total, {len(inlib)} already in the library")
        for p, r in sorted(inlib, key=lambda pr: pr[0].get("year") or 0):
            print(f"  in library  `{r['key']}` {r['title'][:80]}")
        print(f"  top {min(top, len(others))} not in the library (by citation count):")
        rows = []
        for p in others[:top]:
            ext = p.get("externalIds") or {}; link = ("arXiv:" + ext["ArXiv"]) if ext.get("ArXiv") else ("DOI:" + ext["DOI"] if ext.get("DOI") else "")
            rows.append([p.get("year") or "????", p.get("citationCount") or 0, p["title"][:80], p.get("venue") or "", link])
        print(table.render(["year", "cites", "title", "venue", "id"], rows))
    print("\nAdd one with: python3 zl.py add <arXiv id or DOI>")


def library(top=20):
    """Citation links between library papers: who cites whom, most-cited-within-library."""
    lib = [r for r in localdb.load(refresh=True) if s2_id_for(r)]; idx = _index(lib)
    edges = []; n = 0
    for r in lib:
        sid = s2_id_for(r)
        refs = (_get(f"/paper/{urllib.parse.quote(sid)}/references", f"?fields={FIELDS}&limit=500") or {}).get("data", [])
        n += 1
        if n % 10 == 0: print(f"  ... {n}/{len(lib)}", file=sys.stderr)
        for x in refs:
            p = x.get("citedPaper") or {}
            t = _match(p, idx)
            if t and t["key"] != r["key"]: edges.append((r["key"], t["key"]))
        time.sleep(1.1)
    by_key = {r["key"]: r for r in lib}
    cited = {}; citing = {}
    for a, b in edges: cited.setdefault(b, set()).add(a); citing.setdefault(a, set()).add(b)
    print(f"{len(lib)} library papers with an arXiv id / DOI, {len(edges)} citation links between them\n")
    print(f"Most cited within the library (read these first):")
    for k, s in sorted(cited.items(), key=lambda kv: -len(kv[1]))[:top]:
        print(f"  {len(s):>3}  `{k}` {by_key[k]['title'][:80]}")
    print(f"\nPapers that build on the most library papers:")
    for k, s in sorted(citing.items(), key=lambda kv: -len(kv[1]))[:top]:
        print(f"  {len(s):>3}  `{k}` {by_key[k]['title'][:80]}  <- cites " + ", ".join(sorted(s)[:8]))
    with open(os.path.join(CACHE, "library_citations.json"), "w", encoding="utf-8") as f: json.dump(edges, f)
    return edges
