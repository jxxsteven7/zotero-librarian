"""存量复核：[arXiv] 标题查中稿、--dates 核对标题日期是否 v1 提交日。默认只列表，--write 才改（approval mode）。"""
import os, re, time
from datetime import date

from . import localdb, zapi
from .config import DATA_DIR
from .pdf import pdf_text
from .published import lookup_published, s2_venues
from .sources import ARXIV_ID, arxiv_batch, arxiv_by_title
from .venues import venue_from_context


def recheck(write=False, only=None, dates=False, search=False):
    """[arXiv] 标题查中稿（arXiv comment → PDF 首页声明 → Semantic Scholar → Crossref → 项目页）；--dates 再核对日期是否 v1 提交日；
    --search 对没有 arXiv 链接/水印的条目按标题去 arXiv 搜预印本（期刊/会议论文若有更早的预印本，日期用预印本 v1；每条 3 秒）。
    先跑 zc.py dump。默认只列表；--write 才经 Web API 改标题（approval mode：先给用户看表）。"""
    items = localdb.load()
    cands = []
    for it in items:
        if only and it["key"] not in only: continue
        aid = None                                                       # 只认 arxiv.org 链接或 10.48550/arXiv.* 的 DOI，别的 DOI 里的数字会误配
        for blob in ((it.get("url") or ""), (it.get("doi") or "")):
            if "arxiv.org" in blob.lower() or blob.lower().startswith("10.48550/arxiv."):
                got = re.search(ARXIV_ID, blob); aid = got.group(1) if got else None
                if aid: break
        is_arxiv = "[arXiv]" in it["title"]
        text = ""
        if (is_arxiv or (dates and not aid)) and it.get("pdfs"):            # 首页文本：查出版声明；url 里没 arXiv 号的从首页水印认
            text = pdf_text(os.path.join(DATA_DIR, it["pdfs"][0]), first_pages=1)
            if not aid:
                got = re.search(r"arXiv:" + ARXIV_ID, text); aid = got.group(1) if got else None
        if not aid and search and dates:                                  # 按标题搜 arXiv（用户短名如 "PPO" 搜不到，跳过）
            name = re.sub(r"^(\s*\[[^\]]*\]\s*){1,3}", "", it["title"]); name = re.sub(r"[✅❗]", "", name).strip()
            if len(re.sub(r"[^\x20-\x7e]", "", name)) >= 12:
                aid = arxiv_by_title(name); time.sleep(3)
        if is_arxiv or (dates and aid): cands.append(dict(key=it["key"], title=it["title"], aid=aid, text=text, is_arxiv=is_arxiv, abstract=it.get("abstract", "")))
    ids = list(dict.fromkeys(c["aid"] for c in cands if c["aid"]))
    ax = arxiv_batch(ids)                                                # comment/journal_ref + v1 日期（API 限流时逐条抓 abs 页面）
    s2 = s2_venues([c["aid"] for c in cands if c["is_arxiv"] and c["aid"]])
    rows = []
    for c in cands:
        new, why = c["title"], []
        if c["is_arxiv"]:
            m = dict(id=c["aid"], title=re.sub(r"^(\s*\[[^\]]*\]\s*){1,2}", "", c["title"]), venue="arXiv", venue_src="default",
                     comment=ax.get(c["aid"], {}).get("ctx", ""), abstract=c.get("abstract", ""))
            v = venue_from_context(ax.get(c["aid"], {}).get("ctx", ""))
            if v: m["venue"], m["venue_src"] = v, "arxiv-comment: " + ax[c["aid"]]["ctx"][:80]
            else: lookup_published(m, c["text"], s2 if c["aid"] else {})
            if m["venue"] != "arXiv": new = new.replace("[arXiv]", f"[{m['venue']}]", 1); why.append(m["venue_src"])
            elif m["venue_src"] != "default": why.append(m["venue_src"])
        if dates and c["aid"] in ax:
            d = re.match(r"\[(\d{4})-(\d{2})(\d{2})\]", c["title"]); v1 = ax[c["aid"]]["v1"]
            if d and f"{d.group(1)}-{d.group(2)}-{d.group(3)}" != v1:
                new = f"[{v1[:4]}-{v1[5:7]}{v1[8:]}]" + new[len(d.group(0)):]
                why.append(f"日期 {d.group(0)} 不是 v1 提交日 {v1}（最新版 {ax[c['aid']]['latest']}）")
        rows.append((c["key"], c["title"], new if new != c["title"] else None, "; ".join(why)))
        mark = f"→ {new[:60]}" if new != c["title"] else ("（仍是 arXiv）" if c["is_arxiv"] else "ok")
        print(f"{c['key']} | {c['title'][:60]} | {mark} | {'; '.join(why)[:120]}")
    hits = [r for r in rows if r[2]]
    print(f"\n{len(rows)} 条复核，要改标题 {len(hits)} 条。")
    if not write or not hits: return
    env = zapi.env_or_die(); done = []
    for key, old, new, why in hits:
        st, h, it = zapi.req(env, "GET", f"/items/{key}")
        if st != 200: print(f"  ✗ {key} GET {st}"); continue
        if it["data"]["title"] != old: print(f"  ✗ {key} 远端标题和 dump 不一致，跳过: {it['data']['title'][:60]}"); continue
        st, h, body = zapi.req(env, "PATCH", f"/items/{key}", {"title": new, "version": it["version"]})
        print(f"  {'ok' if st in (200, 204) else '✗ ' + str(st)} {key} {old[:40]!r} -> {new[:60]!r}")
        if st in (200, 204): done.append((key, old, new, why))
    if done:
        zapi.log(f"## {date.today()} — recheck（arXiv 条目标题复核）", "### Applied",
                 *[f"- {key} | {old[:60]} -> {new[:70]} | {why[:110]}" for key, old, new, why in done])
