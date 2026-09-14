"""fetch: link -> metadata + PDF + full text + duplicate check + proposed title, all staged in inbox/<slug>.{json,pdf,txt}; the library is not touched."""
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
    if not os.path.exists(p): raise RuntimeError(f"{slug} is not in the inbox; fetch it first")
    return json.load(open(p, encoding="utf-8"))


def list_inbox():
    out = []
    for f in sorted(os.listdir(INBOX)) if os.path.isdir(INBOX) else []:
        if f.endswith(".json"): out.append(json.load(open(os.path.join(INBOX, f), encoding="utf-8")))
    return out


def clear(slug):
    """After saving, drop the three inbox files: Zotero keeps its own copy of the PDF; json/txt were only for tagging."""
    for ext in (".json", ".txt", ".pdf"):
        p = os.path.join(INBOX, slug + ext)
        if os.path.exists(p): os.remove(p)


_LIB = None

def find_duplicate(m):
    global _LIB
    if _LIB is None: _LIB = localdb.dump()          # refresh the local library snapshot once
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
    if kind in ("pdf", "file"):                                    # get the PDF first, then find the arXiv id / DOI on its first page
        tmp = os.path.join(INBOX, hashlib.sha1(ident.encode()).hexdigest()[:10] + ".pdf")
        if kind == "file": shutil.copy(ident, tmp); ok, why = True, ident
        else: ok, why = download_pdf(ident, tmp)
        if not ok: raise RuntimeError(f"PDF download failed: {why}")
        kind, ident = ids_from_pdf_text(pdf_text(tmp, tmp[:-4] + ".txt", first_pages=2))
        if os.path.exists(tmp[:-4] + ".txt"): os.remove(tmp[:-4] + ".txt")
        if not kind: raise RuntimeError(f"no arXiv id or DOI on the PDF's first page, so no metadata (file kept at {tmp}); for DOI-less venues (JMLR etc.) give the paper page instead, which has citation_* meta")
        pre_pdf = tmp
    elif kind == "page":
        page_url = ident; kind, ident, pdf_hint = ids_from_page(ident)
        if kind == "pdf":                                              # the page only offers a PDF: download it and read the id off the first page
            tmp = os.path.join(INBOX, hashlib.sha1(ident.encode()).hexdigest()[:10] + ".pdf")
            ok, why = download_pdf(ident, tmp)
            if not ok: raise RuntimeError(f"the PDF linked from the page failed to download: {why}")
            pdf_from = ident; kind, ident = ids_from_pdf_text(pdf_text(tmp, tmp[:-4] + ".txt", first_pages=2))
            if os.path.exists(tmp[:-4] + ".txt"): os.remove(tmp[:-4] + ".txt")
            pre_pdf = tmp
        if not kind: kind, ident = "page", page_url                     # neither page nor PDF has an arXiv id / DOI: rely on the page's citation_* meta (JMLR etc.), keep the PDF
    if kind == "openreview":                                       # the API is often behind a bot check -> fall back to the PDF route
        try: m = meta_openreview(ident)
        except Exception as e:
            tmp = os.path.join(INBOX, ident + ".pdf"); ok, why = download_pdf(f"https://openreview.net/pdf?id={ident}", tmp)
            if not ok: raise RuntimeError(f"OpenReview API refused ({str(e)[:80]}) and the PDF failed too ({why}); try the arXiv link")
            kind, ident2 = ids_from_pdf_text(pdf_text(tmp, tmp[:-4] + ".txt", first_pages=2))
            if os.path.exists(tmp[:-4] + ".txt"): os.remove(tmp[:-4] + ".txt")
            if not kind: raise RuntimeError(f"OpenReview API refused and the PDF's first page has no arXiv id / DOI (file kept at {tmp}); try the arXiv link")
            pre_pdf, ident = tmp, ident2
    if kind != "openreview": m = {"arxiv": meta_arxiv, "doi": meta_crossref, "page": meta_page}[kind](ident)
    m["link"] = link; m["slug"] = slug_of(kind, ident)
    pdf = os.path.join(INBOX, m["slug"] + ".pdf"); txt = os.path.join(INBOX, m["slug"] + ".txt")
    if pre_pdf: shutil.move(pre_pdf, pdf); m["pdf_src"] = pdf_from
    else:
        cands = [u for u in ([m.get("pdf_url"), pdf_hint] + m.get("pdf_candidates", [])) if u]
        if m["source"] == "crossref":                                    # journal / conference paper: an arXiv version is the PDF fallback
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
        if m["source"] in ("crossref", "page"):                          # a date printed on the PDF first page beats Crossref / citation meta
            got = pdf_first_page_date(text, m.get("pub_year"))
            if got: m["date"], m["date_src"] = got
            m["item"]["date"] = m["date"]
    if m["source"] == "arxiv": lookup_published(m, text if os.path.exists(pdf) else None)   # preprint: look for the published venue
    m["project_urls"] = project_urls(m, text if os.path.exists(pdf) else None, pdf=pdf if os.path.exists(pdf) else None)
    m["project_url"] = next((u for u in m["project_urls"] if project_url_score(u, text if os.path.exists(pdf) else None)), None)   # only project-page-like candidates become the URL field automatically
    m["proposed_title"] = make_title(m)
    m["short_title"] = short_title(m["title"])
    dup = find_duplicate(m); m["duplicate"] = {"key": dup["key"], "title": dup["title"]} if dup else None
    with open(os.path.join(INBOX, m["slug"] + ".json"), "w", encoding="utf-8") as f: json.dump(m, f, ensure_ascii=False, indent=1)
    return m

def card(m):
    a = ", ".join((x["firstName"] + " " + x["lastName"]).strip() for x in m["authors"][:3]) + (" …" if len(m["authors"]) > 3 else "")
    print(f"=== {m['slug']}  ({m['source']}: {m['id']})")
    print(f"  link      : {m.get('link')}")
    print(f"  title     : {m['title']}")
    print(f"  authors   : {a}")
    print(f"  date      : {m.get('date') or '?'}  <- {m.get('date_src')}")
    print(f"  venue     : {m.get('venue')}  <- {m.get('venue_src')}" + (f"   (comment: {m['comment']})" if m.get("comment") else ""))
    print(f"  proposed  : {m['proposed_title']}   short title: {m.get('short_title')}")
    others = [u for u in (m.get("project_urls") or []) if u != m.get("project_url")]
    print(f"  project   : {m.get('project_url') or 'none found (URL field will be ' + (m.get('url') or '-') + '; override with --url)'}" + (f"   candidates: {others}" if others else ""))
    print(f"  PDF       : {'inbox/' + m['slug'] + '.pdf  <- ' + m['pdf_src'] if m.get('pdf_src') else 'not obtained  ' + '; '.join(m.get('pdf_tried', []))}")
    print(f"  full text : inbox/{m['slug']}.txt" if m.get("pdf_src") else "  full text : none (abstract only)")
    if m.get("duplicate"): print(f"  ! duplicate: already in the library as {m['duplicate']['key']} | {m['duplicate']['title']}")
    print(f"  abstract  : {m['abstract'][:1500]}\n")
