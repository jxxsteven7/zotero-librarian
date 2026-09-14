"""Venue names -> the abbreviations used in the title's second bracket. The table lives in taxonomy.toml ([[venues]])."""
import re

from . import taxonomy as tx

VENUE_ABBR = {v["name"].lower(): v["abbr"] for v in tx.VENUES if v.get("name")}          # full journal name (substring) -> abbr
VENUE_RE = [(rx, v["abbr"]) for v in tx.VENUES for rx in v.get("match", [])]             # regex on free text -> abbr
KNOWN_VENUE_TOKENS = {v["abbr"] for v in tx.VENUES} | set(tx.VENUE_MISC.get("other_tokens", []))
ACCEPT_CONTEXT = re.compile(tx.VENUE_MISC.get("accept_context", "accept|publish|appear|proceedings"), re.I)

# Publication statements printed on a PDF's first page (header / footer / footnote). First page only: the last page is
# references, where "In Robotics: Science and Systems, 2023." would be a false positive.
PDF_VENUE_LINE = re.compile(r"published as a conference paper at|proceedings of|conference on robot learning|robotics: science and systems|"
                            r"international conference on (?:robotics and automation|machine learning|learning representations|intelligent robots)|"
                            r"neural information processing systems|computer vision and pattern recognition|"
                            r"\b(?:corl|rss|icra|iros|iclr|icml|neurips|cvpr|iccv|eccv|aaai)\b[ ,'’(]*20\d\d", re.I)
NOT_A_STATEMENT = re.compile(r"^\s*\[\d+\]|et al\.|arXiv preprint|arXiv:\d|pp\.\s*\d|\bvol\.|compared|baseline|following|similar to|we use|we adopt|we follow", re.I)


def abbr_from_name(name):
    """Journal / conference name -> abbreviation, or None if unknown."""
    low = (name or "").lower().strip()
    if not low: return None
    for full, ab in VENUE_ABBR.items():
        if full in low: return ab
    for rx, ab in VENUE_RE:
        if re.search(rx, low): return ab
    return None


def venue_from_context(text):
    """Find an accepted venue in free text (arXiv comment, notes); None unless the text also has an acceptance word."""
    low = (text or "").lower()
    if not low or not ACCEPT_CONTEXT.search(low): return None
    for rx, ab in VENUE_RE:
        if re.search(rx, low): return ab
    return None


def venue_from_pdf(text):
    """Publication statement on the PDF's first page -> (abbr, evidence line), or (None, None)."""
    lines = [l.strip() for l in (text or "").split("\f")[0].split("\n") if l.strip()]
    cands = lines + [a + " " + b for a, b in zip(lines, lines[1:])]        # footers often wrap (ICML template): also try adjacent pairs
    for s in cands:
        if len(s) > 260 or NOT_A_STATEMENT.search(s) or not PDF_VENUE_LINE.search(s): continue
        v = venue_from_context(s)
        if v: return v, s[:120]
    return None, None
