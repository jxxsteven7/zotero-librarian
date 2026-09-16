"""Titles: the `[YYYY-MMDD] [Venue] Original title` format (off with [library] title_prefix = false), Short Title,
normalization for de-duplication."""
import re

from .taxonomy import TITLE_PREFIX


def ws(s): return re.sub(r"\s+", " ", (s or "")).strip()


SUBSCRIPT_DIGITS = str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")


def ascii_pi(t):
    """Physical Intelligence's model names are written in ASCII — `pi0`, `pi0.5`, `pi0.6` — never with the Greek letter:
    a π in a title is not searchable (the user's rule, 2026-09-16). Only a π directly followed by a digit is touched."""
    t = re.sub(r"π[₀-₉][₀-₉.]*", lambda m: m.group(0).translate(SUBSCRIPT_DIGITS), t or "")     # π₀.₅ -> π0.5
    return re.sub(r"π\s*[_\-]?\s*(?=\d)", "pi", t)


def clean_title(t):
    """Strip LaTeX from arXiv titles ($π_0$, $\\pi_0$ -> pi0) and write PI's model names in ASCII (ascii_pi)."""
    return ascii_pi(ws(re.sub(r"\$([^$]*)\$", lambda m: re.sub(r"[_^{}$\\]", "", m.group(1)), t or "")))


def fmt_date(d):
    """YYYY-MM-DD -> YYYY-MMDD; incomplete dates are written as far as they go, never invented. Unpadded parts are padded
    (`2019-6-9`, the HighWire citation_date format); Zotero stores month precision as YYYY-MM-00."""
    m = re.match(r"\s*(\d{4})(?:[-/.](\d{1,2}))?(?:[-/.](\d{1,2}))?", d or "")
    if not m: return "????"
    y, mo, da = m.group(1), int(m.group(2) or 0), int(m.group(3) or 0)
    if mo and da: return f"{y}-{mo:02d}{da:02d}"
    return f"{y}-{mo:02d}" if mo else y


def split_prefix(t):
    """'[2025-0506] [CoRL] Title' -> ('2025-0506', 'CoRL', 'Title'); missing brackets come back as None."""
    m = re.match(r"^\s*\[([^\]]*)\]\s*\[([^\]]*)\]\s*(.*)$", t or "", re.S)
    if m: return m.group(1), m.group(2), m.group(3).strip()
    m = re.match(r"^\s*\[([^\]]*)\]\s*(.*)$", t or "", re.S)
    if m and re.match(r"^\d{4}", m.group(1)): return m.group(1), None, m.group(2).strip()
    return None, None, (t or "").strip()


def merge_prefix(old_date, old_venue, date_, venue):
    """An existing `[date] [venue]` prefix wins over what the scripts derived (AGENTS.md: user-set titles are never changed):
    the date only gains precision, the venue only fills a placeholder (`????` / `arXiv`). A nickname sitting in the venue
    slot (`[2023] [ALOHA/ACT] Title`) is therefore kept too. Returns (date, venue)."""
    if old_date and (date_ in ("????", "") or len(old_date) >= len(date_)): date_ = old_date
    if old_venue and (old_venue not in ("????", "arXiv") or venue in ("????", "arXiv")): venue = old_venue
    return date_, venue


def norm_title(t):
    t = re.sub(r"^(\s*\[[^\]]*\]\s*)+", "", ascii_pi(t))        # drop [date] [venue] prefixes; π0.5 and pi0.5 are the same paper
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
