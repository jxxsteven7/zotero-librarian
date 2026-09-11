"""刊/会名称 → 用户风格缩写。retitle.py 与 download.py 共用；新增缩写只改这里。"""
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
