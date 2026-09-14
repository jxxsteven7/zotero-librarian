"""PDF：下载、抽文本（pdftotext → pypdf）、首页出版日期、项目页链接候选。"""
import os, re, subprocess

from .config import PDFTOTEXT, PDFTOTEXT_INSTALL
from .http import http


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
    m = re.search(r"published:?\s+(\d{1,2})/(\d{2}|\d{4})\b", head)                     # JMLR 首页 "Published 11/08"：只到月
    if m:
        mon, y = int(m.group(1)), int(m.group(2)); y = y + 2000 if y < 100 else y
        if 1 <= mon <= 12 and not (pub_year and abs(y - int(pub_year)) > 1): return f"{y}-{mon:02d}", "pdf:published(只到月)"
    return None

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
