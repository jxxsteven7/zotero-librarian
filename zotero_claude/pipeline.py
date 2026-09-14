"""端到端入库：fetch → 自动分类/贴标签（classify）→ connector 入库 → 等远端同步核对 → 提交日志 → 打印汇报表。
`/download` skill 只跑 `zc.py add <链接>…`，把打印出来的汇报转给用户即可；需要人定的地方脚本会标 ⏸ / ⚠。"""
import os, subprocess

from . import classify, connector, fetch, localdb, zapi
from .config import INBOX, LOG, ROOT
from .vocab import COLLECTIONS, sort_tags

PAUSE_FLAGS = ("Humanoid / Dex-Manipulation 边界", "确认是否该归 Dex-Manipulation")     # 这两种分类拿不准时不自动入库


def _text(slug):
    p = os.path.join(INBOX, slug + ".txt")
    return open(p, encoding="utf-8").read() if os.path.exists(p) else ""


def suggest_for(m):
    return classify.suggest(m["title"], m.get("abstract", ""), _text(m["slug"]), has_pdf=bool(m.get("pdf_src")))


def brief(m, sg):
    """比 fetch 的卡片短：不贴整段摘要（分类已经由脚本判了），只给人核对需要的。"""
    a = ", ".join((x["firstName"] + " " + x["lastName"]).strip() for x in m["authors"][:3]) + (" …" if len(m["authors"]) > 3 else "")
    print(f"=== {m['slug']}  ({m['source']}: {m['id']})")
    print(f"  标题    : {m['proposed_title']}   短名: {m.get('short_title')}")
    print(f"  作者    : {a}")
    print(f"  日期    : {m.get('date') or '?'} ← {m.get('date_src')}   刊/会: {m.get('venue')} ← {m.get('venue_src')}")
    print(f"  URL     : {m.get('project_url') or (m.get('url') or '-') + '（没认出项目页）'}")
    print(f"  PDF     : {'ok ← ' + m['pdf_src'] if m.get('pdf_src') else '没拿到 ' + '; '.join(m.get('pdf_tried', []))[:200]}")
    if m.get("duplicate"): print(f"  ⚠ 重复  : 库里已有 {m['duplicate']['key']} | {m['duplicate']['title']}")
    print(f"  摘要    : {m.get('abstract', '')[:300]}…")
    print(classify.fmt(sg))


def decide(sg, collection=None, tags=None, drop=None, also=None, first=False):
    """把脚本建议和命令行覆盖合成最终 (collection, also, tags)。"""
    coll = collection or sg["collection"]
    if coll not in COLLECTIONS: raise RuntimeError(f"分类只能是 {COLLECTIONS}")
    tags = [t for t in sg["sure"] if t not in set(drop or [])] + [t for t in (tags or []) if t]
    tags = sort_tags(tags + (["status:to-read-first"] if first else []))
    return coll, (also or sg["also"]), tags


def verify(key, wait=150, quiet=False):
    """远端（Web API）+ 本地（sqlite）核对一条：等客户端把新条目同步上去，最多 wait 秒。返回 dict 或 None。"""
    env = zapi.env_or_die()
    it = zapi.wait_remote(env, key, wait=wait, step=10)                      # wait=0 只查一次
    if not it:
        if not quiet: print(f"  同步    : ✗ 等了 {wait}s 远端还没有 {key}（Zotero 没开自动同步？稍后 python3 zc.py verify {key}）")
        return None
    names = {v: k for k, v in zapi.remote_collections(env)[0].items()}
    d = it["data"]; kids = [(c["data"].get("title"), c["data"].get("linkMode")) for c in zapi.children(env, key)]
    synced, ver = localdb.sync_state(key)
    info = dict(version=it["version"], title=d["title"], tags=sorted(t["tag"] for t in d["tags"]), collections=[names.get(c, c) for c in d["collections"]],
                url=d.get("url", ""), short=d.get("shortTitle", ""), children=kids, local_synced=synced, local_version=ver,
                notion="Notion" in [k[0] for k in kids])
    if not quiet:
        print(f"  同步    : ✓ 远端 v{info['version']} | 分类 {info['collections']} | 标签 {info['tags']}")
        print(f"            URL {info['url']} | 短名 {info['short']} | 附件 {[k[0] for k in kids]} | 本地 synced={synced}" + ("" if info["notion"] else " | Notion 附件还没出现（Notero 一般 1 分钟内推）"))
    return info


def commit_log(msg):
    """把审计日志这一个文件提交并推送（其他改动不碰），失败只警告不中断。"""
    def git(*a): return subprocess.run(["git", "-C", ROOT] + list(a), capture_output=True, text=True)
    rel = os.path.relpath(LOG, ROOT)
    if not git("status", "--porcelain", "--", rel).stdout.strip(): return "日志没变化"
    git("add", "--", rel)
    r = git("commit", "-q", "-m", msg + "\n\nCo-Authored-By: Claude <noreply@anthropic.com>", "--", rel)
    if r.returncode: return "commit 失败: " + (r.stderr or r.stdout).strip()[:200]
    r = git("push", "-q")
    return "已提交并推送" if r.returncode == 0 else "已提交，push 失败（" + (r.stderr or r.stdout).strip()[:120] + "）——稍后 git push"


def report_row(got, sg, info, note_extra=""):
    notes = []
    if sg["maybe"]: notes.append("候选: " + "; ".join(f"`{t}`（{w}）" for t, w in sg["maybe"].items()))
    notes += [f for f in sg["flags"] if "Evolution Algorithm" not in f]
    if "⚠" in (got.get("date_src") or "") or "⚠" in (got.get("venue_src") or ""): notes.append(f"日期/刊会有 ⚠：{got.get('date_src')} / {got.get('venue_src')}")
    if note_extra: notes.append(note_extra)
    sync = "✓" if info else "⏳ 未确认"
    return (f"| `{got['key']}` | {got['title']} | {got['collection']}" + (f" + {got['also']}" if got.get("also") else "") +
            f" | {', '.join(t for t in got['tags_written'] if t != 'notion')} | {'✓' if got['pdf_ok'] else '✗'} | 同步{sync}。" + ("；".join(notes) or "—") + " |")


def finish(slug, m, sg, coll, also, tags, venue=None, date_=None, name=None, url=None, short=None, force=False, wait=150, commit=True):
    """入库 + 核对 + 提交日志 + 汇报行。save 和 add 共用。"""
    got = connector.save(slug, coll, tags, also=also, venue=venue, date_=date_, name=name, force=force, url=url, short=short)
    got.update(date_src=m.get("date_src"), venue_src=m.get("venue_src"))
    info = verify(got["key"], wait=wait) if wait else None
    git_msg = commit_log(f"日志：收 {got['short']}") if commit else "未提交（--no-commit）"
    print(f"  git     : {git_msg}")
    row = report_row(got, sg, info)
    print("\n" + row + "\n")
    return got, row


HEADER = "| key | 标题 | 分类 | 标签 | PDF | 备注 |\n|---|---|---|---|---|---|"


def add(links, collection=None, tags=None, drop=None, also=None, first=False, force=False, wait=150, commit=True, dry_run=False,
        venue=None, date_=None, name=None, url=None, short=None):
    rows = []
    for link in links:
        try: m = fetch.fetch_one(link)
        except Exception as e:
            print(f"=== {link}\n  ✗ {e}\n"); rows.append(f"| — | {link} | — | — | — | ✗ {str(e)[:120]} |"); continue
        sg = suggest_for(m)
        brief(m, sg)
        if m.get("duplicate") and not force:
            d = m["duplicate"]; print(f"  → 重复，跳过（--force 才再加）\n"); fetch.clear(m["slug"])
            rows.append(f"| `{d['key']}` | {d['title']} | — | — | — | 重复，库里已有，跳过 |"); continue
        coll, also_, tags_ = decide(sg, collection, tags, drop, also, first)
        if dry_run:
            print(f"  [dry-run] 会入库：{coll}" + (f" + {also_}" if also_ else "") + f" | {', '.join(tags_)}\n"); continue
        if not collection and any(any(p in f for p in PAUSE_FLAGS) for f in sg["flags"]):
            print(f"  ⏸ 分类拿不准，没入库。定了以后跑：\n     python3 zc.py save {m['slug']} --collection \"{coll}\"" +
                  (f" --also \"{also_}\"" if also_ else "") + (f" --tags {','.join(t for t in tags_ if t != 'status:to-read')}" if [t for t in tags_ if t != 'status:to-read'] else "") + "\n")
            rows.append(f"| ⏸ | {m['proposed_title']} | {coll}? | {', '.join(tags_)} | {'✓' if m.get('pdf_src') else '✗'} | 分类待定：{'；'.join(sg['flags'])} |"); continue
        got, row = finish(m["slug"], m, sg, coll, also_, tags_, venue, date_, name, url, short, force, wait, commit)
        rows.append(row)
    print("\n" + HEADER + "\n" + "\n".join(rows))
    return rows


def save(slug, collection=None, tags=None, drop=None, also=None, first=False, force=False, wait=150, commit=True,
         venue=None, date_=None, name=None, url=None, short=None):
    """fetch 过、需要人定分类/标签之后的入库：不给 --tags 就用脚本建议的标签。"""
    m = fetch.load(slug); sg = suggest_for(m)
    coll, also_, tags_ = decide(sg, collection, tags, drop, also, first)
    got, row = finish(slug, m, sg, coll, also_, tags_, venue, date_, name, url, short, force, wait, commit)
    print("\n" + HEADER + "\n" + row)
    return got
