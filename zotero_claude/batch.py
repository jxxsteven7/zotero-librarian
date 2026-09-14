"""Batch changes in approval mode: apply what proposals/proposal.py declares (Web API v3, PATCH-semantics batch POST).

  python3 zc.py apply --dry-run     # offline: build payloads from the local sqlite (version / collection keys), write nothing
  python3 zc.py apply --plan        # online, read-only: compare server and local versions, list what would be written
  python3 zc.py apply --apply [--only K1,K2] [--no-rename] [--no-status]   # write, logging every batch

Rules: only add tags / collections, never delete; automatic tags (type=1) are kept; only titles listed in RENAMES change.
The three exceptions that remove something: RETAG (vocabulary rename) drops the old tag from every item carrying it;
UNTAG drops a wrongly assigned tag from one item; UNCOLLECT moves an item out of a collection.
"""
import argparse, datetime, importlib.util, json, sys

from .config import LOG, PROPOSAL_PY, connect_ro
from .taxonomy import COLLECTIONS as ROOTS, FAMILIES
from .zapi import req, env_or_die, remote_collections

spec = importlib.util.spec_from_file_location("proposal", PROPOSAL_PY)
proposal = importlib.util.module_from_spec(spec); spec.loader.exec_module(proposal)
P, RENAMES = proposal.P, proposal.RENAMES
RETAG = getattr(proposal, "RETAG", {})           # old tag -> new tag, applied to every item in the library that has the old tag
UNCOLLECT = getattr(proposal, "UNCOLLECT", {})   # key -> collections to leave
UNTAG = getattr(proposal, "UNTAG", {})           # key -> tags to remove (assigned in error)


def target_keys(con):
    """Items to touch: those in P plus every item carrying a RETAG old tag (which may not be in P, e.g. added by `zc.py add`)."""
    trashed = {k for (k,) in con.execute("select key from items where itemID in (select itemID from deletedItems)")}
    keys = set(P) - trashed                       # trashed items are invisible to GET /items; skip them
    for old in RETAG:
        keys |= {k for (k,) in con.execute("""select i.key from itemTags it join tags t on t.tagID=it.tagID
            join items i on i.itemID=it.itemID where t.name=? and i.itemID not in (select itemID from deletedItems)""", (old,))}
    return keys


def local_state():
    """From the local database: version / title / tags (with type) / collection keys per item; collection name -> key."""
    con = connect_ro()
    colls = {name: key for key, name in con.execute("select key, collectionName from collections")}
    items = {}; keys = target_keys(con)
    for itemID, key, version in con.execute("select itemID, key, version from items"):
        if key not in keys: continue
        title = con.execute("""select v.value from itemData id join fields f on f.fieldID=id.fieldID
            join itemDataValues v on v.valueID=id.valueID where id.itemID=? and f.fieldName='title'""", (itemID,)).fetchone()
        tags = [{"tag": n, "type": t} if t else {"tag": n} for n, t in con.execute(
            "select t.name, it.type from itemTags it join tags t on t.tagID=it.tagID where it.itemID=?", (itemID,))]
        ckeys = [r[0] for r in con.execute(
            "select c.key from collectionItems ci join collections c on c.collectionID=ci.collectionID where ci.itemID=?", (itemID,))]
        items[key] = dict(version=version, title=title[0] if title else "", tags=tags, collections=ckeys)
    return items, colls


def desired_tags(key, with_status=True):
    c, m, e, t, b, mo, s, _ = P[key]
    out = [f"{fam}:{v}" for fam, vals in zip(FAMILIES, (m, e, t, b, mo)) for v in vals]
    out += getattr(proposal, "EXTRA_TAGS", {}).get(key, [])
    if with_status: out.append(f"status:{s}")
    return out


def build_updates(items, colls, only=None, rename=True, status=True):
    """[(key, patch, human-readable diff)] — unchanged items are omitted."""
    missing_roots = [r for r in ROOTS if r not in colls]
    updates = []
    for key in sorted(items, key=lambda k: (k not in P, k)):
        if only and key not in only: continue
        cur = items[key]; patch = {"key": key, "version": cur["version"]}; diff = []
        have = {t["tag"] for t in cur["tags"]}
        old = [t for t in have if t in RETAG] + [t for t in UNTAG.get(key, []) if t in have]          # RETAG / UNTAG: drop old, add new
        keep = [t for t in cur["tags"] if t["tag"] not in RETAG and t["tag"] not in UNTAG.get(key, [])]
        want = [RETAG[t] for t in sorted(old) if t in RETAG and RETAG[t] not in have]
        if key in P:                                                                                # status never downgrades
            want += [t for t in desired_tags(key, status and not any(t.startswith("status:") for t in have)) if t not in have and t not in want]
        if want or old:
            patch["tags"] = keep + [{"tag": t} for t in want]
            if want: diff.append("+tags: " + ", ".join(want))
            if old: diff.append("-tags: " + ", ".join(sorted(old)))
        if key not in P:
            if len(patch) > 2: updates.append((key, patch, diff))
            continue
        want_c = [colls[n] for n in P[key][0] if n in colls and colls[n] not in cur["collections"]]
        need_c = [n for n in P[key][0] if n not in colls]
        drop_c = [colls[n] for n in UNCOLLECT.get(key, []) if n in colls and colls[n] in cur["collections"]]
        if want_c or drop_c:
            patch["collections"] = [c for c in cur["collections"] if c not in drop_c] + want_c
            if want_c: diff.append("+collection: " + ", ".join(n for n in P[key][0] if n in colls and colls[n] in want_c))
            if drop_c: diff.append("-collection: " + ", ".join(n for n in UNCOLLECT[key] if n in colls and colls[n] in drop_c))
        if need_c: diff.append("(collection to create: " + ", ".join(need_c) + ")")
        if rename and key in RENAMES and cur["title"] != RENAMES[key]:
            patch["title"] = RENAMES[key]; diff.append(f"title: {cur['title'][:40]!r} -> {RENAMES[key][:60]!r}")
        if len(patch) > 2 or need_c:
            updates.append((key, patch, diff))
    return updates, missing_roots


def remote_state(env):
    """Current version / title / tags / collections of the affected items from the Web API (payloads are built from this)."""
    con = connect_ro()
    keys = sorted(target_keys(con)); out = {}
    for i in range(0, len(keys), 50):
        chunk = ",".join(keys[i:i + 50])
        st, _, js = req(env, "GET", "/items", params=f"?itemKey={chunk}&limit=50")
        if st != 200: sys.exit(f"GET items -> {st} {js}")
        for it in js:
            d = it["data"]
            out[it["key"]] = dict(version=it["version"], title=d.get("title", ""), tags=d.get("tags", []),
                                  collections=d.get("collections", []), synced=1)
    return out


def log(lines):
    with open(LOG, "a", encoding="utf-8") as f: f.write("\n".join(lines) + "\n")


def run(argv):
    ap = argparse.ArgumentParser(prog="zc.py apply")
    ap.add_argument("--dry-run", action="store_true"); ap.add_argument("--plan", action="store_true"); ap.add_argument("--apply", action="store_true")
    ap.add_argument("--only"); ap.add_argument("--no-rename", action="store_true"); ap.add_argument("--no-status", action="store_true")
    a = ap.parse_args(argv)
    only = set(a.only.split(",")) if a.only else None
    items, colls = local_state()
    updates, missing_roots = build_updates(items, colls, only, not a.no_rename, not a.no_status)

    if a.dry_run or not (a.plan or a.apply):
        print(f"[dry-run] collections to create: {missing_roots or 'none'}; {len(updates)} items to update ({len(P)} proposal rows)")
        n_tags = sum(len(d[7:].split(", ")) for _, _, ds in updates for d in ds if d.startswith("+tags: "))
        n_rm = sum(1 for _, _, ds in updates if any(d.startswith("-tags") for d in ds))
        n_coll = sum(1 for _, p, _ in updates if 'collections' in p); n_title = sum(1 for _, p, _ in updates if 'title' in p)
        print(f"  +{n_tags} tags, {n_rm} items lose tags (RETAG/UNTAG), +collection on {n_coll}, {n_title} titles")
        for k, p, d in updates[:8]: print("  ", k, "|", " | ".join(d))
        print("  ..."); return

    env = env_or_die()
    rnames, rdata = remote_collections(env)
    remote = remote_state(env)
    absent = [k for k in items if k not in remote]
    con = connect_ro()                                                                  # local changes not yet uploaded -> stop (sync conflicts)
    unsynced = [k for (k,) in con.execute("select key from items where synced=0") if k in items]
    content_drift = [k for k in items if k in remote and (                               # reported only; payloads follow the server
        remote[k]["title"] != items[k]["title"] or {t["tag"] for t in remote[k]["tags"]} != {t["tag"] for t in items[k]["tags"]}
        or set(remote[k]["collections"]) != set(items[k]["collections"]))]
    print(f"server collections: {sorted(rnames)}\nmissing on server: {absent}  local unsynced (synced=0): {unsynced}  server/local drift: {content_drift}")
    if absent or unsynced:
        sys.exit("!! sync Zotero first (items missing on the server, or local changes not uploaded).")
    items = remote
    colls = {**colls, **rnames}
    updates, missing_roots = build_updates(items, colls, only, not a.no_rename, not a.no_status)
    if a.plan:
        print(f"[plan] collections to create: {missing_roots or 'none'}; {len(updates)} items to update")
        for k, p, d in updates: print(k, "|", " | ".join(d))
        return

    today = datetime.date.today().isoformat()
    log([f"\n## {today} — batch 0 (collections)", "### Applied"])
    for name in missing_roots:
        st, _, js = req(env, "POST", "/collections", [{"name": name}])
        ok = st == 200 and js and js.get("successful")
        if not ok: sys.exit(f"creating collection {name} failed: {st} {js}")
        newkey = list(js["successful"].values())[0]["key"]; rnames[name] = newkey
        log([f"- {newkey} | created collection `{name}`"]); print("created collection", name, newkey)
    colls = {**colls, **rnames}
    updates, _ = build_updates(items, colls, only, not a.no_rename, not a.no_status)
    for i in range(0, len(updates), 50):
        batch = updates[i:i + 50]
        st, hdr, js = req(env, "POST", "/items", [p for _, p, _ in batch])
        if st != 200: sys.exit(f"batch {i//50+1} -> {st} {js}")
        succ = {v["key"] for v in js.get("successful", {}).values()}; unch = set(js.get("unchanged", {}).values())
        failed = js.get("failed", {})
        log([f"\n## {today} — batch {i//50+1}", "### Applied"])
        for k, p, d in batch:
            if k in succ or k in unch:
                log([f"- {k} | {items[k]['title'][:60]} | " + " | ".join(d)])
        if failed:
            log(["### Failed"] + [f"- {batch[int(ix)][0]} | {f.get('code')} {f.get('message')}" for ix, f in failed.items()])
        print(f"batch {i//50+1}: ok={len(succ)} unchanged={len(unch)} failed={len(failed)}  lib-version={hdr.get('Last-Modified-Version')}")
        if failed: print(json.dumps(failed, ensure_ascii=False, indent=1)); sys.exit(1)
    unc = [(k, P[k][7]) for k in P if "uncertain" in P[k][7].lower()]
    log(["### Uncertain"] + [f"- {k} | {items[k]['title'][:50]} | {n}" for k, n in unc if k in items and k in {u[0] for u in updates}])
    log(["### Proposed new tags"] + [f"- {t} | {w} | {it}" for t, w, it in proposal.NEW_TAGS])
    print("done. log:", LOG)
