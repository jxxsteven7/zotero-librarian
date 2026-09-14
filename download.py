#!/usr/bin/env python3
"""把论文链接收进 Zotero（供 /download skill 调用）。

  python3 download.py fetch <link>...       解析元数据、下载 PDF 到 inbox/、抽文本、查重、算标题；不动库
  python3 download.py show <slug>           重新打印某条的摘要卡片
  python3 download.py save <slug> --collection "Dex-Manipulation" --tags method:vla,embod:gripper[,...]
                       [--also "AI Foundation"] [--venue CoRL] [--date 2025-0102] [--name "原名"] [--url 项目页] [--short 短名] [--force]
                                            经 Zotero 桌面端 connector 接口入库：建条目 → 进分类+贴标签 → 送 PDF
  python3 download.py collect <itemKey> <collection>   事后经 Web API 追加第二个分类（save --also 同步没等到时用）
  python3 download.py list                  列出 inbox 里还没入库的
  python3 download.py recheck [--dates] [--search] [--write] [--only K1,K2]
                                            复核库里的 arXiv 条目：[arXiv] 标题查中稿（arXiv comment / PDF 首页声明 / Semantic Scholar /
                                            Crossref / 项目页）；--dates 再核对标题日期是否 v1 提交日。默认只列表，--write 才经 Web API 改标题

链接支持：arXiv（abs/pdf/html/裸 id/alphaxiv/hf papers）、DOI（doi.org 或裸 DOI）、OpenReview、直接 PDF 链接、本地 PDF 路径、带 citation_* meta 的网页。
付费期刊的 PDF 抓不到时条目照建（没附件），用户可事后把 PDF 拖进 Zotero，或把下好的 PDF 路径给 fetch。
PDF 不走 Web API 上传：本机附件同步是 WebDAV，Web API 传的文件客户端拿不到；connector 让 Zotero 自己存、自己同步。
"""
import hashlib, html, json, os, re, shutil, sqlite3, subprocess, sys, time, urllib.error, urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from venues import abbr_from_name, venue_from_context, venue_from_pdf
import apply as zapi                      # Web API 封装（req），只在 collect / --also 时用

INBOX = os.path.join(HERE, "inbox")                      # 下载暂存区，入库后清空；不进 git
from config import connect_ro, STORAGE, PDFTOTEXT, PDFTOTEXT_INSTALL
CONNECTOR = "http://127.0.0.1:23119"
LOG = os.path.join(HERE, "zotero-organize.log.md")
UA_WEB = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
UA_LOCAL = "zotero-claude/1.0"            # 不能以 Mozilla/ 开头，否则 connector 当成浏览器请求拒掉
COLLECTIONS = ("Evolution Algorithm", "Dex-Manipulation", "Humanoid", "AI Foundation")
VOCAB = {  # 与 CLAUDE.md §3 一致；词表外的值只警告不拦（用户可能已批准新值）
 "method": {"vla", "policy-learning", "rl", "world-model", "foundation-model", "teleop", "grasp-synthesis"},
 "embod": {"dex-hand", "gripper", "single-arm", "bimanual", "humanoid"},
 "tech": {"action-chunking", "flow-matching", "diffusion", "transformer", "hil", "latent-cot"},
 "base": {"pi0", "pi0.5", "pi0.6", "gr00t"},
 "modality": {"vision", "language", "tactile", "depth", "point-cloud", "audio"},
 "type": {"survey", "benchmark", "dataset"},
 "status": {"to-read-first", "to-read", "skimmed", "read", "to-present", "presented", "to-reproduce", "reproducing", "reproduced"},
}


# ---------- HTTP ----------
def http(url, headers=None, data=None, method=None, timeout=60, ua=UA_WEB):
    hdr = {"User-Agent": ua}; hdr.update(headers or {})
    r = urllib.request.urlopen(urllib.request.Request(url, data=data, headers=hdr, method=method), timeout=timeout)
    return r.status, r.headers, r.read()


def get_text(url, **kw):
    st, h, b = http(url, **kw)
    return b.decode(h.get_content_charset() or "utf-8", "replace")


def connector(path, body=None, headers=None):
    hdr = {"X-Zotero-Connector-API-Version": "3"}; hdr.update(headers or {})
    data = body if isinstance(body, (bytes, bytearray)) else json.dumps(body).encode()
    if not isinstance(body, (bytes, bytearray)): hdr["Content-Type"] = "application/json"
    try:
        st, h, b = http(CONNECTOR + path, headers=hdr, data=data, method="POST", ua=UA_LOCAL, timeout=300)
        return st, b.decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


# ---------- 链接识别 ----------
ARXIV_ID = r"(\d{4}\.\d{4,5}|[a-z\-]+(?:\.[A-Z]{2})?/\d{7})(v\d+)?"

def classify(link):
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


# ---------- 元数据源 ----------
def split_name(full):
    parts = full.strip().split()
    if len(parts) == 1: return {"firstName": "", "lastName": parts[0], "creatorType": "author"}
    return {"firstName": " ".join(parts[:-1]), "lastName": parts[-1], "creatorType": "author"}


def ws(s): return re.sub(r"\s+", " ", (s or "")).strip()


def clean_title(t):
    """去掉 arXiv 标题里的 LaTeX：$π_0$ -> π0，$\\pi_0$ 保留字母部分。"""
    return ws(re.sub(r"\$([^$]*)\$", lambda m: re.sub(r"[_^{}$\\]", "", m.group(1)), t or ""))


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


# ---------- PDF ----------
def download_pdf(url, dest):
    try:
        st, h, b = http(url, headers={"Accept": "application/pdf,*/*"}, timeout=120)
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"
    if not b.startswith(b"%PDF"): return False, f"不是 PDF（content-type={h.get('Content-Type')}）"
    open(dest, "wb").write(b); return True, url


_PDF_WARNED = False
def pdf_text(pdf, txt=None, first_pages=None):
    """PDF → 文本（页间 \f 分隔，和 pdftotext 一样）。首选 pdftotext（config 里三平台查找），没有就退到 pypdf；都没有返回 ""。
    txt 给了就同时写到那个文件（inbox/<slug>.txt，供 grep）。"""
    global _PDF_WARNED
    text = ""
    if PDFTOTEXT:
        cmd = [PDFTOTEXT] + (["-l", str(first_pages)] if first_pages else []) + [pdf, "-"]
        try: text = subprocess.run(cmd, check=False, capture_output=True).stdout.decode("utf-8", "replace")   # pdftotext 输出 UTF-8，不能用 text=True（Windows 会按 GBK 解）
        except OSError as e: print(f"  ⚠ pdftotext 跑不起来（{e}）")
    if not text:
        try:
            import pypdf
            r = pypdf.PdfReader(pdf)
            text = "\f".join((pg.extract_text() or "") for pg in (r.pages[:first_pages] if first_pages else r.pages))
        except ImportError:
            if not PDFTOTEXT and not _PDF_WARNED:
                _PDF_WARNED = True; print(f"  ⚠ 没有 pdftotext 也没有 pypdf，抽不了正文（首页出版声明 / 项目页链接 / 关键词 grep 都会缺）。装一个：{PDFTOTEXT_INSTALL}")
        except Exception as e: print(f"  ⚠ pypdf 解析失败：{e}")
    if txt and text:
        with open(txt, "w", encoding="utf-8") as f: f.write(text)
    return text


MONTH_NUM = {m: i + 1 for i, m in enumerate("january february march april may june july august september october november december".split())}
MONTH_NUM.update({m[:3]: n for m, n in list(MONTH_NUM.items())}); MONTH_NUM["sept"] = 9
MONTHS = "|".join(sorted(MONTH_NUM, key=len, reverse=True))
def pdf_first_page_date(text, pub_year):
    """期刊 PDF 首页印的上线日/出版日；必须与出版年相差 ≤1，否则当噪音。返回 (YYYY-MM-DD, 标签) 或 None。"""
    head = text[:6000].lower()
    lead = r"(?:available online|published online|date of publication|published):?\s*"
    for rx, order in ((lead + r"(\d{1,2})\s+(" + MONTHS + r")\.?,?\s+(\d{4})", "dmy"),
                      (lead + r"(" + MONTHS + r")\.?\s+(\d{1,2}),?\s+(\d{4})", "mdy")):
        m = re.search(rx, head)
        if not m: continue
        d, mon, y = (m.group(1), m.group(2), m.group(3)) if order == "dmy" else (m.group(2), m.group(1), m.group(3))
        if pub_year and abs(int(y) - int(pub_year)) > 1: continue
        return f"{y}-{MONTH_NUM[mon]:02d}-{int(d):02d}", "pdf:online"
    return None


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


# ---------- 查重 ----------
def norm_title(t):
    t = re.sub(r"^(\s*\[[^\]]*\]\s*)+", "", t or "")            # 去掉 [date] [venue] 前缀
    return re.sub(r"[^a-z0-9]+", "", t.lower())


_LIB = None
def find_duplicate(m):
    global _LIB
    if _LIB is None:
        subprocess.run([sys.executable, os.path.join(HERE, "dump_zotero.py")], capture_output=True)
        _LIB = json.load(open(os.path.join(HERE, "library_dump.json"), encoding="utf-8"))
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


# ---------- 标题 ----------
def fmt_date(d):
    """YYYY-MM-DD -> YYYY-MMDD；不完整的能到哪写哪。"""
    d = (d or "").strip()
    if len(d) >= 10: return d[:4] + "-" + d[5:7] + d[8:10]
    if len(d) >= 7: return d[:7]
    return d[:4] or "????"


def s2_venues(arxiv_ids):
    """Semantic Scholar 批量查发表刊/会：{arXiv id: (缩写或None, 证据)}。只认 type=conference 或非 arXiv DOI 的记录
    （S2 会把 cs.RO 预印本挂到一个叫 "Robotics" 的假期刊上，DOI 仍是 arXiv 的，那种不算）。无 key 时常 429，退避重试。"""
    out = {}
    ids = [a for a in dict.fromkeys(arxiv_ids) if a]
    for i in range(0, len(ids), 200):
        chunk = ids[i:i + 200]; body = json.dumps({"ids": ["arXiv:" + a for a in chunk]}).encode()
        for attempt in range(6):
            try:
                st, h, raw = http("https://api.semanticscholar.org/graph/v1/paper/batch?fields=title,venue,publicationVenue,externalIds,year",
                                  data=body, headers={"Content-Type": "application/json"}, method="POST", ua=UA_LOCAL)
                js = json.loads(raw.decode()); break
            except urllib.error.HTTPError as e:
                if e.code != 429 or attempt == 5: raise
                time.sleep(4 * (attempt + 1))
        for a, pp in zip(chunk, js):
            if not pp: continue
            pv = pp.get("publicationVenue") or {}; name = pv.get("name") or pp.get("venue") or ""
            doi = ((pp.get("externalIds") or {}).get("DOI") or "")
            real_doi = doi and not doi.lower().startswith("10.48550/")
            if pv.get("type") == "conference" or real_doi:
                out[a] = (abbr_from_name(name), f"S2: {name}" + (f" doi:{doi}" if real_doi else ""))
    return out


def crossref_by_title(title):
    """Crossref 按标题找已发表版本（IEEE 会议/期刊有 DOI 的才找得到）：(缩写或None, 证据) 或 (None, None)。"""
    try:
        q = urllib.parse.quote(re.sub(r"[^\w\s-]", " ", title)[:200])
        js = json.loads(get_text(f"https://api.crossref.org/works?query.bibliographic={q}&rows=3&select=DOI,title,container-title,event,type", ua=UA_LOCAL))
    except Exception: return None, None
    for it in js.get("message", {}).get("items", []):
        if it.get("DOI", "").lower().startswith("10.48550/"): continue
        if norm_title((it.get("title") or [""])[0]) != norm_title(title): continue
        name = (it.get("container-title") or [""])[0] or (it.get("event") or {}).get("name", "")
        return abbr_from_name(name), f"Crossref: {name} doi:{it['DOI']}"
    return None, None


URL_RE = re.compile(r"https?://[^\s<>\"')\]]+|(?<![\w/.])[\w.-]+\.github\.io(?:/[^\s<>\"')\]]*)?")   # 也认 PDF 里裸写的 xxx.github.io
NOT_PROJECT_HOSTS = ("arxiv.org", "doi.org", "openreview.net", "semanticscholar.org", "youtube.com", "youtu.be", "creativecommons.org",
                     "huggingface.co/papers", "orcid.org", "ieee.org", "acm.org", "overleaf.com", "developer.nvidia.com", "wikipedia.org",
                     "pytorch.org", "tensorflow.org", "python.org", "mujoco.org", "isaac-sim", "shadowrobot.com", "wonikrobotics.com",
                     "unitree.com", "franka.de", "gelsight.com", "intelrealsense.com", "ufactory.cc", "robotis.com", "science.org", "springer.com",
                     "sciencedirect.com", "nature.com", "roboticsproceedings.org", "proceedings.mlr.press", "neurips.cc", "openaccess.thecvf.com",
                     "crossref.org", "crossmark", "dl.acm.org", "ieeexplore", "scholar.google", "researchgate.net", "linkedin.com", "twitter.com", "x.com/")


def _project_score(u):
    """排序：项目页（github.io / 机构博客）> 代码仓库 > 其他；文件直链垫底。"""
    ul = u.lower(); s = 0
    if re.search(r"github\.io|pages\.dev|netlify\.app|vercel\.app|sites\.google\.com/view/", ul): s += 5
    if re.search(r"(physicalintelligence|pi\.website|research\.nvidia|deepmind|openai\.com/(?:index|research)|csail\.mit\.edu)", ul): s += 4
    if re.search(r"github\.com/[^/]+/[^/]+/?$", ul): s += 2
    if re.search(r"\.(pdf|mp4|png|jpg|zip)$", ul): s -= 5
    return s


def project_urls(m, text=None, pdf=None):
    """论文的项目页 / 代码页候选：arXiv comment、摘要、PDF 首页正文里的链接，以及 PDF 里超链接注释的真实目标（/URI，
    pdftotext 会把长链接截断，注释里是完整的）。去掉 arXiv/DOI/出版社/厂商站，按"像项目页"排序，最多 3 个。"""
    blob = " ".join(x for x in (m.get("comment"), m.get("abstract"), (text or "").split("\f")[0]) if x)
    ctx = {}                                                         # 链接前面 120 字有 "project page / website / videos and code" 之类 → 加分
    cands = []
    for g in URL_RE.finditer(blob):
        u = g.group(0).rstrip(".,;:)"); cands.append(u)
        if re.search(r"project (?:page|website|site)|website|webpage|videos?(?: and code)?|code and videos|homepage|available at", blob[max(0, g.start() - 120):g.start()], re.I):
            ctx[u] = 3
    if pdf and os.path.exists(pdf):
        try:
            raw = open(pdf, "rb").read(3_000_000)
            cands += [x.decode("latin-1").rstrip(".,;:)") for x in re.findall(rb"/URI\s*\((https?://[^)]{6,200})\)", raw)]
        except OSError: pass
    out = {}
    for u in cands:
        full = u if u.startswith("http") else "https://" + u
        if any(h in full.lower() for h in NOT_PROJECT_HOSTS) or full.rstrip("/") in out: continue
        out[full.rstrip("/")] = (_project_score(full) + ctx.get(u, 0), full)
    return [full for _, (sc, full) in sorted(out.items(), key=lambda kv: kv[1][0], reverse=True)][:3]


def project_url_score(u, text=None):
    """给 fetch 用：候选是否够格自动当 URL 字段（github.io 之类，或正文里点名 "project page/website" 的）。"""
    return _project_score(u) > 0 or bool(text and re.search(r"(?:project (?:page|website|site)|website|webpage|videos?|homepage|available at)[\s\S]{0,120}" + re.escape(u.replace("https://", "").rstrip("/")), text.split("\f")[0], re.I))


def venue_from_page(url):
    """抓项目页/README，找 "Accepted to CoRL 2026" 这类声明 → (缩写, 证据) ；写着 under review / anonymous 返回 (None, 说明)。"""
    try: page = get_text(url, timeout=30)
    except Exception: return None, None
    txt = re.sub(r"<!--.*?-->", " ", page, flags=re.S)                  # 注释里常留着模板的 "Anonymous Author(s)"，不算
    txt = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", " ", txt, flags=re.S | re.I)
    txt = ws(html.unescape(re.sub(r"<[^>]+>", " ", txt)))
    if re.search(r"anonymous submission|under review", txt, re.I): return None, f"{url} 写着 under review / anonymous"
    head = txt[:800]                                                    # 页头徽章：直接写 "CoRL 2025"
    v = venue_from_context(head)
    if v and re.search(r"(corl|rss|icra|iros|iclr|icml|neurips|cvpr|iccv|eccv|aaai|aistats)\W{0,3}20\d\d", head, re.I):
        return v, f"{url} 页头: " + re.search(r".{0,50}(corl|rss|icra|iros|iclr|icml|neurips|cvpr|iccv|eccv|aaai|aistats)\W{0,3}20\d\d.{0,30}", head, re.I).group(0)
    for s in re.split(r"(?<=[.!。])\s+", txt):
        if len(s) > 300 or not re.search(r"accept|to appear|publish|presented at|\boral\b|spotlight|proceedings", s, re.I): continue
        v = venue_from_context(s)
        if v: return v, f"{url}: {s[:120]}"
    return None, None


def lookup_published(m, text=None, s2=None):
    """arXiv 预印本查有没有中稿：arXiv comment → PDF 首页声明 → Semantic Scholar → Crossref → 项目页。回填 m['venue'] / m['venue_src']。"""
    if m.get("venue_src") != "default": return
    v, ev = venue_from_pdf(text) if text else (None, None)
    if v: m["venue"], m["venue_src"] = v, f"pdf: {ev}"; return
    s2 = s2 if s2 is not None else s2_venues([m["id"]])
    notes = []
    if m["id"] in s2:
        ab, ev = s2[m["id"]]
        if ab: m["venue"], m["venue_src"] = ab, ev; return
        notes.append(f"S2 说是 {ev}，缩写表里没有 ⚠")
    ab, ev = crossref_by_title(m["title"])
    if ab: m["venue"], m["venue_src"] = ab, ev; return
    if ev: notes.append(f"{ev}，缩写表里没有 ⚠")
    for u in project_urls(m, text):
        ab, ev = venue_from_page(u)
        if ab: m["venue"], m["venue_src"] = ab, "project page " + ev; return
        if ev: notes.append(ev)
    if notes: m["venue_src"] = "default（" + "；".join(notes) + "）"


def short_title(name):
    """Zotero 的 Short Title 字段 = 论文短名，Notero 拿它当 Notion 页面标题（CLAUDE.md §4）：用户昵称 [ALOHA/ACT] > 冒号前的名字 > 原名。"""
    name = re.sub(r"^(\s*\[[^\]]*\]\s*){2}", "", name or "").strip()          # 去掉 [日期] [刊/会]
    g = re.match(r"^\[([^\]]+)\]\s*", name)
    if g: return g.group(1)
    head = name.split(":")[0].strip()
    if ":" in name and 2 <= len(head) <= 40: return head
    return re.sub(r"\s*[✅❗]+$", "", name)


def make_title(m, name=None, venue=None, date_=None):
    return f"[{date_ or fmt_date(m.get('date'))}] [{venue or m.get('venue') or '????'}] {name or m['title']}".strip()


# ---------- fetch ----------
def fetch_one(link):
    os.makedirs(INBOX, exist_ok=True)
    kind, ident = classify(link); pdf_hint = None; pre_pdf = None
    if kind in ("pdf", "file"):                                    # 先拿到 PDF，从首页找 arXiv 号 / DOI
        tmp = os.path.join(INBOX, hashlib.sha1(ident.encode()).hexdigest()[:10] + ".pdf")
        if kind == "file": shutil.copy(ident, tmp); ok, why = True, ident
        else: ok, why = download_pdf(ident, tmp)
        if not ok: raise RuntimeError(f"PDF 下不下来: {why}")
        kind, ident = ids_from_pdf_text(pdf_text(tmp, tmp[:-4] + ".txt", first_pages=2))
        if os.path.exists(tmp[:-4] + ".txt"): os.remove(tmp[:-4] + ".txt")
        if not kind: raise RuntimeError(f"PDF 首页找不到 arXiv 号或 DOI，没法拿元数据（文件留在 {tmp}）")
        pre_pdf = tmp
    elif kind == "page":
        kind, ident, pdf_hint = ids_from_page(ident)
        if not kind: raise RuntimeError("网页里没有 citation_arxiv_id / citation_doi / arXiv 链接 / PDF 链接，认不出是哪篇")
        if kind == "pdf":                                              # 页面只给了 PDF：下下来从首页认 arXiv 号 / DOI
            tmp = os.path.join(INBOX, hashlib.sha1(ident.encode()).hexdigest()[:10] + ".pdf")
            ok, why = download_pdf(ident, tmp)
            if not ok: raise RuntimeError(f"页面上的 PDF 下不下来: {why}")
            src = ident; kind, ident = ids_from_pdf_text(pdf_text(tmp, tmp[:-4] + ".txt", first_pages=2))
            if os.path.exists(tmp[:-4] + ".txt"): os.remove(tmp[:-4] + ".txt")
            if not kind: raise RuntimeError(f"页面 PDF 首页找不到 arXiv 号或 DOI（文件留在 {tmp}）")
            pre_pdf = tmp
    if kind == "openreview":                                       # API 常被人机验证挡住 → 退到 PDF 路线
        try: m = meta_openreview(ident)
        except Exception as e:
            tmp = os.path.join(INBOX, ident + ".pdf"); ok, why = download_pdf(f"https://openreview.net/pdf?id={ident}", tmp)
            if not ok: raise RuntimeError(f"OpenReview API 拒了（{str(e)[:80]}），PDF 也下不了（{why}）；给 arXiv 链接吧")
            kind, ident2 = ids_from_pdf_text(pdf_text(tmp, tmp[:-4] + ".txt", first_pages=2))
            if os.path.exists(tmp[:-4] + ".txt"): os.remove(tmp[:-4] + ".txt")
            if not kind: raise RuntimeError(f"OpenReview API 拒了，PDF 首页也认不出 arXiv 号/DOI（文件留在 {tmp}）；给 arXiv 链接吧")
            pre_pdf, ident = tmp, ident2
    if kind != "openreview": m = {"arxiv": meta_arxiv, "doi": meta_crossref}[kind](ident)
    m["link"] = link; m["slug"] = slug_of(kind, ident)
    pdf = os.path.join(INBOX, m["slug"] + ".pdf"); txt = os.path.join(INBOX, m["slug"] + ".txt")
    if pre_pdf: shutil.move(pre_pdf, pdf); m["pdf_src"] = link
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
        if m["source"] == "crossref":                                    # PDF 首页印的上线日优先级高于 Crossref
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


# ---------- save ----------
def local_collection_id(name):
    c = connect_ro()
    r = c.execute("select collectionID from collections where libraryID=1 and collectionName=?", (name,)).fetchone()
    if not r: raise RuntimeError(f"本地没有分类 {name!r}（只允许 {COLLECTIONS}）")
    return r[0]


def local_item_by_title(title):
    c = connect_ro()
    r = c.execute("""select i.itemID, i.key, i.dateAdded from items i join itemData d on d.itemID=i.itemID join fields f on f.fieldID=d.fieldID
                     join itemDataValues v on v.valueID=d.valueID where f.fieldName='title' and v.value=? and i.itemID not in (select itemID from deletedItems)
                     order by i.dateAdded desc limit 1""", (title,)).fetchone()
    if not r: return None
    att = c.execute("""select a.path, ai.key from itemAttachments a join items ai on ai.itemID=a.itemID where a.parentItemID=?""", (r[0],)).fetchall()
    tags = [t[0] for t in c.execute("select t.name from itemTags it join tags t on t.tagID=it.tagID where it.itemID=?", (r[0],)).fetchall()]
    colls = [t[0] for t in c.execute("select c.collectionName from collectionItems ci join collections c on c.collectionID=ci.collectionID where ci.itemID=?", (r[0],)).fetchall()]
    files = [os.path.join(STORAGE, k, p.split("storage:", 1)[1]) for p, k in att if p and p.startswith("storage:")]
    return dict(itemID=r[0], key=r[1], dateAdded=r[2], tags=tags, collections=colls, files=files)


KEEP_BARE_TAGS = {"notion"}   # notion = Notero 插件自动打的，不算词表外（用户手打的 Dex-Hand 已于 2026-09-12 删除）
def check_tags(tags):
    for t in tags:
        if t in KEEP_BARE_TAGS: continue
        m = re.fullmatch(r"([a-z]+):([a-z0-9.\-]+)", t)
        if not m: print(f"  ⚠ 标签 {t!r} 不是 family:value 形式（照写，但请确认）"); continue
        if m.group(1) not in VOCAB: print(f"  ⚠ 标签家族 {m.group(1)!r} 不在词表")
        elif m.group(2) not in VOCAB[m.group(1)]: print(f"  ⚠ {t!r} 不在 CLAUDE.md 词表里（用户批准过才用）")


def save(slug, collection, tags, also=None, venue=None, date_=None, name=None, force=False, url=None, short=None):
    p = os.path.join(INBOX, slug + ".json")
    if not os.path.exists(p): raise RuntimeError(f"inbox 里没有 {slug}，先 fetch")
    m = json.load(open(p, encoding="utf-8"))
    if m.get("duplicate") and not force: raise RuntimeError(f"库里已有 {m['duplicate']['key']} | {m['duplicate']['title']}；确认要加就 --force")
    if collection not in COLLECTIONS or (also and also not in COLLECTIONS): raise RuntimeError(f"分类只能是 {COLLECTIONS}")
    tags = [t.strip() for t in tags if t.strip()]
    if not any(t.startswith("status:") for t in tags): tags.append("status:to-read")
    check_tags(tags)
    title = make_title(m, name=name, venue=venue, date_=date_)
    item = dict(m["item"], id=slug, title=title, shortTitle=short or short_title(title))
    item["url"] = url or m.get("project_url") or m["item"].get("url") or ""      # URL 字段 = 项目页优先（Notion 那边显示的就是它）
    pdf = os.path.join(INBOX, slug + ".pdf")
    if urllib.request.urlopen(urllib.request.Request(CONNECTOR + "/connector/ping", headers={"User-Agent": UA_LOCAL}), timeout=5).status != 200:
        raise RuntimeError("Zotero 桌面端没在跑（connector 23119 不通）")
    sid = hashlib.sha1(f"{slug}{time.time()}".encode()).hexdigest()[:8]
    st, body = connector("/connector/saveItems", {"sessionID": sid, "uri": m["url"], "items": [item]})
    if st != 201: raise RuntimeError(f"saveItems 失败 {st}: {body[:300]}")
    st, body = connector("/connector/updateSession", {"sessionID": sid, "target": f"C{local_collection_id(collection)}", "tags": tags})
    if st != 200: raise RuntimeError(f"updateSession 失败 {st}: {body[:300]}（条目已建，标签/分类没落）")
    pdf_ok = False
    if os.path.exists(pdf):
        meta = json.dumps({"sessionID": sid, "parentItemID": slug, "title": "Full Text PDF", "url": m.get("pdf_src") or m["url"]})
        st, body = connector("/connector/saveAttachment?sessionID=" + sid, open(pdf, "rb").read(), headers={"X-Metadata": meta, "Content-Type": "application/pdf"})
        pdf_ok = st == 201
        if not pdf_ok: print(f"  ⚠ saveAttachment 失败 {st}: {body[:300]}")
    time.sleep(1)
    got = local_item_by_title(title)
    if not got: raise RuntimeError("connector 回了 201 但本地库里查不到这个标题，去 Zotero 里看看")
    missing = [f for f in got["files"] if not os.path.exists(f)]
    print(f"入库 {got['key']} | {title}\n  分类: {got['collections']}\n  标签: {sorted(got['tags'])}\n  PDF : {got['files'] or '无'}" + (f"  ⚠ 文件缺失 {missing}" if missing else ""))
    extra = ""
    if also:
        try: extra = " | +collection(web api): " + also + " " + add_collection(got["key"], also)
        except Exception as e: extra = f" | ⚠ 第二分类 {also} 没加上（{e}），稍后 python3 download.py collect {got['key']} \"{also}\""
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"\n## {date.today()} — download\n- {got['key']} | {title} | +collection: {collection}{extra} | +tags: {', '.join(tags)} | pdf: {'ok' if pdf_ok else 'missing'} | src: {m.get('link')}\n")
    for ext in (".json", ".txt", ".pdf"):                       # 入库后 inbox 里的三个文件都删：PDF Zotero 已存了自己的一份，json/txt 只在定标签时有用
        if os.path.exists(os.path.join(INBOX, slug + ext)): os.remove(os.path.join(INBOX, slug + ext))
    print(extra.strip(" |") if extra else "")
    return got


def add_collection(key, name, wait=180):
    """经 Web API 给条目追加一个分类（超集写法）；条目要先被客户端同步上去，最多等 wait 秒。"""
    env = zapi.load_env()
    st, h, colls = zapi.req(env, "GET", "/collections", params="?limit=100")
    ck = {c["data"]["name"]: c["key"] for c in colls}
    if name not in ck: raise RuntimeError(f"远端没有分类 {name!r}")
    t0 = time.time()
    while True:
        st, h, it = zapi.req(env, "GET", f"/items/{key}")
        if st == 200: break
        if time.time() - t0 > wait: raise RuntimeError("等了 %ds 条目还没同步到远端" % wait)
        time.sleep(10)
    cur = it["data"]["collections"]
    if ck[name] in cur: return "(已在)"
    st, h, body = zapi.req(env, "PATCH", f"/items/{key}", {"collections": cur + [ck[name]], "version": it["version"]})   # 乐观锁
    if st not in (200, 204): raise RuntimeError(f"PATCH {st}: {body}")
    return "ok"


# ---------- recheck：库里的 arXiv 条目复核标题 ----------
def recheck(write=False, only=None, dates=False, search=False):
    """[arXiv] 标题查中稿（arXiv comment → PDF 首页声明 → Semantic Scholar → Crossref → 项目页）；--dates 再核对日期是否 v1 提交日；
    --search 对没有 arXiv 链接/水印的条目按标题去 arXiv 搜预印本（期刊/会议论文若有更早的预印本，日期用预印本 v1；每条 3 秒）。
    先跑 dump_zotero.py。默认只列表；--write 才经 Web API 改标题（approval mode：先给用户看表）。"""
    from config import DATA_DIR
    items = json.load(open(os.path.join(HERE, "library_dump.json"), encoding="utf-8"))
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
    ax = {}                                                             # arXiv API 一次批量：comment/journal_ref + v1 日期
    ns = {"a": "http://www.w3.org/2005/Atom", "x": "http://arxiv.org/schemas/atom"}
    for i in range(0, len(ids), 80):
        chunk = ids[i:i + 80]
        for e in ET.fromstring(get_text("https://export.arxiv.org/api/query?id_list=" + ",".join(chunk) + f"&max_results={len(chunk)}")).findall("a:entry", ns):
            a = re.search(ARXIV_ID, e.findtext("a:id", "", ns))
            if a: ax[a.group(1)] = dict(ctx=ws(e.findtext("x:comment", "", ns)) + " " + ws(e.findtext("x:journal_ref", "", ns)),
                                        v1=e.findtext("a:published", "", ns)[:10], latest=e.findtext("a:updated", "", ns)[:10])
    for a in [i for i in ids if i not in ax]:                              # 批量查偶尔漏条目，单个补一次
        try:
            e = ET.fromstring(get_text(f"https://export.arxiv.org/api/query?id_list={a}")).find("a:entry", ns)
            if e is not None and e.findtext("a:published", "", ns):
                ax[a] = dict(ctx=ws(e.findtext("x:comment", "", ns)) + " " + ws(e.findtext("x:journal_ref", "", ns)),
                             v1=e.findtext("a:published", "", ns)[:10], latest=e.findtext("a:updated", "", ns)[:10])
        except Exception: pass
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
    env = zapi.load_env(); done = []
    for key, old, new, why in hits:
        st, h, it = zapi.req(env, "GET", f"/items/{key}")
        if st != 200: print(f"  ✗ {key} GET {st}"); continue
        if it["data"]["title"] != old: print(f"  ✗ {key} 远端标题和 dump 不一致，跳过: {it['data']['title'][:60]}"); continue
        st, h, body = zapi.req(env, "PATCH", f"/items/{key}", {"title": new, "version": it["version"]})
        print(f"  {'ok' if st in (200, 204) else '✗ ' + str(st)} {key} {old[:40]!r} -> {new[:60]!r}")
        if st in (200, 204): done.append((key, old, new, why))
    if done:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(f"\n## {date.today()} — recheck（arXiv 条目标题复核）\n### Applied\n")
            for key, old, new, why in done: f.write(f"- {key} | {old[:60]} -> {new[:70]} | {why[:110]}\n")


# ---------- main ----------
def main(argv):
    if not argv or argv[0] in ("-h", "--help"): print(__doc__); return
    cmd, args = argv[0], argv[1:]
    if cmd == "fetch":
        for link in args:
            try: card(fetch_one(link))
            except Exception as e: print(f"=== {link}\n  ✗ {e}\n")
    elif cmd == "show":
        card(json.load(open(os.path.join(INBOX, args[0] + ".json"), encoding="utf-8")))
    elif cmd == "list":
        for f in sorted(os.listdir(INBOX)) if os.path.isdir(INBOX) else []:
            if f.endswith(".json"): m = json.load(open(os.path.join(INBOX, f), encoding="utf-8")); print(f"{m['slug']:<28} {m['proposed_title'][:90]}")
    elif cmd == "save":
        import argparse
        ap = argparse.ArgumentParser(prog="download.py save"); ap.add_argument("slug")
        ap.add_argument("--collection", required=True); ap.add_argument("--tags", default=""); ap.add_argument("--also")
        ap.add_argument("--venue"); ap.add_argument("--date"); ap.add_argument("--name"); ap.add_argument("--force", action="store_true")
        ap.add_argument("--url", help="URL 字段（默认项目页，没有就 arXiv/DOI 链接）"); ap.add_argument("--short", help="Short Title（默认冒号前的名字）")
        a = ap.parse_args(args)
        save(a.slug, a.collection, a.tags.split(","), also=a.also, venue=a.venue, date_=a.date, name=a.name, force=a.force, url=a.url, short=a.short)
    elif cmd == "collect":
        print(add_collection(args[0], args[1]))
    elif cmd == "recheck":
        only = None
        if "--only" in args: only = set(args[args.index("--only") + 1].split(","))
        recheck(write="--write" in args, only=only, dates="--dates" in args, search="--search" in args)
    else: print(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
