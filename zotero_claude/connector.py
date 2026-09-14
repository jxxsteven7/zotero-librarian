"""经 Zotero 桌面端 connector 接口（127.0.0.1:23119）入库：saveItems（建条目）→ updateSession（进分类 + 手动标签）→ saveAttachment（PDF）。
PDF 必须让 Zotero 自己存：本机附件同步是 WebDAV，Web API 上传的文件客户端拿不到。请求 UA 不能以 Mozilla/ 开头。"""
import hashlib, json, os, time, urllib.error, urllib.request
from datetime import date

from . import fetch, localdb, zapi
from .config import INBOX
from .http import http, UA_LOCAL
from .titles import make_title, short_title
from .vocab import COLLECTIONS, check_tags

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
    if m.get("duplicate") and not force: raise RuntimeError(f"库里已有 {m['duplicate']['key']} | {m['duplicate']['title']}；确认要加就 --force")
    if collection not in COLLECTIONS or (also and also not in COLLECTIONS): raise RuntimeError(f"分类只能是 {COLLECTIONS}")
    tags = [t.strip() for t in tags if t.strip()]
    if not any(t.startswith("status:") for t in tags): tags.append("status:to-read")
    check_tags(tags)
    title = make_title(m, name=name, venue=venue, date_=date_)
    item = dict(m["item"], id=slug, title=title, shortTitle=short or short_title(title))
    item["url"] = url or m.get("project_url") or m["item"].get("url") or ""      # URL 字段 = 项目页优先（Notion 那边显示的就是它）
    pdf = os.path.join(INBOX, slug + ".pdf")
    if not ping(): raise RuntimeError("Zotero 桌面端没在跑（connector 23119 不通）")
    sid = hashlib.sha1(f"{slug}{time.time()}".encode()).hexdigest()[:8]
    st, body = connector("/connector/saveItems", {"sessionID": sid, "uri": m["url"], "items": [item]})
    if st != 201: raise RuntimeError(f"saveItems 失败 {st}: {body[:300]}")
    st, body = connector("/connector/updateSession", {"sessionID": sid, "target": f"C{localdb.collection_id(collection)}", "tags": tags})
    if st != 200: raise RuntimeError(f"updateSession 失败 {st}: {body[:300]}（条目已建，标签/分类没落）")
    pdf_ok = False
    if os.path.exists(pdf):
        meta = json.dumps({"sessionID": sid, "parentItemID": slug, "title": "Full Text PDF", "url": m.get("pdf_src") or m["url"]})
        st, body = connector("/connector/saveAttachment?sessionID=" + sid, open(pdf, "rb").read(), headers={"X-Metadata": meta, "Content-Type": "application/pdf"})
        pdf_ok = st == 201
        if not pdf_ok: print(f"  ⚠ saveAttachment 失败 {st}: {body[:300]}")
    time.sleep(1)
    got = localdb.item_by_title(title)
    if not got: raise RuntimeError("connector 回了 201 但本地库里查不到这个标题，去 Zotero 里看看")
    missing = [f for f in got["files"] if not os.path.exists(f)]
    print(f"入库 {got['key']} | {title}\n  分类: {got['collections']}\n  标签: {sorted(got['tags'])}\n  PDF : {got['files'] or '无'}" + (f"  ⚠ 文件缺失 {missing}" if missing else ""))
    extra = ""
    if also:
        try: extra = " | +collection(web api): " + also + " " + zapi.add_collection(got["key"], also)
        except Exception as e: extra = f" | ⚠ 第二分类 {also} 没加上（{e}），稍后 python3 zc.py collect {got['key']} \"{also}\""
    zapi.log(f"## {date.today()} — download",
             f"- {got['key']} | {title} | +collection: {collection}{extra} | +tags: {', '.join(tags)} | pdf: {'ok' if pdf_ok else 'missing'} | src: {m.get('link')}")
    fetch.clear(slug)
    if extra: print(extra.strip(" |"))
    got.update(title=title, pdf_ok=pdf_ok, tags_written=tags, collection=collection, also=also, url=item["url"], short=item["shortTitle"])
    return got
