"""Zotero Web API v3 封装（库 ID 来自 .env）。所有对库的修改都走这里；PDF 不走这里（见 connector.py）。
写规则：tags / collections 是整体替换，载荷以远端当前状态为基础只增不减；用远端 version 做乐观锁。
key 永远不打印。"""
import json, sys, time, urllib.error, urllib.request
from datetime import date

from .config import LOG, load_env

API = "https://api.zotero.org"


def req(env, method, path, body=None, params=""):
    url = f"{API}/users/{env['ZOTERO_LIBRARY_ID']}{path}{params}"
    data = json.dumps(body).encode() if body is not None else None
    hdr = {"Zotero-API-Key": env["ZOTERO_API_KEY"], "Zotero-API-Version": "3"}
    if data: hdr["Content-Type"] = "application/json"
    for attempt in range(6):
        try:
            r = urllib.request.urlopen(urllib.request.Request(url, data=data, headers=hdr, method=method), timeout=60)
            txt = r.read().decode()
            if r.headers.get("Backoff"): time.sleep(int(r.headers["Backoff"]))
            return r.status, dict(r.headers), (json.loads(txt) if txt else None)
        except urllib.error.HTTPError as e:
            if e.code == 429 or (e.code >= 500 and attempt < 5):
                time.sleep(int(e.headers.get("Retry-After", 5))); continue
            return e.code, dict(e.headers), e.read().decode()
    raise RuntimeError("重试耗尽: " + url)


def env_or_die():
    env = load_env()
    if not env.get("ZOTERO_API_KEY"):
        sys.exit("缺 ZOTERO_API_KEY：请在仓库目录的 .env 写入 ZOTERO_API_KEY=...（不要贴进对话）")
    return env


def remote_collections(env):
    """{name: key}, {key: data}"""
    st, _, js = req(env, "GET", "/collections", params="?limit=100")
    if st != 200: sys.exit(f"GET collections -> {st} {js}")
    return {c["data"]["name"]: c["key"] for c in js}, {c["key"]: c["data"] for c in js}


def remote_versions(env):
    st, _, js = req(env, "GET", "/items", params="?format=versions")
    if st != 200: sys.exit(f"GET items versions -> {st} {js}")
    return js


def get_item(env, key):
    """(status, item json or error text)"""
    st, _, js = req(env, "GET", f"/items/{key}")
    return st, js


def children(env, key):
    st, _, js = req(env, "GET", f"/items/{key}/children")
    return js if st == 200 else []


def wait_remote(env, key, wait=180, step=10):
    """刚经 connector 入库的条目要等客户端同步上去才能 GET 到；最多等 wait 秒。返回 item 或 None。"""
    t0 = time.time()
    while True:
        st, it = get_item(env, key)
        if st == 200: return it
        if time.time() - t0 > wait: return None
        time.sleep(step)


def patch(env, key, version, fields):
    st, _, body = req(env, "PATCH", f"/items/{key}", dict(fields, version=version))   # 乐观锁
    if st not in (200, 204): raise RuntimeError(f"PATCH {key} {st}: {body}")
    return st


def add_collection(key, name, wait=180):
    """经 Web API 给条目追加一个分类（超集写法）；条目要先被客户端同步上去，最多等 wait 秒。"""
    env = env_or_die()
    ck, _ = remote_collections(env)
    if name not in ck: raise RuntimeError(f"远端没有分类 {name!r}")
    it = wait_remote(env, key, wait)
    if not it: raise RuntimeError("等了 %ds 条目还没同步到远端" % wait)
    cur = it["data"]["collections"]
    if ck[name] in cur: return "(已在)"
    patch(env, key, it["version"], {"collections": cur + [ck[name]]})
    log(f"## {date.today()} — collect（补第二分类）", f"- {key} | {it['data']['title']} | +collection: {name}")
    return "ok"


def add_tags(key, tags):
    """给条目补标签（远端现有 + 新增，绝不摘）；和用户讨论后追加边缘标签用。日志自动记。"""
    from .vocab import check_tags
    tags = [t.strip() for t in tags if t.strip()]
    check_tags(tags)
    env = env_or_die()
    st, it = get_item(env, key)
    if st != 200: raise RuntimeError(f"远端没有条目 {key}（{st}）——刚入库的要等客户端同步上去")
    cur = [t["tag"] for t in it["data"]["tags"]]
    new = [t for t in tags if t not in cur]
    if not new: return "(已有)"
    patch(env, key, it["version"], {"tags": it["data"]["tags"] + [{"tag": t, "type": 0} for t in new]})   # type 0 = 手动标签
    log(f"## {date.today()} — tag（补标签）", f"- {key} | {it['data']['title']} | +tags: {', '.join(new)}")
    return "ok +" + ", ".join(new)


def remove_tags(key, tags, why=""):
    """摘标签。只用于两种情况：修正刚入库条目上脚本贴错的标签；用户明说要摘。日志记 −tags。"""
    tags = [t.strip() for t in tags if t.strip()]
    env = env_or_die()
    st, it = get_item(env, key)
    if st != 200: raise RuntimeError(f"远端没有条目 {key}（{st}）")
    gone = [t["tag"] for t in it["data"]["tags"] if t["tag"] in tags]
    if not gone: return "(本来就没有)"
    patch(env, key, it["version"], {"tags": [t for t in it["data"]["tags"] if t["tag"] not in tags]})
    log(f"## {date.today()} — untag（摘标签）", f"- {key} | {it['data']['title']} | −tags: {', '.join(gone)}" + (f" | {why}" if why else ""))
    return "ok −" + ", ".join(gone)


def set_fields(key, fields, why=""):
    """改条目字段（title / url / shortTitle …）。日志记改了什么。"""
    env = env_or_die()
    st, it = get_item(env, key)
    if st != 200: raise RuntimeError(f"远端没有条目 {key}（{st}）")
    changed = {k: v for k, v in fields.items() if it["data"].get(k, "") != v}
    if not changed: return "(没变化)"
    patch(env, key, it["version"], changed)
    log(f"## {date.today()} — set（改字段）", f"- {key} | {it['data']['title'][:60]} | " + " | ".join(f"{k}: {it['data'].get(k, '')[:40]!r} -> {v[:60]!r}" for k, v in changed.items()) + (f" | {why}" if why else ""))
    return "ok " + ", ".join(changed)


def log(*lines):
    """追加审计日志（logs/zotero-organize.log.md）。第一个参数一般是 '## 日期 — 动作' 段头。"""
    with open(LOG, "a", encoding="utf-8") as f: f.write("\n" + "\n".join(lines) + "\n")
