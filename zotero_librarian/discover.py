"""discover — recent papers from arXiv (and Hugging Face daily papers), scored against the taxonomy, nothing saved.

    zl.py discover [--days 7] [--cat cs.RO,cs.AI] [--query REGEX] [--tags a,b] [--all] [--source arxiv,hf] [--max 400]

Each candidate's title + abstract is run through the rule classifier (title/abstract evidence only, so it is fast);
the result is a table of papers with the tags they would get, ranked by how many of the wanted tags they match.
Papers already in the library are dropped. Pick what you want and add it with `zl.py add <arXiv id>`."""
import json, re, sys, time, urllib.error, urllib.parse
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone

from . import classify, localdb, table
from .http import get_text, UA_LOCAL
from .sources import ARXIV_ID
from .titles import clean_title, norm_title, ws

NS = {"a": "http://www.w3.org/2005/Atom", "x": "http://arxiv.org/schemas/atom"}


def arxiv_recent(cats, days, max_results=400):
    """arXiv API: papers in the categories submitted in the last `days` days (newest first). Falls back to the RSS feed
    (last announcement only) when the API is rate-limited."""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y%m%d%H%M")
    until = datetime.now(timezone.utc).strftime("%Y%m%d%H%M")
    q = "(" + " OR ".join(f"cat:{c}" for c in cats) + f") AND submittedDate:[{since} TO {until}]"
    out, start = [], 0
    while start < max_results:
        url = ("https://export.arxiv.org/api/query?search_query=" + urllib.parse.quote(q) +
               f"&sortBy=submittedDate&sortOrder=descending&start={start}&max_results={min(100, max_results - start)}")
        try:
            xml = get_text(url, ua=UA_LOCAL)
        except (urllib.error.HTTPError, urllib.error.URLError, OSError) as e:
            print(f"  ! arXiv API {getattr(e, 'code', e)} — falling back to the RSS feed (latest announcement only)", file=sys.stderr)
            return out or arxiv_rss(cats)
        entries = ET.fromstring(xml).findall("a:entry", NS)
        for e in entries:
            aid = re.search(ARXIV_ID, e.findtext("a:id", "", NS))
            if not aid: continue
            out.append(dict(id=aid.group(1), title=clean_title(e.findtext("a:title", "", NS)), abstract=ws(e.findtext("a:summary", "", NS)),
                            date=e.findtext("a:published", "", NS)[:10], authors=[a.findtext("a:name", "", NS) for a in e.findall("a:author", NS)],
                            cats=[c.get("term") for c in e.findall("a:category", NS)], comment=ws(e.findtext("x:comment", "", NS)), source="arxiv"))
        if len(entries) < 100: break
        start += 100; time.sleep(3)                                         # arXiv asks for 3 s between requests
    return out


def arxiv_rss(cats):
    out = []
    for c in cats:
        try: xml = get_text(f"https://rss.arxiv.org/rss/{c}", ua=UA_LOCAL)
        except Exception: continue
        for it in ET.fromstring(xml).iter("item"):
            link = it.findtext("link", ""); aid = re.search(ARXIV_ID, link)
            if not aid: continue
            desc = re.sub(r"^.*?Abstract:\s*", "", it.findtext("description", ""), flags=re.S)
            out.append(dict(id=aid.group(1), title=clean_title(it.findtext("title", "")), abstract=ws(re.sub(r"<[^>]+>", " ", desc)),
                            date=date.today().isoformat(), authors=[], cats=[c], comment="", source="arxiv-rss"))
    return out


def hf_daily(days):
    """Hugging Face daily papers (a curated subset with upvotes), one request per day."""
    out = []
    for i in range(days):
        d = (date.today() - timedelta(days=i)).isoformat()
        try: js = json.loads(get_text(f"https://huggingface.co/api/daily_papers?date={d}", ua=UA_LOCAL))
        except Exception: continue
        for p in js:
            paper = p.get("paper", {}); aid = paper.get("id", "")
            if not re.fullmatch(ARXIV_ID, aid): continue
            out.append(dict(id=aid, title=clean_title(paper.get("title", "")), abstract=ws(paper.get("summary", "")), date=(paper.get("publishedAt") or d)[:10],
                            authors=[a.get("name", "") for a in paper.get("authors", [])], cats=[], comment="", source="hf", upvotes=paper.get("upvotes", 0)))
    return out


def run(days=7, cats=("cs.RO",), query=None, tags=(), require_all=False, sources=("arxiv", "hf"), max_results=400):
    lib = localdb.load()
    known = {norm_title(r["title"]) for r in lib}
    known_ids = set()
    for r in lib:
        for blob in (r.get("doi") or "", r.get("url") or "", r.get("extra") or ""):
            g = re.search(ARXIV_ID, blob) if "arxiv" in blob.lower() else None
            if g: known_ids.add(g.group(1))
    cands = {}
    if "arxiv" in sources:
        for p in arxiv_recent(list(cats), days, max_results): cands.setdefault(p["id"], p)
    if "hf" in sources:
        for p in hf_daily(days):
            if p["id"] in cands: cands[p["id"]]["upvotes"] = p.get("upvotes", 0); cands[p["id"]]["source"] += "+hf"
            else: cands[p["id"]] = p
    want = [t for t in tags if t]
    rx = re.compile(query, re.I) if query else None
    rows = []
    for p in cands.values():
        if p["id"] in known_ids or norm_title(p["title"]) in known: continue
        if rx and not (rx.search(p["title"]) or rx.search(p["abstract"])): continue
        sg = classify.suggest(p["title"], p["abstract"], "", has_pdf=False)
        got = [t for t in sg["sure"] if not t.startswith("status:")]
        hit = [t for t in want if t in got]
        if want and (not hit or (require_all and len(hit) < len(want))): continue
        rows.append((len(hit), len(got), p.get("upvotes", 0), p, got, sg["collection"]))
    rows.sort(key=lambda r: (-r[0], -r[1], -r[2], r[3]["date"]), reverse=False)
    print(f"{len(cands)} candidates from {', '.join(sources)} ({', '.join(cats)}, last {days} days); {len(rows)} after filters"
          + (f"; wanted tags: {', '.join(want)}" if want else "") + (f"; query /{query}/" if query else ""))
    link = (lambda i: i) if table.HUMAN else (lambda i: f"[{i}](https://arxiv.org/abs/{i})")
    out = [[i, p["date"], link(p["id"]), p["title"][:90], coll, ", ".join(got), p["source"] + (" ▲" + str(up) if up else "")]
           for i, (nh, ng, up, p, got, coll) in enumerate(rows, 1)]
    print("\n" + table.render(["#", "date", "arXiv", "title", "collection", "tags", "src"], out))
    print("\nAdd one with: python3 zl.py add <arXiv id>")
    return rows
