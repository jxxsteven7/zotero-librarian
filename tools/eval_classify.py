#!/usr/bin/env python3
"""用库里已经人工核过标签的条目评估 classify.suggest：分类准确率、每个标签的精确率/召回率、候选命中率。
    python3 tools/eval_classify.py [--show KEY|--errors]
全文缓存在 cache/text/<key>.txt（第一次跑会从 Zotero 的 PDF 抽）。调 classify.py 的规则/阈值后重跑看指标。"""
import os, sys, collections, re
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, ROOT)
from zotero_claude import localdb, classify
from zotero_claude.config import CACHE, DATA_DIR
from zotero_claude.pdf import pdf_text

TXT = os.path.join(CACHE, "text"); os.makedirs(TXT, exist_ok=True)
rows = localdb.load()
FAM = ("method", "embod", "tech", "base", "modality", "type")


def text_of(r):
    p = os.path.join(TXT, r["key"] + ".txt")
    if os.path.exists(p): return open(p, encoding="utf-8").read()
    if not r["pdfs"]: return ""
    t = pdf_text(os.path.join(DATA_DIR, r["pdfs"][0]))
    open(p, "w", encoding="utf-8").write(t); return t


def strip_title(t): return re.sub(r"^(\s*\[[^\]]*\]\s*){1,3}", "", t)


tp = collections.Counter(); fp = collections.Counter(); fn = collections.Counter(); maybe_hit = collections.Counter(); maybe_all = collections.Counter()
coll_ok = 0; coll_err = []; per_item = {}
for r in rows:
    txt = text_of(r)
    sg = classify.suggest(strip_title(r["title"]), r["abstract"], txt, has_pdf=bool(txt))
    truth = {t for t in r["tags"] if t.split(":")[0] in FAM}
    pred = set(sg["sure"])
    per_item[r["key"]] = (sg, truth, r)
    for t in pred & truth: tp[t.split(":")[0]] += 1; tp["all"] += 1
    for t in pred - truth: fp[t.split(":")[0]] += 1; fp["all"] += 1; fp[t] += 1
    for t in truth - pred: fn[t.split(":")[0]] += 1; fn["all"] += 1; fn[t] += 1
    for t in sg["maybe"]:
        maybe_all[t.split(":")[0]] += 1
        if t in truth: maybe_hit[t.split(":")[0]] += 1
    want = set(r["collections"]); got = {sg["collection"]} | ({sg["also"]} if sg["also"] else set())
    if sg["collection"] in want: coll_ok += 1
    else: coll_err.append((r["key"], r["title"][:60], sorted(want), sg["collection"], sg["flags"]))

if "--show" in sys.argv:
    k = sys.argv[sys.argv.index("--show") + 1]; sg, truth, r = per_item[k]
    print(r["title"]); print("库里:", sorted(truth), r["collections"]); print(classify.fmt(sg)); sys.exit()

print(f"条目 {len(rows)}；分类命中 {coll_ok}/{len(rows)}")
for e in coll_err: print("   ✗", *e)
print(f"\n{'family':<10}{'TP':>5}{'FP':>5}{'FN':>5}{'prec':>7}{'rec':>7}   maybe命中/候选数")
for f in FAM + ("all",):
    p = tp[f] / (tp[f] + fp[f]) if tp[f] + fp[f] else 0; rc = tp[f] / (tp[f] + fn[f]) if tp[f] + fn[f] else 0
    print(f"{f:<10}{tp[f]:>5}{fp[f]:>5}{fn[f]:>5}{p:>7.2f}{rc:>7.2f}   {maybe_hit[f]}/{maybe_all[f]}")
print("\n误贴最多:", [(t, n) for t, n in fp.most_common(40) if ":" in t][:12])
print("漏贴最多:", [(t, n) for t, n in fn.most_common(40) if ":" in t][:12])
if "--errors" in sys.argv:
    for k, (sg, truth, r) in per_item.items():
        pred = set(sg["sure"])
        if pred != truth:
            print(f"\n{k} {r['title'][:70]}\n   多贴: {sorted(pred - truth)}\n   漏贴: {sorted(truth - pred)}   候选: {sorted(sg['maybe'])}")
