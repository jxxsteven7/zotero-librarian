"""Titles: the `[YYYY-MMDD] [Venue] Original title` format (off with [library] title_prefix = false), Short Title,
normalization for de-duplication."""
import re

from .taxonomy import TITLE_PREFIX


def ws(s): return re.sub(r"\s+", " ", (s or "")).strip()


def clean_title(t):
    """Strip LaTeX from arXiv titles: $π_0$ -> π0, $\\pi_0$ keeps the letters."""
    return ws(re.sub(r"\$([^$]*)\$", lambda m: re.sub(r"[_^{}$\\]", "", m.group(1)), t or ""))


def fmt_date(d):
    """YYYY-MM-DD -> YYYY-MMDD; incomplete dates are written as far as they go, never invented."""
    d = (d or "").strip()
    if len(d) >= 10 and d[8:10] != "00": return d[:4] + "-" + d[5:7] + d[8:10]
    if len(d) >= 7 and d[5:7] != "00": return d[:7]                        # Zotero stores month precision as YYYY-MM-00
    return d[:4] or "????"


def split_prefix(t):
    """'[2025-0506] [CoRL] Title' -> ('2025-0506', 'CoRL', 'Title'); missing brackets come back as None."""
    m = re.match(r"^\s*\[([^\]]*)\]\s*\[([^\]]*)\]\s*(.*)$", t or "", re.S)
    if m: return m.group(1), m.group(2), m.group(3).strip()
    m = re.match(r"^\s*\[([^\]]*)\]\s*(.*)$", t or "", re.S)
    if m and re.match(r"^\d{4}", m.group(1)): return m.group(1), None, m.group(2).strip()
    return None, None, (t or "").strip()


def norm_title(t):
    t = re.sub(r"^(\s*\[[^\]]*\]\s*)+", "", t or "")            # drop [date] [venue] prefixes
    return re.sub(r"[^a-z0-9]+", "", t.lower())


def strip_prefix(t):
    """Remove the [date] [venue] brackets (and a nickname bracket) from a formatted title."""
    return re.sub(r"^(\s*\[[^\]]*\]\s*){1,3}", "", t or "").strip()


def short_title(name):
    """Zotero's Short Title = the paper's short name (mirrors such as a Notion database use it as the page title):
    user nickname [ALOHA/ACT] > the name before the colon > the title without prefixes."""
    name = re.sub(r"^(\s*\[[^\]]*\]\s*){2}", "", name or "").strip()          # drop [date] [venue]
    g = re.match(r"^\[([^\]]+)\]\s*", name)
    if g: return g.group(1)
    head = name.split(":")[0].strip()
    if ":" in name and 2 <= len(head) <= 40: return head
    return re.sub(r"\s*[✅❗]+$", "", name)


def make_title(m, name=None, venue=None, date_=None):
    if not TITLE_PREFIX: return (name or m["title"]).strip()
    return f"[{date_ or fmt_date(m.get('date'))}] [{venue or m.get('venue') or '????'}] {name or m['title']}".strip()
