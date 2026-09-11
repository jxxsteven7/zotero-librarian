"""刊/会名称 → 用户风格缩写。download.py 用；新增缩写只改这里。"""
import re

VENUE_ABBR = {  # 期刊/会议全名(小写) -> 缩写
 "knowledge-based systems": "KBS", "advances in engineering software": "AES", "the journal of supercomputing": "JSC",
 "advanced engineering informatics": "AEI", "systems science & control engineering": "SSCE", "expert systems with applications": "ESWA",
 "cluster computing": "Cluster Computing", "information sciences": "INS", "engineering applications of artificial intelligence": "EAAI",
 "computers & industrial engineering": "CAIE", "neural computing and applications": "NCA", "biomimetics": "Biomimetics",
 "computer methods in applied mechanics and engineering": "CMAME", "applied soft computing": "ASOC", "journal of global optimization": "JOGO",
 "swarm and evolutionary computation": "SWEVO", "applied thermal engineering": "ATE", "soft computing": "SOCO",
 "ieee transactions on evolutionary computation": "TEVC", "applied mathematical modelling": "AMM", "communications of the acm": "CACM",
 "ieee access": "Access", "science robotics": "SR", "robotics: science and systems": "RSS", "simulation": "Simulation",
}
VENUE_RE = [  # (regex on notes / arXiv comment / PDF header / container-title, abbr)
 (r"conference on robot learning|\bcorl\b", "CoRL"), (r"robotics: science and systems|\brss\b", "RSS"),
 (r"international conference on robotics and automation|\bicra\b", "ICRA"), (r"intelligent robots and systems|\biros\b", "IROS"),
 (r"international conference on learning representations|\biclr\b", "ICLR"), (r"international conference on machine learning|\bicml\b", "ICML"),
 (r"neural information processing systems|\bneurips\b|\bnips\b", "NeurIPS"), (r"computer vision and pattern recognition|\bcvpr\b", "CVPR"),
 (r"\biccv\b", "ICCV"), (r"\beccv\b", "ECCV"), (r"\baaai\b", "AAAI"), (r"science robotics", "SR"), (r"\bijrr\b|international journal of robotics research", "IJRR"),
 (r"\bt-ro\b|transactions on robotics", "TRO"), (r"\bra-l\b|robotics and automation letters", "RAL"), (r"congress on evolutionary computation|\bcec\b", "CEC"),
 (r"\bhumanoids\b", "Humanoids"), (r"artificial intelligence and statistics|\baistats\b", "AISTATS"), (r"\bjmlr\b", "JMLR"), (r"\btpami\b", "TPAMI"),
]
KNOWN_VENUE_TOKENS = {v for _, v in VENUE_RE} | set(VENUE_ABBR.values()) | {"arXiv", "Book", "ICRA-Best", "TechReport"}

# arXiv comment / 笔记里必须带这类语境词才认作"已中稿"，避免把 "compared with the CoRL 2023 baseline" 当会议
ACCEPT_CONTEXT = re.compile(r"accept|publish|appear|proceedings|to be presented|oral|spotlight|best|award|"
                            r"(corl|rss|icra|iros|iclr|icml|neurips|cvpr|iccv|eccv|aaai|aistats|robotics: science and systems)\)?\s*20\d\d")


def abbr_from_name(name):
    """期刊/会议全名 -> 缩写；查不到返回 None。"""
    low = (name or "").lower().strip()
    if not low: return None
    for full, ab in VENUE_ABBR.items():
        if full in low: return ab
    for rx, ab in VENUE_RE:
        if re.search(rx, low): return ab
    return None


def venue_from_context(text):
    """从 arXiv comment / 笔记这类自由文本里找中稿会议；没有语境词或没匹配到返回 None。"""
    low = (text or "").lower()
    if not low or not ACCEPT_CONTEXT.search(low): return None
    for rx, ab in VENUE_RE:
        if re.search(rx, low): return ab
    return None


# PDF 首页上的出版声明（页眉/页脚/脚注）。只看首页：末页常是参考文献，"In Robotics: Science and Systems, 2023." 这种换行会误判
PDF_VENUE_LINE = re.compile(r"published as a conference paper at|proceedings of|conference on robot learning|robotics: science and systems|"
                            r"international conference on (?:robotics and automation|machine learning|learning representations|intelligent robots)|"
                            r"neural information processing systems|computer vision and pattern recognition|"
                            r"\b(?:corl|rss|icra|iros|iclr|icml|neurips|cvpr|iccv|eccv|aaai)\b[ ,'’(]*20\d\d", re.I)
NOT_A_STATEMENT = re.compile(r"^\s*\[\d+\]|et al\.|arXiv preprint|arXiv:\d|pp\.\s*\d|\bvol\.|compared|baseline|following|similar to|we use|we adopt|we follow", re.I)


def venue_from_pdf(text):
    """从 PDF 首页文本找出版声明 → (缩写, 证据行)；找不到 (None, None)。"""
    lines = [l.strip() for l in (text or "").split("\f")[0].split("\n") if l.strip()]
    cands = lines + [a + " " + b for a, b in zip(lines, lines[1:])]        # 页脚声明常换行（ICML 模板），再看相邻两行拼起来的
    for s in cands:
        if len(s) > 260 or NOT_A_STATEMENT.search(s) or not PDF_VENUE_LINE.search(s): continue
        v = venue_from_context(s)
        if v: return v, s[:120]
    return None, None
