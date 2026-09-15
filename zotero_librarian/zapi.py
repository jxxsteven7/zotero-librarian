"""Zotero Web API v3 (library id from .env). Every modification of existing items goes through here; PDFs do not
(see connector.py). Write rules: tags / collections are replaced wholesale, so payloads start from the remote state
and only add; the remote `version` is the optimistic lock. The API key is never printed."""
import json, sys, time, urllib.error, urllib.request
from datetime import date

from .config import append_log, load_env
from .taxonomy import check_tags

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
    raise RuntimeError("retries exhausted: " + url)


def env_or_die():
    env = load_env()
    if not env.get("ZOTERO_API_KEY"):
        sys.exit("ZOTERO_API_KEY missing: put ZOTERO_API_KEY=... in the repo's .env (never paste it into the conversation)")
    return env


def remote_collections(env):
    """{name: key}, {key: data} — every collection of the library (paged by 100)."""
    js = []
    while True:
        st, _, page = req(env, "GET", "/collections", params=f"?limit=100&start={len(js)}")
        if st != 200: sys.exit(f"GET collections -> {st} {page}")
        js += page
        if len(page) < 100: break
    return {c["data"]["name"]: c["key"] for c in js}, {c["key"]: c["data"] for c in js}


def create_collection(env, name):
    """Create a top-level collection; returns its key. Used only by `zl.py tidy --create-collections`."""
    st, _, js = req(env, "POST", "/collections", body=[{"name": name, "parentCollection": False}])
    if st != 200 or not js.get("successful"): sys.exit(f"POST collections {name!r} -> {st} {js}")
    key = js["successful"]["0"]["key"]
    log(f"## {date.today()} — create collection", f"- {key} | {name}")
    return key


def get_item(env, key):
    """(status, item json or error text)"""
    st, _, js = req(env, "GET", f"/items/{key}")
    return st, js


def children(env, key):
    st, _, js = req(env, "GET", f"/items/{key}/children")
    return js if st == 200 else []


def wait_remote(env, key, wait=180, step=10):
    """An item just saved through the connector is only GET-able once the client has synced it; wait up to `wait` seconds. Item or None."""
    t0 = time.time()
    while True:
        st, it = get_item(env, key)
        if st == 200: return it
        if time.time() - t0 > wait: return None
        time.sleep(step)


def patch(env, key, version, fields):
    st, _, body = req(env, "PATCH", f"/items/{key}", dict(fields, version=version))   # optimistic lock
    if st not in (200, 204): raise RuntimeError(f"PATCH {key} {st}: {body}")
    return st


def add_collection(key, name, wait=180):
    """Add a collection to an item (superset write); waits up to `wait` seconds for the client to sync the item up."""
    env = env_or_die()
    ck, _ = remote_collections(env)
    if name not in ck: raise RuntimeError(f"no remote collection named {name!r}")
    it = wait_remote(env, key, wait)
    if not it: raise RuntimeError("item not on the server after %ds" % wait)
    cur = it["data"]["collections"]
    if ck[name] in cur: return "(already there)"
    patch(env, key, it["version"], {"collections": cur + [ck[name]]})
    log(f"## {date.today()} — collect", f"- {key} | {it['data']['title']} | +collection: {name}")
    return "ok"


def add_tags(key, tags):
    """Add tags to an item (remote tags + new ones, never removes). Used after discussing candidate tags with the user. Logged."""
    tags = [t.strip() for t in tags if t.strip()]
    check_tags(tags)
    env = env_or_die()
    st, it = get_item(env, key)
    if st != 200: raise RuntimeError(f"item {key} not on the server ({st}) — a just-saved item needs the client to sync first")
    cur = [t["tag"] for t in it["data"]["tags"]]
    new = [t for t in tags if t not in cur]
    if not new: return "(already tagged)"
    patch(env, key, it["version"], {"tags": it["data"]["tags"] + [{"tag": t, "type": 0} for t in new]})   # type 0 = manual tag
    log(f"## {date.today()} — tag", f"- {key} | {it['data']['title']} | +tags: {', '.join(new)}")
    return "ok +" + ", ".join(new)


def remove_tags(key, tags, why=""):
    """Remove tags. Only to correct a tag the script just assigned wrongly, or when the user explicitly asks. Logged as -tags."""
    tags = [t.strip() for t in tags if t.strip()]
    env = env_or_die()
    st, it = get_item(env, key)
    if st != 200: raise RuntimeError(f"item {key} not on the server ({st})")
    gone = [t["tag"] for t in it["data"]["tags"] if t["tag"] in tags]
    if not gone: return "(not tagged with those)"
    patch(env, key, it["version"], {"tags": [t for t in it["data"]["tags"] if t["tag"] not in tags]})
    log(f"## {date.today()} — untag", f"- {key} | {it['data']['title']} | -tags: {', '.join(gone)}" + (f" | {why}" if why else ""))
    return "ok −" + ", ".join(gone)


def set_fields(key, fields, why=""):
    """Set item fields (title / url / shortTitle ...). Logged with before/after."""
    env = env_or_die()
    st, it = get_item(env, key)
    if st != 200: raise RuntimeError(f"item {key} not on the server ({st})")
    changed = {k: v for k, v in fields.items() if it["data"].get(k, "") != v}
    if not changed: return "(no change)"
    patch(env, key, it["version"], changed)
    log(f"## {date.today()} — set", f"- {key} | {it['data']['title'][:60]} | " + " | ".join(f"{k}: {it['data'].get(k, '')[:40]!r} -> {v[:60]!r}" for k, v in changed.items()) + (f" | {why}" if why else ""))
    return "ok " + ", ".join(changed)


def log(*lines):
    """Append to the audit log (logs/zotero-organize.log.md). The first line is usually a '## date — action' heading."""
    append_log(*lines)
