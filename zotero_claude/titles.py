"""标题相关：`[YYYY-MMDD] [刊/会] 原名` 的拼装、Short Title、查重用的规范化（CLAUDE.md §4）。"""
import re


def ws(s): return re.sub(r"\s+", " ", (s or "")).strip()


def clean_title(t):
    """去掉 arXiv 标题里的 LaTeX：$π_0$ -> π0，$\\pi_0$ 保留字母部分。"""
    return ws(re.sub(r"\$([^$]*)\$", lambda m: re.sub(r"[_^{}$\\]", "", m.group(1)), t or ""))

def fmt_date(d):
    """YYYY-MM-DD -> YYYY-MMDD；不完整的能到哪写哪。"""
    d = (d or "").strip()
    if len(d) >= 10: return d[:4] + "-" + d[5:7] + d[8:10]
    if len(d) >= 7: return d[:7]
    return d[:4] or "????"

def norm_title(t):
    t = re.sub(r"^(\s*\[[^\]]*\]\s*)+", "", t or "")            # 去掉 [date] [venue] 前缀
    return re.sub(r"[^a-z0-9]+", "", t.lower())

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
