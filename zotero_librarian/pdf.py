"""PDFs: download, text extraction (pdftotext, then pypdf), first-page publication date, project-page candidates."""
import os, re, subprocess

from .config import PDFTOTEXT, PDFTOTEXT_INSTALL
from .http import http


def download_pdf(url, dest):
    try:
        st, h, b = http(url, headers={"Accept": "application/pdf,*/*"}, timeout=120)
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"
    if not b.startswith(b"%PDF"): return False, f"not a PDF (content-type={h.get('Content-Type')})"
    with open(dest, "wb") as f: f.write(b)
    return True, url

_PDF_WARNED = False

def pdf_text(pdf, txt=None, first_pages=None):
    """PDF -> text (pages separated by \f, like pdftotext). pdftotext first (located by config on all platforms), pypdf as
    fallback, "" if neither. With `txt`, the text is also written to that file (inbox/<slug>.txt, for grepping)."""
    global _PDF_WARNED
    text = ""
    if PDFTOTEXT:
        cmd = [PDFTOTEXT] + (["-l", str(first_pages)] if first_pages else []) + [pdf, "-"]
        try: text = subprocess.run(cmd, check=False, capture_output=True).stdout.decode("utf-8", "replace")   # pdftotext emits UTF-8; text=True would decode with the Windows code page
        except OSError as e: print(f"  ! pdftotext failed to run ({e})")
    if not text:
        try:
            import pypdf
            r = pypdf.PdfReader(pdf)
            text = "\f".join((pg.extract_text() or "") for pg in (r.pages[:first_pages] if first_pages else r.pages))
        except ImportError:
            if not PDFTOTEXT and not _PDF_WARNED:
                _PDF_WARNED = True; print(f"  ! neither pdftotext nor pypdf available: no full text (no first-page venue statement, project links or evidence). Install one: {PDFTOTEXT_INSTALL}")
        except Exception as e: print(f"  ! pypdf failed: {e}")
    if txt and text:
        with open(txt, "w", encoding="utf-8") as f: f.write(text)
    return text

MONTH_NUM = {m: i + 1 for i, m in enumerate("january february march april may june july august september october november december".split())}

MONTHS = "|".join(sorted(MONTH_NUM, key=len, reverse=True))

def pdf_first_page_date(text, pub_year):
    """Online / publication date printed on a journal PDF's first page; must be within a year of the print year or it is noise. Returns (YYYY-MM-DD, source label) or None."""
    head = text[:6000].lower()
    lead = r"(?:available online|published online|date of publication|published):?\s*"
    for rx, order in ((lead + r"(\d{1,2})\s+(" + MONTHS + r")\.?,?\s+(\d{4})", "dmy"),
                      (lead + r"(" + MONTHS + r")\.?\s+(\d{1,2}),?\s+(\d{4})", "mdy")):
        m = re.search(rx, head)
        if not m: continue
        d, mon, y = (m.group(1), m.group(2), m.group(3)) if order == "dmy" else (m.group(2), m.group(1), m.group(3))
        if pub_year and abs(int(y) - int(pub_year)) > 1: continue
        return f"{y}-{MONTH_NUM[mon]:02d}-{int(d):02d}", "pdf:online"
    m = re.search(r"published:?\s+(\d{1,2})/(\d{2}|\d{4})\b", head)                     # JMLR prints "Published 11/08": month precision only
    if m:
        mon, y = int(m.group(1)), int(m.group(2)); y = y + 2000 if y < 100 else y
        if 1 <= mon <= 12 and not (pub_year and abs(y - int(pub_year)) > 1): return f"{y}-{mon:02d}", "pdf:published(month only)"
    return None

def pdf_creation_date(pdf):
    """The day the PDF file was produced (Info dictionary or XMP), YYYY-MM-DD or None. The only date a camera-ready PDF that is
    on neither arXiv nor Crossref carries — a stand-in for the day the paper appeared, flagged as such by the caller."""
    try:
        with open(pdf, "rb") as f: raw = f.read()
    except OSError: return None
    m = re.search(rb"/CreationDate\s*\(D:(\d{4})(\d{2})(\d{2})", raw) or re.search(rb"<xmp:CreateDate>(\d{4})-(\d{2})-(\d{2})", raw)
    if not m: return None
    y, mo, d = (int(x) for x in m.groups())
    return f"{y}-{mo:02d}-{d:02d}" if 1990 <= y <= 2100 and 1 <= mo <= 12 and 1 <= d <= 31 else None


URL_RE = re.compile(r"https?://[^\s<>\"')\]]+|(?<![\w/.])[\w.-]+\.github\.io(?:/[^\s<>\"')\]]*)?")   # also bare xxx.github.io as printed in PDFs

NOT_PROJECT_HOSTS = ("arxiv.org", "doi.org", "openreview.net", "semanticscholar.org", "youtube.com", "youtu.be", "creativecommons.org",
                     "huggingface.co/papers", "orcid.org", "ieee.org", "acm.org", "overleaf.com", "developer.nvidia.com", "wikipedia.org",
                     "pytorch.org", "tensorflow.org", "python.org", "mujoco.org", "isaac-sim", "shadowrobot.com", "wonikrobotics.com",
                     "unitree.com", "franka.de", "gelsight.com", "intelrealsense.com", "ufactory.cc", "robotis.com", "science.org", "springer.com",
                     "sciencedirect.com", "nature.com", "roboticsproceedings.org", "proceedings.mlr.press", "neurips.cc", "openaccess.thecvf.com",
                     "crossref.org", "crossmark", "dl.acm.org", "ieeexplore", "scholar.google", "researchgate.net", "linkedin.com", "twitter.com", "x.com/")

def _project_score(u):
    """Ranking: project page (github.io / lab blog) > code repository > other; direct file links last."""
    ul = u.lower(); s = 0
    if re.search(r"github\.io|pages\.dev|netlify\.app|vercel\.app|sites\.google\.com/view/", ul): s += 5
    if re.search(r"(physicalintelligence|pi\.website|research\.nvidia|deepmind|openai\.com/(?:index|research)|csail\.mit\.edu)", ul): s += 4
    if re.search(r"github\.com/[^/]+/[^/]+/?$", ul): s += 2
    if re.search(r"\.(pdf|mp4|png|jpg|zip)$", ul): s -= 5
    return s

def project_urls(m, text=None, pdf=None):
    """Project / code page candidates: links in the arXiv comment, abstract and PDF first page, plus the real targets of the
    PDF's link annotations (/URI — pdftotext truncates long links, the annotations are complete). arXiv / DOI / publisher /
    vendor sites are dropped; ranked by how much they look like a project page; at most 3."""
    blob = " ".join(x for x in (m.get("comment"), m.get("abstract"), (text or "").split("\f")[0]) if x)
    ctx = {}                                                         # "project page / website / videos and code" within 120 chars before the link -> bonus
    cands = []
    for g in URL_RE.finditer(blob):
        u = g.group(0).rstrip(".,;:)"); cands.append(u)
        if re.search(r"project (?:page|website|site)|website|webpage|videos?(?: and code)?|code and videos|homepage|available at", blob[max(0, g.start() - 120):g.start()], re.I):
            ctx[u] = 3
    if pdf and os.path.exists(pdf):
        try:
            with open(pdf, "rb") as f: raw = f.read(3_000_000)
            cands += [x.decode("latin-1").rstrip(".,;:)") for x in re.findall(rb"/URI\s*\((https?://[^)]{6,200})\)", raw)]
        except OSError: pass
    out = {}
    for u in cands:
        full = u if u.startswith("http") else "https://" + u
        if any(h in full.lower() for h in NOT_PROJECT_HOSTS) or full.rstrip("/") in out: continue
        out[full.rstrip("/")] = (_project_score(full) + ctx.get(u, 0), full)
    return [full for _, (sc, full) in sorted(out.items(), key=lambda kv: kv[1][0], reverse=True)][:3]

def project_url_score(u, text=None):
    """For fetch: does a candidate qualify as the URL field automatically (github.io-like, or named as "project page/website" in the text)?"""
    return _project_score(u) > 0 or bool(text and re.search(r"(?:project (?:page|website|site)|website|webpage|videos?|homepage|available at)[\s\S]{0,120}" + re.escape(u.replace("https://", "").rstrip("/")), text.split("\f")[0], re.I))
