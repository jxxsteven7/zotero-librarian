"""recheck — re-verify existing arXiv items: has an [arXiv] paper been published? (--dates) is the title date the v1 submission date?
Lists only; --write applies the title changes through the Web API (approval mode: show the table to the user first)."""
import os, re, time
from datetime import date

from . import localdb, zapi
from .config import DATA_DIR
from .pdf import pdf_text
from .published import lookup_published, s2_venues
from .sources import ARXIV_ID, arxiv_batch, arxiv_by_title
from .titles import strip_prefix
from .venues import venue_from_context


def recheck(write=False, only=None, dates=False, search=False):
    """[arXiv] titles: look for the published venue (arXiv comment -> PDF first page -> Semantic Scholar -> Crossref -> project page);
    --dates: also check that the title date is the v1 submission date; --search: for items without an arXiv link / watermark,
    search arXiv by title for an earlier preprint (a journal paper with an earlier preprint takes the preprint's v1 date; 3 s each).
    Run `zl.py dump` first. Lists only; --write changes titles through the Web API."""
    from .taxonomy import TITLE_PREFIX
    if write and not TITLE_PREFIX: print("[library] title_prefix = false: titles are never rewritten; listing only"); write = False
    items = localdb.load()
    cands = []
    for it in items:
        if only and it["key"] not in only: continue
        aid = None                                                       # only arxiv.org links or 10.48550/arXiv.* DOIs; digits in other DOIs would mis-match
        for blob in ((it.get("url") or ""), (it.get("doi") or "")):
            if "arxiv.org" in blob.lower() or blob.lower().startswith("10.48550/arxiv."):
                got = re.search(ARXIV_ID, blob); aid = got.group(1) if got else None
                if aid: break
        is_arxiv = "[arXiv]" in it["title"]
        text = ""
        if (is_arxiv or (dates and not aid)) and it.get("pdfs"):            # first-page text: venue statement; arXiv id from the watermark when the URL has none
            text = pdf_text(os.path.join(DATA_DIR, it["pdfs"][0]), first_pages=1)
            if not aid:
                got = re.search(r"arXiv:" + ARXIV_ID, text); aid = got.group(1) if got else None
        if not aid and search and dates:                                  # search arXiv by title (user short names like "PPO" are skipped)
            name = re.sub(r"[✅❗]", "", strip_prefix(it["title"])).strip()
            if len(re.sub(r"[^\x20-\x7e]", "", name)) >= 12:
                aid = arxiv_by_title(name); time.sleep(3)
        if is_arxiv or (dates and aid): cands.append(dict(key=it["key"], title=it["title"], aid=aid, text=text, is_arxiv=is_arxiv, abstract=it.get("abstract", "")))
    ids = list(dict.fromkeys(c["aid"] for c in cands if c["aid"]))
    ax = arxiv_batch(ids)                                                # comment / journal_ref + v1 date (abs pages when the API is rate-limited)
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
                why.append(f"date {d.group(0)} is not the v1 submission date {v1} (latest version {ax[c['aid']]['latest']})")
        rows.append((c["key"], c["title"], new if new != c["title"] else None, "; ".join(why)))
        mark = f"-> {new[:60]}" if new != c["title"] else ("(still arXiv)" if c["is_arxiv"] else "ok")
        print(f"{c['key']} | {c['title'][:60]} | {mark} | {'; '.join(why)[:120]}")
    hits = [r for r in rows if r[2]]
    print(f"\n{len(rows)} items checked, {len(hits)} titles to change.")
    if not write or not hits: return
    env = zapi.env_or_die(); done = []
    for key, old, new, why in hits:
        st, h, it = zapi.req(env, "GET", f"/items/{key}")
        if st != 200: print(f"  x {key} GET {st}"); continue
        if it["data"]["title"] != old: print(f"  x {key} server title differs from the dump, skipped: {it['data']['title'][:60]}"); continue
        st, h, body = zapi.req(env, "PATCH", f"/items/{key}", {"title": new, "version": it["version"]})
        print(f"  {'ok' if st in (200, 204) else 'x ' + str(st)} {key} {old[:40]!r} -> {new[:60]!r}")
        if st in (200, 204): done.append((key, old, new, why))
    if done:
        zapi.log(f"## {date.today()} — recheck", "### Applied",
                 *[f"- {key} | {old[:60]} -> {new[:70]} | {why[:110]}" for key, old, new, why in done])
