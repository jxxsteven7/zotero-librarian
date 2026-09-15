"""Save through the Zotero desktop connector endpoint (127.0.0.1:23119) — the same API the browser connector uses:
saveItems (create the item) -> updateSession (collection + manual tags) -> saveAttachment (PDF bytes).
The PDF must be stored by Zotero itself: with WebDAV attachment sync, files uploaded through the Web API never reach
the clients. The request User-Agent must not start with "Mozilla/"."""
import hashlib, json, os, time, urllib.error, urllib.request
from datetime import date

from . import fetch, localdb, zapi
from .config import INBOX
from .http import http, UA_LOCAL
from .titles import make_title, short_title
from .taxonomy import COLLECTIONS, check_tags, sort_tags, with_status

CONNECTOR = "http://127.0.0.1:23119"


def ping(timeout=5):
    try:
        return urllib.request.urlopen(urllib.request.Request(CONNECTOR + "/connector/ping", headers={"User-Agent": UA_LOCAL}), timeout=timeout).status == 200
    except Exception: return False


def connector(path, body=None, headers=None):
    hdr = {"X-Zotero-Connector-API-Version": "3"}; hdr.update(headers or {})
    data = body if isinstance(body, (bytes, bytearray)) else json.dumps(body).encode()
    if not isinstance(body, (bytes, bytearray)): hdr["Content-Type"] = "application/json"
    try:
        st, h, b = http(CONNECTOR + path, headers=hdr, data=data, method="POST", ua=UA_LOCAL, timeout=300)
        return st, b.decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")

def save(slug, collection, tags, also=None, venue=None, date_=None, name=None, force=False, url=None, short=None):
    m = fetch.load(slug)
    if m.get("duplicate") and not force: raise RuntimeError(f"already in the library: {m['duplicate']['key']} | {m['duplicate']['title']} (use --force to add anyway)")
    if collection not in COLLECTIONS or (also and also not in COLLECTIONS): raise RuntimeError(f"collection must be one of {COLLECTIONS}")
    tags = with_status([t.strip() for t in tags if t.strip()])
    check_tags(tags)
    title = make_title(m, name=name, venue=venue, date_=date_)
    item = dict(m["item"], id=slug, title=title, shortTitle=short or short_title(title))
    item["url"] = url or m.get("project_url") or m["item"].get("url") or ""      # URL field = project page when we have one
    pdf = os.path.join(INBOX, slug + ".pdf")
    if not ping(): raise RuntimeError("Zotero desktop is not running (connector port 23119 unreachable)")
    target = f"C{localdb.collection_id(collection)}"                              # resolved before anything is created: a missing collection must not leave a half-saved item
    sid = hashlib.sha1(f"{slug}{time.time()}".encode()).hexdigest()[:8]
    st, body = connector("/connector/saveItems", {"sessionID": sid, "uri": m["url"], "items": [item]})
    if st != 201: raise RuntimeError(f"saveItems failed {st}: {body[:300]}")
    st, body = connector("/connector/updateSession", {"sessionID": sid, "target": target, "tags": tags})
    if st != 200: raise RuntimeError(f"updateSession failed {st}: {body[:300]} (item created, but tags / collection were not applied)")
    pdf_ok = False
    if os.path.exists(pdf):
        meta = json.dumps({"sessionID": sid, "parentItemID": slug, "title": "Full Text PDF", "url": m.get("pdf_src") or m["url"]})
        with open(pdf, "rb") as f: data = f.read()
        st, body = connector("/connector/saveAttachment?sessionID=" + sid, data, headers={"X-Metadata": meta, "Content-Type": "application/pdf"})
        pdf_ok = st == 201
        if not pdf_ok: print(f"  ! saveAttachment failed {st}: {body[:300]}")
    for _ in range(5):                                                            # the client commits the new item within a moment; read it back by title
        time.sleep(1); got = localdb.item_by_title(title)
        if got: break
    if not got: raise RuntimeError("connector returned 201 but the title is not in the local database — check Zotero")
    missing = [f for f in got["files"] if not os.path.exists(f)]
    print(f"  saved     : {got['key']} <- Zotero desktop | {' + '.join(got['collections'])} | {', '.join(sort_tags(got['tags']))}")
    print(f"  PDF       : {', '.join(os.path.basename(f) for f in got['files']) if got['files'] else 'none'}" + (f"  ! missing files {missing}" if missing else ""))
    extra = ""
    if also:
        try: extra = " | +collection(web api): " + also + " " + zapi.add_collection(got["key"], also)
        except Exception as e: extra = f" | ! second collection {also} not added ({e}); later: python3 zl.py collect {got['key']} \"{also}\""
    zapi.log(f"## {date.today()} — download",
             f"- {got['key']} | {title} | +collection: {collection}{extra} | +tags: {', '.join(tags)} | pdf: {'ok' if pdf_ok else 'missing'} | src: {m.get('link')}")
    fetch.clear(slug)
    if extra: print(extra.strip(" |"))
    got.update(title=title, pdf_ok=pdf_ok, tags_written=tags, collection=collection, also=also, url=item["url"], short=item["shortTitle"])
    return got
