"""zc.py 的子命令。规则在仓库 CLAUDE.md；三平台通用（Windows 上 python3 写成 python）。"""
import argparse, sys

from . import config   # noqa: F401  —— 一进来就把 stdout 固定成 UTF-8（Windows 管道下打中文/✓ 会崩）

USAGE = """python3 zc.py <命令> …     Zotero 文献库整理（规则：CLAUDE.md）

收论文（/download 用）
  add <链接|PDF路径>…      一条龙：fetch → 自动分类/贴标签 → 入库 → 等远端同步核对 → 提交日志 → 汇报表
        [--collection X] [--also Y] [--tags a,b] [--drop a,b] [--first] [--force] [--venue X] [--date YYYY-MM-DD]
        [--url 项目页] [--short 短名] [--name 原名] [--wait 秒(默认150)] [--no-commit] [--dry-run]
  fetch <链接>…            只抓取到 inbox/（元数据 + PDF + 全文 + 查重 + 建议标题），打印完整卡片，不动库
  suggest <slug>           对 inbox 里的一条打印自动分类/标签和证据（不动库）
  save <slug> [同 add 的选项]   fetch 过之后入库；不给 --tags 就用脚本建议的
  list / show <slug>       inbox 里还没入库的

改已有条目（都走 Web API，自动记日志）
  verify <key> [--wait 秒]        远端 + 本地核对一条（分类/标签/URL/短名/附件/同步状态）
  tag <key> a,b                   补标签（只增不减；讨论后补边缘标签用）
  untag <key> a,b [--why 原因]    摘标签（只用于修正刚入库条目上贴错的，或用户明说）
  collect <key> <分类>            补第二个分类
  set <key> field=value …         改字段（title / url / shortTitle …）
  recheck [--dates] [--search] [--write] [--only K1,K2]   存量 [arXiv] 条目查中稿 / 核对 v1 日期

库与批量
  dump [--table]           只读导出全库 → cache/library_dump.json
  proposal                 由 proposals/proposal.py 生成 proposals/proposal.md
  apply --dry-run|--plan|--apply [--only K1,K2] [--no-rename] [--no-status]   批量写入（approval mode）
  setup                    新机器体检（Python / .env / 数据目录 / pdftotext / 网络 / Zotero / API key）
"""


def _add_save_opts(ap):
    ap.add_argument("--collection"); ap.add_argument("--also"); ap.add_argument("--tags", default="")
    ap.add_argument("--drop", default="", help="从脚本建议里去掉的标签"); ap.add_argument("--first", action="store_true", help="status:to-read-first")
    ap.add_argument("--force", action="store_true", help="库里已有也再加"); ap.add_argument("--venue"); ap.add_argument("--date")
    ap.add_argument("--name", help="原名（覆盖抓到的标题）"); ap.add_argument("--url", help="URL 字段（默认项目页，没有就 arXiv/DOI 链接）")
    ap.add_argument("--short", help="Short Title（默认冒号前的名字）"); ap.add_argument("--wait", type=int, default=150, help="等远端同步的秒数，0 = 不等")
    ap.add_argument("--no-commit", action="store_true", help="不自动 git commit/push 日志")


def _kw(a):
    return dict(collection=a.collection, also=a.also, tags=[t for t in a.tags.split(",") if t], drop=[t for t in a.drop.split(",") if t], first=a.first,
                force=a.force, venue=a.venue, date_=a.date, name=a.name, url=a.url, short=a.short, wait=a.wait, commit=not a.no_commit)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] in ("-h", "--help", "help"): print(USAGE); return
    cmd, args = argv[0], argv[1:]

    if cmd == "add":
        from . import pipeline
        ap = argparse.ArgumentParser(prog="zc.py add"); ap.add_argument("links", nargs="+"); _add_save_opts(ap); ap.add_argument("--dry-run", action="store_true")
        a = ap.parse_args(args); pipeline.add(a.links, dry_run=a.dry_run, **_kw(a))
    elif cmd == "fetch":
        from . import fetch
        for link in args:
            try: fetch.card(fetch.fetch_one(link))
            except Exception as e: print(f"=== {link}\n  ✗ {e}\n")
    elif cmd == "suggest":
        from . import classify, fetch, pipeline
        m = fetch.load(args[0]); print(f"=== {m['proposed_title']}"); print(classify.fmt(pipeline.suggest_for(m)))
    elif cmd == "save":
        from . import pipeline
        ap = argparse.ArgumentParser(prog="zc.py save"); ap.add_argument("slug"); _add_save_opts(ap)
        a = ap.parse_args(args); pipeline.save(a.slug, **_kw(a))
    elif cmd == "show":
        from . import fetch; fetch.card(fetch.load(args[0]))
    elif cmd == "list":
        from . import fetch
        for m in fetch.list_inbox(): print(f"{m['slug']:<28} {m['proposed_title'][:90]}")
    elif cmd == "verify":
        from . import pipeline
        wait = int(args[args.index("--wait") + 1]) if "--wait" in args else 0
        pipeline.verify(args[0], wait=wait)
    elif cmd == "tag":
        from . import zapi; print(zapi.add_tags(args[0], args[1].split(",")))
    elif cmd == "untag":
        from . import zapi
        why = args[args.index("--why") + 1] if "--why" in args else ""
        print(zapi.remove_tags(args[0], args[1].split(","), why))
    elif cmd == "collect":
        from . import zapi; print(zapi.add_collection(args[0], args[1]))
    elif cmd == "set":
        from . import zapi
        fields = dict(kv.split("=", 1) for kv in args[1:]); print(zapi.set_fields(args[0], fields))
    elif cmd == "recheck":
        from . import recheck
        only = set(args[args.index("--only") + 1].split(",")) if "--only" in args else None
        recheck.recheck(write="--write" in args, only=only, dates="--dates" in args, search="--search" in args)
    elif cmd == "dump":
        from . import localdb; localdb.dump(table="--table" in args)
    elif cmd == "proposal":
        import importlib.util
        from .config import PROPOSAL_PY
        spec = importlib.util.spec_from_file_location("proposal", PROPOSAL_PY); mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); mod.run(args)
    elif cmd == "apply":
        from . import batch; batch.run(args)
    elif cmd == "setup":
        from . import setup_check; setup_check.run(args)
    else:
        print(f"不认识的命令 {cmd!r}\n"); print(USAGE); sys.exit(2)
