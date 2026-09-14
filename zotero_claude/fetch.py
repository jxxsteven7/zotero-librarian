"""fetch：链接 → 元数据 + PDF + 全文 txt + 查重 + 建议标题，全部落在 inbox/<slug>.{json,pdf,txt}，不动库。"""
import hashlib, json, os, re, shutil, urllib.parse
import xml.etree.ElementTree as ET

from . import localdb
from .config import INBOX
from .http import get_text
from .pdf import download_pdf, pdf_text, pdf_first_page_date, project_urls, project_url_score
from .published import lookup_published
from .sources import ARXIV_ID, classify_link, slug_of, meta_arxiv, meta_crossref, meta_openreview, meta_page, ids_from_pdf_text, ids_from_page
from .titles import make_title, norm_title, short_title


def load(slug):
    p = os.path.join(INBOX, slug + ".json")
    if not os.path.exists(p): raise RuntimeError(f"inbox 里没有 {slug}，先 fetch")
    return json.load(open(p, encoding="utf-8"))


def list_inbox():
    out = []
    for f in sorted(os.listdir(INBOX)) if os.path.isdir(INBOX) else []:
        if f.endswith(".json"): out.append(json.load(open(os.path.join(INBOX, f), encoding="utf-8")))
    return out


def clear(slug):
    """入库后 inbox 里的三个文件都删：PDF Zotero 已存了自己的一份，json/txt 只在定标签时有用。"""
    for ext in (".json", ".txt", ".pdf"):
        p = os.path.join(INBOX, slug + ext)
        if os.path.exists(p): os.remove(p)


_LIB = None

def find_duplicate(m):
    global _LIB
    if _LIB is None: _LIB = localdb.dump()          # 刷新一次本地库快照
    lib = _LIB
    aid = m["id"] if m["source"] == "arxiv" else (m.get("arxiv_id") or "")
    doi = (m["id"] if m["source"] == "crossref" else m.get("doi") or "").lower()
    nt = norm_title(m["title"])
    for it in lib:
        blob = " ".join(str(it.get(k) or "") for k in ("url", "doi", "title")).lower()
        if aid and re.search(r"(?<![\d.])" + re.escape(aid.lower()) + r"(?![\d])", blob): return it
        if doi and doi in blob: return it
        if nt and norm_title(it.get("title")) == nt: return it
    return None

def fetch_one(link):
    os.makedirs(INBOX, exist_ok=True)
    kind, ident = classify_link(link); pdf_hint = None; pre_pdf = None; pdf_from = link
    if kind in ("pdf", "file"):                                    # 先拿到 PDF，从首页找 arXiv 号 / DOI
        tmp = os.path.join(INBOX, hashlib.sha1(ident.encode()).hexdigest()[:10] + ".pdf")
        if kind == "file": shutil.copy(ident, tmp); ok, why = True, ident
        else: ok, why = download_pdf(ident, tmp)
        if not ok: raise RuntimeError(f"PDF 下不下来: {why}")
        kind, ident = ids_from_pdf_text(pdf_text(tmp, tmp[:-4] + ".txt", first_pages=2))
        if os.path.exists(tmp[:-4] + ".txt"): os.remove(tmp[:-4] + ".txt")
        if not kind: raise RuntimeError(f"PDF 首页找不到 arXiv 号或 DOI，没法拿元数据（文件留在 {tmp}）；没有 DOI 的刊物（JMLR 之类）请给论文页链接，脚本读 citation_* meta")
        pre_pdf = tmp
    elif kind == "page":
        page_url = ident; kind, ident, pdf_hint = ids_from_page(ident)
        if kind == "pdf":                                              # 页面只给了 PDF：下下来从首页认 arXiv 号 / DOI
            tmp = os.path.join(INBOX, hashlib.sha1(ident.encode()).hexdigest()[:10] + ".pdf")
            ok, why = download_pdf(ident, tmp)
            if not ok: raise RuntimeError(f"页面上的 PDF 下不下来: {why}")
            pdf_from = ident; kind, ident = ids_from_pdf_text(pdf_text(tmp, tmp[:-4] + ".txt", first_pages=2))
            if os.path.exists(tmp[:-4] + ".txt"): os.remove(tmp[:-4] + ".txt")
            pre_pdf = tmp
        if not kind: kind, ident = "page", page_url                     # 页面和 PDF 都没有 arXiv 号 / DOI：靠页面的 citation_* meta（JMLR 之类），PDF 留用
    if kind == "openreview":                                       # API 常被人机验证挡住 → 退到 PDF 路线
        try: m = meta_openreview(ident)
        except Exception as e:
            tmp = os.path.join(INBOX, ident + ".pdf"); ok, why = download_pdf(f"https://openreview.net/pdf?id={ident}", tmp)
            if not ok: raise RuntimeError(f"OpenReview API 拒了（{str(e)[:80]}），PDF 也下不了（{why}）；给 arXiv 链接吧")
            kind, ident2 = ids_from_pdf_text(pdf_text(tmp, tmp[:-4] + ".txt", first_pages=2))
            if os.path.exists(tmp[:-4] + ".txt"): os.remove(tmp[:-4] + ".txt")
            if not kind: raise RuntimeError(f"OpenReview API 拒了，PDF 首页也认不出 arXiv 号/DOI（文件留在 {tmp}）；给 arXiv 链接吧")
            pre_pdf, ident = tmp, ident2
    if kind != "openreview": m = {"arxiv": meta_arxiv, "doi": meta_crossref, "page": meta_page}[kind](ident)
    m["link"] = link; m["slug"] = slug_of(kind, ident)
    pdf = os.path.join(INBOX, m["slug"] + ".pdf"); txt = os.path.join(INBOX, m["slug"] + ".txt")
    if pre_pdf: shutil.move(pre_pdf, pdf); m["pdf_src"] = pdf_from
    else:
        cands = [u for u in ([m.get("pdf_url"), pdf_hint] + m.get("pdf_candidates", [])) if u]
        if m["source"] == "crossref":                                    # 期刊/会议论文：找 arXiv 版本兜底
            try:
                q = urllib.parse.quote(f'ti:"{m["title"]}"'); ns = {"a": "http://www.w3.org/2005/Atom"}
                for e in ET.fromstring(get_text(f"https://export.arxiv.org/api/query?search_query={q}&max_results=3")).findall("a:entry", ns):
                    if norm_title(e.findtext("a:title", "", ns)) == norm_title(m["title"]):
                        aid = re.search(ARXIV_ID, e.findtext("a:id", "", ns)).group(1); m["arxiv_id"] = aid
                        cands.append(f"https://arxiv.org/pdf/{aid}"); break
            except Exception: pass
        m["pdf_src"] = None; tried = []
        for u in cands:
            ok, why = download_pdf(u, pdf)
            if ok: m["pdf_src"] = u; break
            tried.append(f"{u} → {why}")
        m["pdf_tried"] = tried
    if os.path.exists(pdf):
        text = pdf_text(pdf, txt)
        if m["source"] in ("crossref", "page"):                          # PDF 首页印的上线日优先级高于 Crossref / citation meta
            got = pdf_first_page_date(text, m.get("pub_year"))
            if got: m["date"], m["date_src"] = got
            m["item"]["date"] = m["date"]
    if m["source"] == "arxiv": lookup_published(m, text if os.path.exists(pdf) else None)   # 预印本查中稿，查到就写会议
    m["project_urls"] = project_urls(m, text if os.path.exists(pdf) else None, pdf=pdf if os.path.exists(pdf) else None)
    m["project_url"] = next((u for u in m["project_urls"] if project_url_score(u, text if os.path.exists(pdf) else None)), None)   # 像项目页的才自动当 URL；其余只列候选
    m["proposed_title"] = make_title(m)
    m["short_title"] = short_title(m["title"])
    dup = find_duplicate(m); m["duplicate"] = {"key": dup["key"], "title": dup["title"]} if dup else None
    with open(os.path.join(INBOX, m["slug"] + ".json"), "w", encoding="utf-8") as f: json.dump(m, f, ensure_ascii=False, indent=1)
    return m

def card(m):
    a = ", ".join((x["firstName"] + " " + x["lastName"]).strip() for x in m["authors"][:3]) + (" …" if len(m["authors"]) > 3 else "")
    print(f"=== {m['slug']}  ({m['source']}: {m['id']})")
    print(f"  链接    : {m.get('link')}")
    print(f"  标题    : {m['title']}")
    print(f"  作者    : {a}")
    print(f"  日期    : {m.get('date') or '?'}  ← {m.get('date_src')}")
    print(f"  刊/会   : {m.get('venue')}  ← {m.get('venue_src')}" + (f"   (comment: {m['comment']})" if m.get("comment") else ""))
    print(f"  建议标题: {m['proposed_title']}   短名: {m.get('short_title')}")
    others = [u for u in (m.get("project_urls") or []) if u != m.get("project_url")]
    print(f"  项目页  : {m.get('project_url') or '没认出（URL 字段将用 ' + (m.get('url') or '-') + '，可 --url 指定）'}" + (f"   候选: {others}" if others else ""))
    print(f"  PDF     : {'inbox/' + m['slug'] + '.pdf  ← ' + m['pdf_src'] if m.get('pdf_src') else '没拿到  ' + '; '.join(m.get('pdf_tried', []))}")
    print(f"  全文    : inbox/{m['slug']}.txt" if m.get("pdf_src") else "  全文    : 无（只能靠摘要）")
    if m.get("duplicate"): print(f"  ⚠ 重复  : 库里已有 {m['duplicate']['key']} | {m['duplicate']['title']}")
    print(f"  摘要    : {m['abstract'][:1500]}\n")
