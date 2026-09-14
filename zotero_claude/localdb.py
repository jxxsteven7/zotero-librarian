"""Read-only access to the local zotero.sqlite (works while Zotero runs, see config.connect_ro). Never writes to sqlite.
dump()   -> cache/library_dump.json (title / authors / collections / tags / PDF paths / notes / annotations)
load()   -> the dump's content (refreshed first if missing)
"""
import json, os, re, sys

from .config import CACHE, DUMP, STORAGE, connect_ro

_strip = lambda h: re.sub(r"<[^>]+>", " ", h or "").strip()


def dump(table=False):
    con = connect_ro()
    q = lambda sql, *a: con.execute(sql, a).fetchall()
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
        notes = [_strip(n) for (n,) in q("select note from itemNotes where parentItemID=?", itemID)]
        annots = [dict(page=pg, text=t, comment=c) for t, c, pg in q("""
          select a.text, a.comment, a.pageLabel from itemAnnotations a
          join itemAttachments att on att.itemID=a.parentItemID
          where att.parentItemID=? order by a.sortIndex""", itemID)]
        rows.append(dict(key=key, type=typeName, title=f.get("title", ""), year=(f.get("date") or "")[:4],
            authors=authors, venue=f.get("publicationTitle") or f.get("proceedingsTitle") or f.get("repository") or "",
            collections=colls, tags=tags, pdfs=pdfs, notes=notes, annotations=annots,
            dateAdded=dateAdded[:10], url=f.get("url", ""), doi=f.get("DOI", ""), abstract=f.get("abstractNote", ""),
            shortTitle=f.get("shortTitle", ""), date=f.get("date", ""), extra=f.get("extra", "")))
    os.makedirs(CACHE, exist_ok=True)
    with open(DUMP, "w", encoding="utf-8") as f: json.dump(rows, f, ensure_ascii=False, indent=1)
    print(f"{len(rows)} items -> {os.path.relpath(DUMP)}", file=sys.stderr)
    if table:
        for r in rows:
            print(f"{r['year']:<5}{(','.join(r['collections']) or '-')[:21]:<22}{(r['authors'][0] if r['authors'] else '?')[:14]:<15}{r['title'][:80]}")
    return rows


def load(refresh=False):
    if refresh or not os.path.exists(DUMP): return dump()
    return json.load(open(DUMP, encoding="utf-8"))


def collection_id(name):
    """Local collectionID (the connector target is C<id>)."""
    r = connect_ro().execute("select collectionID from collections where libraryID=1 and collectionName=?", (name,)).fetchone()
    if not r: raise RuntimeError(f"no local collection named {name!r}")
    return r[0]


def item_by_title(title):
    """Newest item with this exact title (connector saveItems returns no key, so this is how we read it back)."""
    c = connect_ro()
    r = c.execute("""select i.itemID, i.key, i.dateAdded from items i join itemData d on d.itemID=i.itemID join fields f on f.fieldID=d.fieldID
                     join itemDataValues v on v.valueID=d.valueID where f.fieldName='title' and v.value=? and i.itemID not in (select itemID from deletedItems)
                     order by i.dateAdded desc limit 1""", (title,)).fetchone()
    if not r: return None
    att = c.execute("select a.path, ai.key from itemAttachments a join items ai on ai.itemID=a.itemID where a.parentItemID=?", (r[0],)).fetchall()
    tags = [t[0] for t in c.execute("select t.name from itemTags it join tags t on t.tagID=it.tagID where it.itemID=?", (r[0],)).fetchall()]
    colls = [t[0] for t in c.execute("select c.collectionName from collectionItems ci join collections c on c.collectionID=ci.collectionID where ci.itemID=?", (r[0],)).fetchall()]
    files = [os.path.join(STORAGE, k, p.split("storage:", 1)[1]) for p, k in att if p and p.startswith("storage:")]
    return dict(itemID=r[0], key=r[1], dateAdded=r[2], tags=tags, collections=colls, files=files)


def sync_state(key):
    """(synced, version) — synced=0 means the local item has changes not yet uploaded."""
    r = connect_ro().execute("select synced, version from items where key=?", (key,)).fetchone()
    return tuple(r) if r else (None, None)
