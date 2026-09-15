#!/usr/bin/env python3
"""Evaluate the classifier against the library's own reviewed items (their tags are the ground truth).

    python3 tools/eval_classify.py [--llm [--policy adjudicate|veto]] [--errors] [--show KEY] [--only K1,K2]

--llm runs the configured local model on top of the rules (one model call per item; raw answers are cached in
cache/llm/<model>/ so merge policies can be compared without re-running the model).
Full texts are cached in cache/text/<key>.txt (extracted from the Zotero PDFs on first run).
Re-run after editing taxonomy.toml patterns / thresholds to see precision and recall move."""
import os, sys, collections, re
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, ROOT)
from zotero_librarian import localdb, classify, llm, taxonomy as tx
from zotero_librarian.config import CACHE, DATA_DIR
from zotero_librarian.pdf import pdf_text
from zotero_librarian.titles import strip_prefix

TXT = os.path.join(CACHE, "text"); os.makedirs(TXT, exist_ok=True)
rows = localdb.load()
FAM = tx.FAMILIES + ("type",)
use_llm = "--llm" in sys.argv
policy = sys.argv[sys.argv.index("--policy") + 1] if "--policy" in sys.argv else "adjudicate"      # adjudicate | veto
only = set(sys.argv[sys.argv.index("--only") + 1].split(",")) if "--only" in sys.argv else None


def text_of(r):
    p = os.path.join(TXT, r["key"] + ".txt")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f: return f.read()
    if not r["pdfs"]: return ""
    t = pdf_text(os.path.join(DATA_DIR, r["pdfs"][0]))
    with open(p, "w", encoding="utf-8") as f: f.write(t)
    return t


tp = collections.Counter(); fp = collections.Counter(); fn = collections.Counter(); maybe_hit = collections.Counter(); maybe_all = collections.Counter()
coll_ok = 0; coll_err = []; per_item = {}
for r in rows:
    if only and r["key"] not in only: continue
    txt = text_of(r)
    if use_llm:
        sg = llm.suggest(strip_prefix(r["title"]), r["abstract"], txt, has_pdf=bool(txt), policy=policy,
                         cache=os.path.join(CACHE, "llm", llm.settings()["model"].replace("/", "_").replace(":", "_"), r["key"] + ".json"))
    else:
        sg = classify.suggest(strip_prefix(r["title"]), r["abstract"], txt, has_pdf=bool(txt))
    truth = {t for t in r["tags"] if t.split(":")[0] in FAM}
    pred = set(sg["sure"])
    per_item[r["key"]] = (sg, truth, r)
    for t in pred & truth: tp[t.split(":")[0]] += 1; tp["all"] += 1
    for t in pred - truth: fp[t.split(":")[0]] += 1; fp["all"] += 1; fp[t] += 1
    for t in truth - pred: fn[t.split(":")[0]] += 1; fn["all"] += 1; fn[t] += 1
    for t in sg["maybe"]:
        maybe_all[t.split(":")[0]] += 1
        if t in truth: maybe_hit[t.split(":")[0]] += 1
    want = set(r["collections"])
    if sg["collection"] in want: coll_ok += 1
    else: coll_err.append((r["key"], r["title"][:60], sorted(want), sg["collection"], [f for f in sg["flags"] if "BOUNDARY" in f]))

if "--show" in sys.argv:
    k = sys.argv[sys.argv.index("--show") + 1]; sg, truth, r = per_item[k]
    print(r["title"]); print("library:", sorted(truth), r["collections"]); print(classify.fmt(sg)); print(llm.fmt_llm(sg)); sys.exit()

n = len(per_item)
print(f"{n} items; collection correct {coll_ok}/{n}" + ("  [rules + LLM]" if use_llm else "  [rules only]"))
for e in coll_err: print("   x", *e)
print(f"\n{'family':<10}{'TP':>5}{'FP':>5}{'FN':>5}{'prec':>7}{'rec':>7}   candidates that were right / listed")
for f in FAM + ("all",):
    p = tp[f] / (tp[f] + fp[f]) if tp[f] + fp[f] else 0; rc = tp[f] / (tp[f] + fn[f]) if tp[f] + fn[f] else 0
    print(f"{f:<10}{tp[f]:>5}{fp[f]:>5}{fn[f]:>5}{p:>7.2f}{rc:>7.2f}   {maybe_hit[f]}/{maybe_all[f]}")
print("\nmost over-assigned:", [(t, c) for t, c in fp.most_common(40) if ":" in t][:12])
print("most missed:", [(t, c) for t, c in fn.most_common(40) if ":" in t][:12])
if "--errors" in sys.argv:
    for k, (sg, truth, r) in per_item.items():
        pred = set(sg["sure"])
        if pred != truth:
            print(f"\n{k} {r['title'][:70]}\n   extra: {sorted(pred - truth)}\n   missed: {sorted(truth - pred)}   candidates: {sorted(sg['maybe'])}")
