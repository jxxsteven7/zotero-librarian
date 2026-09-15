"""Has an arXiv preprint been published? arXiv comment -> PDF first-page statement -> Semantic Scholar -> Crossref -> project page (source priority per AGENTS.md)."""
import html, json, re, sys, time, urllib.parse

from .http import http, get_text, UA_LOCAL
from .pdf import project_urls
from .titles import norm_title, ws
from .venues import abbr_from_name, venue_from_context, venue_from_pdf


def s2_venues(arxiv_ids):
    """Semantic Scholar batch lookup of the publication venue: {arXiv id: (abbr or None, evidence)}. Only records with
    type=conference or a non-arXiv DOI count (S2 files cs.RO preprints under a fake journal called "Robotics" with the arXiv
    DOI — not a publication). Without an API key it 429s often; back off and retry."""
    out = {}
    ids = [a for a in dict.fromkeys(arxiv_ids) if a]
    for i in range(0, len(ids), 200):
        chunk = ids[i:i + 200]; body = json.dumps({"ids": ["arXiv:" + a for a in chunk]}).encode()
        js = None
        for attempt in range(6):
            try:
                st, h, raw = http("https://api.semanticscholar.org/graph/v1/paper/batch?fields=title,venue,publicationVenue,externalIds,year",
                                  data=body, headers={"Content-Type": "application/json"}, method="POST", ua=UA_LOCAL)
                js = json.loads(raw.decode()); break
            except OSError as e:                                        # 400 for ids S2 doesn't know yet (a day-old preprint), 429, timeouts
                if getattr(e, "code", None) == 429 and attempt < 5: time.sleep(4 * (attempt + 1)); continue
                print(f"  ! Semantic Scholar {getattr(e, 'code', e)}; venue lookup continues without it", file=sys.stderr); break
        if not js: continue
        for a, pp in zip(chunk, js):
            if not pp: continue
            pv = pp.get("publicationVenue") or {}; name = pv.get("name") or pp.get("venue") or ""
            doi = ((pp.get("externalIds") or {}).get("DOI") or "")
            real_doi = doi and not doi.lower().startswith("10.48550/")
            if pv.get("type") == "conference" or real_doi:
                out[a] = (abbr_from_name(name), f"S2: {name}" + (f" doi:{doi}" if real_doi else ""))
    return out

def crossref_by_title(title):
    """Crossref title search for a published version (only venues that mint DOIs, e.g. IEEE): (abbr or None, evidence) or (None, None)."""
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

def venue_from_page(url):
    """Fetch a project page / README and look for "Accepted to CoRL 2026"-style statements -> (abbr, evidence); (None, note) when it says under review / anonymous."""
    try: page = get_text(url, timeout=30)
    except Exception: return None, None
    txt = re.sub(r"<!--.*?-->", " ", page, flags=re.S)                  # HTML comments often keep the template's "Anonymous Author(s)"; ignore them
    txt = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", " ", txt, flags=re.S | re.I)
    txt = ws(html.unescape(re.sub(r"<[^>]+>", " ", txt)))
    if re.search(r"anonymous submission|under review", txt, re.I): return None, f"{url} says under review / anonymous"
    head = txt[:800]                                                    # header badge: literally "CoRL 2025"
    v = venue_from_context(head)
    if v and re.search(r"(corl|rss|icra|iros|iclr|icml|neurips|cvpr|iccv|eccv|aaai|aistats)\W{0,3}20\d\d", head, re.I):
        return v, f"{url} header: " + re.search(r".{0,50}(corl|rss|icra|iros|iclr|icml|neurips|cvpr|iccv|eccv|aaai|aistats)\W{0,3}20\d\d.{0,30}", head, re.I).group(0)
    for s in re.split(r"(?<=[.!。])\s+", txt):
        if len(s) > 300 or not re.search(r"accept|to appear|publish|presented at|\boral\b|spotlight|proceedings", s, re.I): continue
        v = venue_from_context(s)
        if v: return v, f"{url}: {s[:120]}"
    return None, None

def lookup_published(m, text=None, s2=None):
    """Is this arXiv preprint published? arXiv comment -> PDF first page -> Semantic Scholar -> Crossref -> project page. Fills m['venue'] / m['venue_src']."""
    if m.get("venue_src") != "default": return
    v, ev = venue_from_pdf(text) if text else (None, None)
    if v: m["venue"], m["venue_src"] = v, f"pdf: {ev}"; return
    s2 = s2 if s2 is not None else s2_venues([m["id"]])
    notes = []
    if m["id"] in s2:
        ab, ev = s2[m["id"]]
        if ab: m["venue"], m["venue_src"] = ab, ev; return
        notes.append(f"S2 says {ev}, no abbreviation in taxonomy.toml !")
    ab, ev = crossref_by_title(m["title"])
    if ab: m["venue"], m["venue_src"] = ab, ev; return
    if ev: notes.append(f"{ev}, no abbreviation in taxonomy.toml !")
    for u in project_urls(m, text):
        ab, ev = venue_from_page(u)
        if ab: m["venue"], m["venue_src"] = ab, "project page " + ev; return
        if ev: notes.append(ev)
    if notes: m["venue_src"] = "default（" + "；".join(notes) + "）"
