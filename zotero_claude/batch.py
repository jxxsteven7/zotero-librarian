"""批量整理（approval mode）：按 proposals/proposal.py 里批准的提案写 Zotero（Web API v3，PATCH 语义批量 POST）。

  python3 zc.py apply --dry-run                 # 离线：用本地 sqlite 的 version / collection key 构造载荷，不联网、不写
  python3 zc.py apply --plan                    # 联网只读：核对远端版本与本地是否一致，列出将写的内容
  python3 zc.py apply --apply [--only K1,K2] [--no-rename] [--no-status]   # 真写，逐批追加 logs/zotero-organize.log.md

规则：只增标签/分类、不删任何东西；自动标签(type=1)原样保留；只改 RENAMES 里的标题。
例外只有三个：RETAG（词表改名）会从条目上摘掉旧标签；UNTAG 摘掉某条目贴错的标签；UNCOLLECT 会把条目移出指定分类。
"""
import argparse, datetime, importlib.util, json, sys

from .config import LOG, PROPOSAL_PY, connect_ro
from .vocab import COLLECTIONS as ROOTS, FAMILIES
from .zapi import req, env_or_die

spec = importlib.util.spec_from_file_location("proposal", PROPOSAL_PY)
proposal = importlib.util.module_from_spec(spec); spec.loader.exec_module(proposal)
P, RENAMES = proposal.P, proposal.RENAMES
RETAG = getattr(proposal, "RETAG", {})   # 旧标签→新标签，作用于库里所有带旧标签的条目（不限于 P）
UNCOLLECT = getattr(proposal, "UNCOLLECT", {})   # key → 要移出的分类名列表
UNTAG = getattr(proposal, "UNTAG", {})           # key → 要摘掉的标签列表（贴错的）


def target_keys(con):
    """要处理的条目：P 里的 + 库里带 RETAG 旧标签的（后者可能不在 P 里，比如 /download 收的）。"""
    trashed = {k for (k,) in con.execute("select key from items where itemID in (select itemID from deletedItems)")}
    keys = set(P) - trashed   # 回收站里的（如用户扔掉的 Z6QB6YQG）远端 GET /items 看不到，跳过
    for old in RETAG:
        keys |= {k for (k,) in con.execute("""select i.key from itemTags it join tags t on t.tagID=it.tagID
            join items i on i.itemID=it.itemID where t.name=? and i.itemID not in (select itemID from deletedItems)""", (old,))}
    return keys


def local_state():
    """从本地库读：每个条目的 version / title / 现有 tags(含 type) / 现有 collection keys；分类名→key。"""
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
    """返回 [(key, patch_obj, human_diff)]；无变化的条目不含在内。"""
    missing_roots = [r for r in ROOTS if r not in colls]
    updates = []
    for key in sorted(items, key=lambda k: (k not in P, k)):
        if only and key not in only: continue
        cur = items[key]; patch = {"key": key, "version": cur["version"]}; diff = []
        have = {t["tag"] for t in cur["tags"]}
        # RETAG：摘掉旧标签，补上新标签（新标签已有就只摘）
        old = [t for t in have if t in RETAG] + [t for t in UNTAG.get(key, []) if t in have]
        keep = [t for t in cur["tags"] if t["tag"] not in RETAG and t["tag"] not in UNTAG.get(key, [])]
        want = [RETAG[t] for t in sorted(old) if t in RETAG and RETAG[t] not in have]
        if key in P:
            # status 不降级：已有 status:* 则不再加
            want += [t for t in desired_tags(key, status and not any(t.startswith("status:") for t in have)) if t not in have and t not in want]
        if want or old:
            patch["tags"] = keep + [{"tag": t} for t in want]
            if want: diff.append("+tags: " + ", ".join(want))
            if old: diff.append("−tags: " + ", ".join(sorted(old)))
        if key not in P:
            if len(patch) > 2: updates.append((key, patch, diff))
            continue
        want_c = [colls[n] for n in P[key][0] if n in colls and colls[n] not in cur["collections"]]
        need_c = [n for n in P[key][0] if n not in colls]
        drop_c = [colls[n] for n in UNCOLLECT.get(key, []) if n in colls and colls[n] in cur["collections"]]
        if want_c or drop_c:
            patch["collections"] = [c for c in cur["collections"] if c not in drop_c] + want_c
            if want_c: diff.append("+collection: " + ", ".join(n for n in P[key][0] if n in colls and colls[n] in want_c))
            if drop_c: diff.append("−collection: " + ", ".join(n for n in UNCOLLECT[key] if n in colls and colls[n] in drop_c))
        if need_c: diff.append("(待建分类: " + ", ".join(need_c) + ")")
        if rename and key in RENAMES and cur["title"] != RENAMES[key]:
            patch["title"] = RENAMES[key]; diff.append(f"title: {cur['title'][:40]!r} -> {RENAMES[key][:60]!r}")
        if len(patch) > 2 or need_c:
            updates.append((key, patch, diff))
    return updates, missing_roots


# ---------------- Web API ----------------
from .zapi import remote_collections


def remote_state(env):
    """从 Web API 拉提案涉及条目的当前 version / title / tags / collections（以远端为准构造载荷）。"""
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
        print(f"[dry-run] 待建根分类: {missing_roots or '无'}；将更新 {len(updates)} 条（共 {len(P)} 条提案）")
        n_tags = sum(len(d[7:].split(", ")) for _, _, ds in updates for d in ds if d.startswith("+tags: "))
        n_rm = sum(1 for _, _, ds in updates if any(d.startswith("−tags") for d in ds))
        n_coll = sum(1 for _, p, _ in updates if 'collections' in p); n_title = sum(1 for _, p, _ in updates if 'title' in p)
        print(f"  +tags {n_tags} 个, 摘旧标签(RETAG) {n_rm} 条, +collection {n_coll} 条, 改标题 {n_title} 条")
        for k, p, d in updates[:8]: print("  ", k, "|", " | ".join(d))
        print("  …"); return

    env = env_or_die()
    rnames, rdata = remote_collections(env)
    remote = remote_state(env)
    absent = [k for k in items if k not in remote]
    # 本地有未上传改动的条目 → 停，避免客户端下次同步时冲突
    con = connect_ro()
    unsynced = [k for (k,) in con.execute("select key from items where synced=0") if k in items]
    # 远端与本地内容差异（只报告，不阻塞；载荷以远端为准）
    content_drift = [k for k in items if k in remote and (
        remote[k]["title"] != items[k]["title"] or {t["tag"] for t in remote[k]["tags"]} != {t["tag"] for t in items[k]["tags"]}
        or set(remote[k]["collections"]) != set(items[k]["collections"]))]
    print(f"远端分类: {sorted(rnames)}\n远端不存在: {absent}  本地未同步(synced=0): {unsynced}  远端/本地内容有差异: {content_drift}")
    if absent or unsynced:
        sys.exit("!! 先在 Zotero 里同步一次再跑（远端缺条目或本地有未上传改动）。")
    items = remote  # 以远端状态构造载荷
    colls = {**colls, **rnames}
    updates, missing_roots = build_updates(items, colls, only, not a.no_rename, not a.no_status)
    if a.plan:
        print(f"[plan] 待建根分类: {missing_roots or '无'}；将更新 {len(updates)} 条")
        for k, p, d in updates: print(k, "|", " | ".join(d))
        return

    # ---- 真写 ----
    today = datetime.date.today().isoformat()
    log([f"\n## {today} — batch 0（分类）", "### Applied"])
    for name in missing_roots:
        st, _, js = req(env, "POST", "/collections", [{"name": name}])
        ok = st == 200 and js and js.get("successful")
        if not ok: sys.exit(f"新建分类 {name} 失败: {st} {js}")
        newkey = list(js["successful"].values())[0]["key"]; rnames[name] = newkey
        log([f"- {newkey} | 新建根分类 `{name}`"]); print("新建分类", name, newkey)
    colls = {**colls, **rnames}  # 含新建的 Misc
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
    # Uncertain 段
    unc = [(k, P[k][7]) for k in P if "Uncertain" in P[k][7] or "请定" in P[k][7] or "存疑" in P[k][7] or "不确定" in P[k][7]]
    log(["### Uncertain"] + [f"- {k} | {items[k]['title'][:50]} | {n}" for k, n in unc if k in items and k in {u[0] for u in updates}])
    log(["### Proposed new tags"] + [f"- {t} | {w} | {it}" for t, w, it in proposal.NEW_TAGS])
    print("完成。日志:", LOG)

