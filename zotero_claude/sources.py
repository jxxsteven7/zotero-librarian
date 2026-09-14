"""链接识别与元数据源：arXiv（API，限流时抓 abs 页面）、Crossref（DOI）、OpenReview、带 citation_* meta 的论文页。
每个 meta_* 返回统一的 dict：source/id/url/title/authors/abstract/date/date_src/venue/venue_src/item（connector saveItems 的载荷）。"""
import hashlib, html, json, os, re, sys, time, urllib.error, urllib.parse, urllib.request
import xml.etree.ElementTree as ET

from .http import get_text
from .venues import abbr_from_name, venue_from_context
from .titles import clean_title, norm_title, ws


ARXIV_ID = r"(\d{4}\.\d{4,5}|[a-z\-]+(?:\.[A-Z]{2})?/\d{7})(v\d+)?"

def classify_link(link):
    s = link.strip()
    if os.path.isfile(os.path.expanduser(s)): return "file", os.path.expanduser(s)
    m = re.search(r"(?:arxiv\.org|alphaxiv\.org)/(?:abs|pdf|html)/" + ARXIV_ID, s) or re.search(r"huggingface\.co/papers/" + ARXIV_ID, s) \
        or re.fullmatch(r"(?:arxiv:)?" + ARXIV_ID, s, re.I)
    if m: return "arxiv", m.group(1)
    m = re.search(r"openreview\.net/(?:forum|pdf|attachment)\?id=([\w\-]+)", s)
    if m: return "openreview", m.group(1)
    m = re.search(r"doi\.org/(10\.\d{4,9}/\S+)", s) or re.fullmatch(r"(?:doi:)?(10\.\d{4,9}/\S+)", s, re.I)
    if m: return "doi", m.group(1).rstrip(".,;)")
    if re.search(r"\.pdf(?:$|[?#])", s, re.I): return "pdf", s
    return "page", s

def slug_of(kind, ident):
    if kind in ("arxiv", "openreview"): return ident.replace("/", "_")
    if kind == "doi": return re.sub(r"[^\w.\-]+", "_", ident)[:80]
    return hashlib.sha1(ident.encode()).hexdigest()[:10]

PARTICLES = {"van", "der", "den", "de", "von", "da", "di", "del", "della", "la", "le", "du", "dos", "das"}

def split_name(full):
    parts = full.strip().split()
    if len(parts) == 1: return {"firstName": "", "lastName": parts[0], "creatorType": "author"}
    cut = next((i for i in range(1, len(parts) - 1) if parts[i] in PARTICLES), len(parts) - 1)   # 小写小品词起算姓："van der Maaten"
    return {"firstName": " ".join(parts[:cut]), "lastName": " ".join(parts[cut:]), "creatorType": "author"}

def meta_arxiv_api(aid):
    ns = {"a": "http://www.w3.org/2005/Atom", "x": "http://arxiv.org/schemas/atom"}
    xml = get_text(f"https://export.arxiv.org/api/query?id_list={aid}")
    e = ET.fromstring(xml).find("a:entry", ns)
    if e is None or e.find("a:title", ns) is None or "Error" in (e.findtext("a:title", "", ns)): raise RuntimeError("arXiv API 没找到 " + aid)
    idurl = e.findtext("a:id", "", ns); ver = re.search(r"v(\d+)$", idurl)
    cat = e.find("x:primary_category", ns); cat = cat.get("term") if cat is not None else ""
    return dict(title=clean_title(e.findtext("a:title", "", ns)),
                authors=[split_name(a.findtext("a:name", "", ns)) for a in e.findall("a:author", ns)],
                abstract=ws(e.findtext("a:summary", "", ns)), published=e.findtext("a:published", "", ns)[:10],
                updated=e.findtext("a:updated", "", ns)[:10], version=int(ver.group(1)) if ver else 1,
                comment=ws(e.findtext("x:comment", "", ns)), journal_ref=ws(e.findtext("x:journal_ref", "", ns)),
                doi=e.findtext("x:doi", "", ns), category=cat)

def meta_arxiv_html(aid):
    """export.arxiv.org 被限流（429/503，校园网共用出口 IP 常见）时改抓 arxiv.org/abs 页面：
    citation_* meta 给标题/作者/摘要/v1 日期，Submission history 给版本号，表格给 comment / journal-ref / 主分类。"""
    h = get_text(f"https://arxiv.org/abs/{aid}")
    metas = re.findall(r'<meta name="citation_(\w+)" content="([^"]*)"', h)
    def meta(k): return [html.unescape(v) for n, v in metas if n == k]
    if not meta("title"): raise RuntimeError("arXiv abs 页面没找到 " + aid)
    def cell(cls, label=None):
        pat = (re.escape(label) + r"</td>\s*" if label else "") + r'<td class="tablecell ' + cls + r'[^"]*">(.*?)</td>'
        m = re.search(pat, h, re.S)
        if not m: return ""
        t = re.sub(r'<a href="([^"]+)"[^>]*>this https? URL</a>', r"\1", m.group(1))  # 页面把链接文字换成了 "this https URL"，还原成 URL
        return ws(html.unescape(re.sub(r"<[^>]+>", " ", t)))
    vers = re.findall(r"<strong>(?:<a[^>]*>)?\[v(\d+)\]", h)
    cat = re.search(r'<span class="primary-subject">[^(]*\(([^)]+)\)', h)
    return dict(title=clean_title(meta("title")[0]),
                authors=[split_name(" ".join(reversed(a.split(", ", 1)))) for a in meta("author")],
                abstract=ws(re.sub(r"<[^>]+>", " ", (meta("abstract") or [""])[0])),
                published=(meta("date") or [""])[0].replace("/", "-"), updated=(meta("online_date") or [""])[0].replace("/", "-"),
                version=max(map(int, vers)) if vers else 1, comment=cell("comments"),
                journal_ref=cell("jref", "Journal&nbsp;reference:"), doi=(meta("doi") or [""])[0], category=cat.group(1) if cat else "")

def arxiv_batch(ids):
    """一批 arXiv 号 → {id: dict(ctx=comment+journal_ref, v1, latest)}。先走 API 批量（80 个一批），漏的/被限流的逐条抓 abs 页面。"""
    ns = {"a": "http://www.w3.org/2005/Atom", "x": "http://arxiv.org/schemas/atom"}
    out = {}
    for i in range(0, len(ids), 80):
        chunk = ids[i:i + 80]
        try:
            for e in ET.fromstring(get_text("https://export.arxiv.org/api/query?id_list=" + ",".join(chunk) + f"&max_results={len(chunk)}")).findall("a:entry", ns):
                a = re.search(ARXIV_ID, e.findtext("a:id", "", ns))
                if a: out[a.group(1)] = dict(ctx=ws(e.findtext("x:comment", "", ns)) + " " + ws(e.findtext("x:journal_ref", "", ns)),
                                             v1=e.findtext("a:published", "", ns)[:10], latest=e.findtext("a:updated", "", ns)[:10])
        except (urllib.error.HTTPError, urllib.error.URLError, OSError) as e:
            print(f"  ⚠ arXiv API {getattr(e, 'code', e)}，这批改逐条抓 abs 页面", file=sys.stderr)
    for a in [i for i in ids if i not in out]:
        try:
            m = meta_arxiv_html(a); out[a] = dict(ctx=m["comment"] + " " + m["journal_ref"], v1=m["published"], latest=m["updated"] or m["published"])
            time.sleep(1)
        except Exception: pass
    return out


def meta_arxiv(aid):
    try:
        m = meta_arxiv_api(aid)
    except (urllib.error.HTTPError, urllib.error.URLError) as e:
        print(f"  ⚠ arXiv API {getattr(e, 'code', e)}，改抓 abs 页面", file=sys.stderr)
        m = meta_arxiv_html(aid)
    cat = m["category"]
    m.update(source="arxiv", id=aid, url=f"http://arxiv.org/abs/{aid}", pdf_url=f"https://arxiv.org/pdf/{aid}")
    m["date"], m["date_src"] = m["published"], "arxiv:v1"
    v = venue_from_context(m["comment"] + " " + m["journal_ref"])
    m["venue"], m["venue_src"] = (v, "arxiv-comment") if v else ("arXiv", "default")
    m["item"] = dict(itemType="preprint", title=m["title"], creators=m["authors"], abstractNote=m["abstract"], date=m["published"],
                     url=m["url"], DOI=f"10.48550/arXiv.{aid}", repository="arXiv", archiveID=f"arXiv:{aid}",
                     extra=f"arXiv:{aid} [{cat}]" if cat else f"arXiv:{aid}", libraryCatalog="arXiv.org", language="en", accessDate="CURRENT_TIMESTAMP")
    return m

def cr_date(parts):
    p = (parts or {}).get("date-parts", [[None]])[0]
    if not p or p[0] is None: return ""
    return "-".join(f"{x:02d}" if i else str(x) for i, x in enumerate(p))

def meta_crossref(doi):
    r = json.loads(get_text("https://api.crossref.org/works/" + urllib.parse.quote(doi, safe="")))["message"]
    t = r.get("type", "")
    itype = {"journal-article": "journalArticle", "proceedings-article": "conferencePaper", "book-chapter": "bookSection",
             "posted-content": "preprint", "report": "report"}.get(t, "journalArticle")
    container = (r.get("container-title") or [""])[0]; event = (r.get("event") or {}).get("name", "")
    abstract = ws(re.sub(r"<[^>]+>", " ", html.unescape(r.get("abstract", ""))))
    authors = [{"firstName": a.get("given", ""), "lastName": a.get("family", a.get("name", "")), "creatorType": "author"} for a in r.get("author", [])]
    dates = {k: cr_date(r.get(k)) for k in ("published-online", "published-print", "issued", "created")}
    pub_year = (dates["published-print"] or dates["issued"] or "")[:4]
    m = dict(source="crossref", id=doi, url="https://doi.org/" + doi, title=ws((r.get("title") or [""])[0]), authors=authors, abstract=abstract,
             container=container, event=event, cr_dates=dates, pub_year=pub_year,
             pdf_candidates=[l["URL"] for l in r.get("link", []) if "pdf" in (l.get("content-type") or "") or l.get("content-type") == "unspecified"])
    # 日期：在线发表日 > created(≈出版年) > 能到哪写哪。PDF 首页印的日期在 fetch 拿到 PDF 后再覆盖（优先级更高）
    if len(dates["published-online"]) == 10: m["date"], m["date_src"] = dates["published-online"], "crossref:online"
    elif len(dates["created"]) == 10 and pub_year and abs(int(dates["created"][:4]) - int(pub_year)) <= 1: m["date"], m["date_src"] = dates["created"], "crossref:created(≈出版年)"
    else: m["date"], m["date_src"] = (dates["published-online"] or dates["published-print"] or dates["issued"] or ""), "crossref:不完整 ⚠"
    v = abbr_from_name(container) or abbr_from_name(event)
    m["venue"], m["venue_src"] = (v, "crossref") if v else (container or event or "????", "crossref:全名 ⚠")
    item = dict(itemType=itype, title=m["title"], creators=authors, abstractNote=abstract, date=m["date"], DOI=doi, url=m["url"],
                volume=r.get("volume", ""), issue=r.get("issue", ""), pages=r.get("page", ""), language=r.get("language", ""),
                libraryCatalog="DOI.org (Crossref)", accessDate="CURRENT_TIMESTAMP")
    if itype == "journalArticle": item["publicationTitle"] = container
    elif itype == "conferencePaper": item["proceedingsTitle"] = container; item["conferenceName"] = event
    elif itype == "bookSection": item["bookTitle"] = container
    m["item"] = {k: v for k, v in item.items() if v}
    return m

def meta_page(url):
    """没有 arXiv 号也没有 DOI 的论文页（JMLR / PMLR / ACL Anthology 之类）：只靠 citation_* meta。日期常常只有年，
    拿到 PDF 后 pdf_first_page_date 会再用首页印的 Published 日期覆盖。"""
    page = get_text(url)
    metas = re.findall(r'<meta[^>]+name=["\']citation_(\w+)["\'][^>]+content=["\']([^"\']*)', page, re.I)
    def meta(k, all_=False):
        v = [html.unescape(c) for n, c in metas if n.lower() == k]
        return v if all_ else (v[0] if v else "")
    if not meta("title"): raise RuntimeError("网页里没有 citation_arxiv_id / citation_doi / arXiv 链接 / PDF 链接，也没有 citation_title，认不出是哪篇")
    authors = [split_name(" ".join(reversed(a.split(", ", 1))) if ", " in a else a) for a in meta("author", True)]
    journal, conf = meta("journal_title"), meta("conference_title")
    d = (meta("online_date") or meta("publication_date") or meta("date")).replace("/", "-")
    abstract = meta("abstract")
    if not abstract:
        g = re.search(r'<(p|div|section|blockquote)[^>]+(?:class|id)=["\'][^"\']*abstract[^"\']*["\'][^>]*>(.*?)</\1>', page, re.S | re.I)
        abstract = g.group(2) if g else ""
    m = dict(source="page", id=url, url=url, title=ws(meta("title")), authors=authors, abstract=ws(html.unescape(re.sub(r"<[^>]+>", " ", abstract))),
             container=journal or conf, pub_year=d[:4], pdf_candidates=[meta("pdf_url")] if meta("pdf_url") else [],
             date=d, date_src="page:citation_date" + ("" if len(d) == 10 else " ⚠ 不完整"))
    v = abbr_from_name(journal) or abbr_from_name(conf)
    m["venue"], m["venue_src"] = (v, "page") if v else (journal or conf or "????", "page:全名 ⚠")
    itype = "conferencePaper" if conf and not journal else "journalArticle"
    item = dict(itemType=itype, title=m["title"], creators=authors, abstractNote=m["abstract"], date=d, url=url,
                volume=meta("volume"), issue=meta("issue"), pages=meta("firstpage") + ("-" + meta("lastpage") if meta("lastpage") else ""),
                ISSN=meta("issn"), publisher=meta("publisher"), libraryCatalog=urllib.parse.urlparse(url).netloc, accessDate="CURRENT_TIMESTAMP")
    if itype == "journalArticle": item["publicationTitle"] = journal
    else: item["proceedingsTitle"] = conf; item["conferenceName"] = conf
    m["item"] = {k: v for k, v in item.items() if v}
    return m

def meta_openreview(oid):
    r = json.loads(get_text(f"https://api2.openreview.net/notes?id={oid}"))
    if not r.get("notes"): r = json.loads(get_text(f"https://api.openreview.net/notes?id={oid}"))
    n = r["notes"][0]; c = n["content"]
    val = lambda k: (c.get(k, {}) or {}).get("value", c.get(k)) if isinstance(c.get(k), dict) else c.get(k)
    ts = n.get("pdate") or n.get("cdate") or n.get("tcdate")
    d = time.strftime("%Y-%m-%d", time.gmtime(ts / 1000)) if ts else ""
    venue_txt = (val("venue") or "") + " " + (val("venueid") or "")
    m = dict(source="openreview", id=oid, url=f"https://openreview.net/forum?id={oid}", title=ws(val("title")),
             authors=[split_name(a) for a in (val("authors") or [])], abstract=ws(val("abstract")), venue_txt=venue_txt,
             pdf_url=f"https://openreview.net/pdf?id={oid}", date=d, date_src="openreview:pdate ⚠" if n.get("pdate") else "openreview:cdate ⚠")
    v = abbr_from_name(venue_txt)
    m["venue"], m["venue_src"] = (v, "openreview") if v else (ws(val("venue")) or "????", "openreview:全名 ⚠")
    m["item"] = dict(itemType="conferencePaper", title=m["title"], creators=m["authors"], abstractNote=m["abstract"], date=d,
                     proceedingsTitle=ws(val("venue")) or "", url=m["url"], libraryCatalog="OpenReview.net", accessDate="CURRENT_TIMESTAMP")
    return m

def arxiv_by_title(title):
    """按标题在 arXiv 搜（短语查询要保留连字符、去掉非 ASCII），规范化后完全一致才算命中；返回 arXiv 号或 None。"""
    def clean(t): return ws(re.sub(r"[^A-Za-z0-9\- ]+", " ", t))
    ascii_chunks = [clean(c) for c in re.split(r"[^\x00-\x7f]+", title)]
    cands = [clean(title), clean(title.split(":", 1)[1]) if ":" in title else "", max(ascii_chunks, key=len)]
    ns = {"a": "http://www.w3.org/2005/Atom"}; want = norm_title(clean_title(title))
    for q in dict.fromkeys(c for c in cands if len(c) > 15):
        try:
            xml = get_text("https://export.arxiv.org/api/query?search_query=" + urllib.parse.quote(f'ti:"{q}"') + "&max_results=5")
            for e in ET.fromstring(xml).findall("a:entry", ns):
                got = norm_title(clean_title(e.findtext("a:title", "", ns)))
                if got == want or (len(q) > 30 and got.endswith(norm_title(q))):
                    return re.search(ARXIV_ID, e.findtext("a:id", "", ns)).group(1)
        except Exception: pass
    return None

def ids_from_pdf_text(text):
    head = text.split("\f")[0]                                            # 整个首页：pypdf 把 arXiv 侧边水印排在页末，不能只看前 4000 字
    m = re.search(r"arXiv:" + ARXIV_ID + r"\s*\[", head)
    if m: return "arxiv", m.group(1)
    m = re.search(r"\b(10\.\d{4,9}/[^\s\"<>]+)", head[:6000])
    if m: return "doi", re.sub(r"\(0123456789.*$", "", m.group(1)).rstrip(".,;)")   # pypdf 会把 Springer 的隐形水印 (0123456789().,-volV) 粘到 DOI 后面
    lines = [l.strip() for l in text[:3000].splitlines() if len(l.strip()) > 15]     # 没有 arXiv 戳/DOI：拿前几行当标题去 arXiv 搜
    for i in range(min(3, len(lines))):
        for cand in (lines[i], " ".join(lines[i:i + 2])):
            aid = arxiv_by_title(cand)
            if aid: return "arxiv", aid
    return None, None

def ids_from_page(url):
    try: page = get_text(url)
    except Exception as e: raise RuntimeError(f"网页取不到: {e}")
    def meta(name):
        m = re.search(r'<meta[^>]+name=["\']' + name + r'["\'][^>]+content=["\']([^"\']+)', page, re.I) or \
            re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']' + name + r'["\']', page, re.I)
        return html.unescape(m.group(1)) if m else None
    if meta("citation_arxiv_id"): return "arxiv", meta("citation_arxiv_id"), None
    if meta("citation_doi"): return "doi", meta("citation_doi"), meta("citation_pdf_url")
    m = re.search(r"arxiv\.org/(?:abs|pdf)/" + ARXIV_ID, page)
    if m: return "arxiv", m.group(1), None
    m = re.search(r"doi\.org/(10\.\d{4,9}/[^\s\"'<>]+)", page)
    if m: return "doi", m.group(1), meta("citation_pdf_url")
    m = re.search(r'href=["\']([^"\']+\.pdf(?:\?[^"\']*)?)["\']', page, re.I)          # 项目页常见 "Paper (PDF)"
    if m: return "pdf", urllib.parse.urljoin(url, html.unescape(m.group(1))), None
    return None, None, meta("citation_pdf_url")
