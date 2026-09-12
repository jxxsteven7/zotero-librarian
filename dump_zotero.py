#!/usr/bin/env python3
"""只读导出 Zotero 库 -> library_dump.json（Zotero 运行中也可用，immutable 模式不碰锁）。
用法: python3 dump_zotero.py [--table]
"""
import sqlite3, os, json, sys, re

from config import connect_ro   # 数据目录来自 .env 的 ZOTERO_DATA_DIR（或 prefs.js 自动探测）；Zotero 10 的 WAL 也处理了
con = connect_ro()
q = lambda sql, *a: con.execute(sql, a).fetchall()
strip = lambda h: re.sub(r"<[^>]+>", " ", h or "").strip()

items = q("""select i.itemID, i.key, it.typeName, i.dateAdded from items i
  join itemTypes it on it.itemTypeID=i.itemTypeID
  where it.typeName not in ('attachment','annotation','note')
    and i.itemID not in (select itemID from deletedItems) order by i.dateAdded""")

rows = []
for itemID, key, typeName, dateAdded in items:
    f = dict(q("""select f.fieldName, v.value from itemData id
      join fields f on f.fieldID=id.fieldID join itemDataValues v on v.valueID=id.valueID
      where id.itemID=?""", itemID))
    authors = [f"{fn} {ln}".strip() for ln, fn in q("""select c.lastName, c.firstName from itemCreators ic
      join creators c on c.creatorID=ic.creatorID where ic.itemID=? order by ic.orderIndex""", itemID)]
    colls = [r[0] for r in q("""select c.collectionName from collectionItems ci
      join collections c on c.collectionID=ci.collectionID where ci.itemID=?""", itemID)]
    tags = [r[0] for r in q("select t.name from itemTags it join tags t on t.tagID=it.tagID where it.itemID=?", itemID)]
    pdfs = [f"storage/{k}/{p[8:]}" if p.startswith("storage:") else p
            for p, k in q("""select ia.path, i2.key from itemAttachments ia join items i2 on i2.itemID=ia.itemID
              where ia.parentItemID=? and ia.contentType='application/pdf'""", itemID) if p]
    notes = [strip(n) for (n,) in q("select note from itemNotes where parentItemID=?", itemID)]
    annots = [dict(page=pg, text=t, comment=c) for t, c, pg in q("""
      select a.text, a.comment, a.pageLabel from itemAnnotations a
      join itemAttachments att on att.itemID=a.parentItemID
      where att.parentItemID=? order by a.sortIndex""", itemID)]
    rows.append(dict(key=key, type=typeName, title=f.get("title", ""), year=(f.get("date") or "")[:4],
        authors=authors, venue=f.get("publicationTitle") or f.get("proceedingsTitle") or f.get("repository") or "",
        collections=colls, tags=tags, pdfs=pdfs, notes=notes, annotations=annots,
        dateAdded=dateAdded[:10], url=f.get("url", ""), doi=f.get("DOI", ""), abstract=f.get("abstractNote", "")))

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "library_dump.json")
with open(out, "w", encoding="utf-8") as f: json.dump(rows, f, ensure_ascii=False, indent=1)
print(f"{len(rows)} 篇 -> {out}", file=sys.stderr)

if "--table" in sys.argv:
    for r in rows:
        print(f"{r['year']:<5}{(','.join(r['collections']) or '-')[:21]:<22}{(r['authors'][0] if r['authors'] else '?')[:14]:<15}{r['title'][:80]}")
