"""Subcommands of zl.py. Rules live in AGENTS.md, the taxonomy in taxonomy.toml. (On Windows, `python` instead of `python3`.)"""
import argparse, sys

from . import NAME, __version__, config   # noqa: F401 — config forces UTF-8 stdout before anything prints (Windows pipes)

USAGE = """python3 zl.py <command> ...        Zotero library maintenance (rules: AGENTS.md, taxonomy: taxonomy.toml)

Adding papers (the download skill)
  add <link|PDF path>...   fetch -> classify (rules + local LLM) -> save via Zotero desktop -> verify on the server -> log -> report
        [--from-file FILE]   (one link / arXiv id / DOI per line; # comments) — a reading list or a bibliography in one go
        [--collection X] [--also Y] [--tags a,b] [--drop a,b] [--first] [--force] [--venue X] [--date YYYY-MM-DD]
        [--url URL] [--short NAME] [--name TITLE] [--wait SECONDS (150)] [--dry-run] [--confirm a,b|none]
  fetch <link>...          stage only (metadata + PDF + full text + duplicate check + proposed title) in inbox/, full card, no write
  suggest <slug>           classification with evidence for a staged paper (no write)
  save <slug> [add options]   save a staged paper; without --tags the script's suggestion is used
  list / show <slug>       staged papers

Organizing what is already in Zotero
  tidy [--only K1,K2] [--collection X] [--confirm a,b|none] [--dry-run] [--limit N] [--create-collections] [--wait S]
                           items without a status tag (dropped into Zotero by hand — or, on a library nobody has organized
                           yet, every item): fill metadata, format the title, set URL / short title, classify, file into a
                           collection — via the Web API. --dry-run --limit 20 samples the plan; --create-collections adds
                           the taxonomy's collections that the library lacks
  verify <key> [--wait S]  server + local state of one item
  tag <key> a,b            add tags (never removes)
  untag <key> a,b [--why REASON]   remove tags (only to correct a fresh mistake, or on explicit request)
  collect <key> <collection>       add a second collection
  set <key> field=value ...        change fields (title, url, shortTitle, ...)
  recheck [--dates] [--search] [--write] [--only K1,K2]   re-verify [arXiv] items: published? v1 date?

Finding papers
  discover [--days 7] [--cat cs.RO,cs.AI] [--query REGEX] [--tags a,b] [--all] [--source arxiv,hf] [--max 400]
                           recent papers scored against the taxonomy; nothing is saved
  refs <key|arXiv|DOI|link> [--top 15]   references and citations of one paper, cross-checked with the library
  refs --library [--top 20]              citation links between library papers

Library
  dump [--table]           read-only snapshot -> cache/library_dump.json
  setup [--sync-skills] [--offline]   health check (Python / .env / data dir / taxonomy / pdftotext / network / Zotero / API key / LLM / skills /
                           agents); --offline = repository checks only (what CI runs; no Zotero, no network)
  install [--remove]       use it from anywhere: launcher `zl` on PATH + user-level skills for Claude Code / Codex
  --version                print the version (CHANGELOG.md lists the changes)

With ZC_LLM=agent (no local model) add / save / tidy pause with an ADJUDICATE block; answer it on the printed command with
--confirm <tags> (the candidates you confirm) or --confirm none.
"""


def _add_save_opts(ap):
    ap.add_argument("--collection"); ap.add_argument("--also"); ap.add_argument("--tags", default="")
    ap.add_argument("--drop", default="", help="tags to remove from the script's suggestion"); ap.add_argument("--first", action="store_true", help="status: first value of the read axis (to-read-first)")
    ap.add_argument("--force", action="store_true", help="add even if the library already has it"); ap.add_argument("--venue"); ap.add_argument("--date")
    ap.add_argument("--name", help="original title (overrides the fetched one)"); ap.add_argument("--url", help="URL field (default: project page, else arXiv/DOI link)")
    ap.add_argument("--short", help="Short Title (default: the name before the colon)"); ap.add_argument("--wait", type=int, default=150, help="seconds to wait for the server sync; 0 = don't wait")
    ap.add_argument("--confirm", help="ZC_LLM=agent: the ADJUDICATE candidates you confirm (comma-separated), or none")


def _confirm(v):
    return None if v is None else [t for t in v.split(",") if t and t != "none"]


def _kw(a):
    return dict(collection=a.collection, also=a.also, tags=[t for t in a.tags.split(",") if t], drop=[t for t in a.drop.split(",") if t], first=a.first,
                force=a.force, venue=a.venue, date_=a.date, name=a.name, url=a.url, short=a.short, wait=a.wait, confirm=_confirm(a.confirm))


def _opt(args, name, default=None, cast=str):
    return cast(args[args.index(name) + 1]) if name in args else default


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] in ("-h", "--help", "help"): print(USAGE); return
    if argv[0] in ("--version", "-V", "version"): print(f"{NAME} {__version__}"); return
    try: run(argv[0], argv[1:])
    except IndexError: sys.exit(f"zl.py {argv[0]}: missing argument — see `python3 zl.py --help`")


def run(cmd, args):
    if cmd == "add":
        from . import pipeline
        ap = argparse.ArgumentParser(prog="zl.py add"); ap.add_argument("links", nargs="*"); _add_save_opts(ap); ap.add_argument("--dry-run", action="store_true")
        ap.add_argument("--from-file", metavar="FILE", help="one link / arXiv id / DOI per line; blank lines and # comments skipped")
        a = ap.parse_args(args); links = list(a.links)
        if a.from_file:
            with open(a.from_file, encoding="utf-8") as f: links += [l.split("#")[0].strip() for l in f if l.split("#")[0].strip()]
        if not links: ap.error("give links, or --from-file FILE")
        pipeline.add(links, dry_run=a.dry_run, **_kw(a))
    elif cmd == "fetch":
        from . import fetch
        for link in args:
            try: fetch.card(fetch.fetch_one(link))
            except Exception as e: print(f"=== {link}\n  x {e}\n")
    elif cmd == "suggest":
        from . import classify, fetch, llm, pipeline
        m = fetch.load(args[0]); sg = pipeline.suggest_for(m); print(f"=== {m['proposed_title']}"); print(classify.fmt(sg)); print(llm.fmt_llm(sg))
    elif cmd == "save":
        from . import pipeline
        ap = argparse.ArgumentParser(prog="zl.py save"); ap.add_argument("slug"); _add_save_opts(ap)
        a = ap.parse_args(args); pipeline.save(a.slug, **_kw(a))
    elif cmd == "show":
        from . import fetch; fetch.card(fetch.load(args[0]))
    elif cmd == "list":
        from . import fetch
        for m in fetch.list_inbox(): print(f"{m['slug']:<28} {m['proposed_title'][:90]}")
    elif cmd == "tidy":
        from . import pipeline
        only = set(_opt(args, "--only", "").split(",")) - {""} or None
        pipeline.tidy(only=only, write="--dry-run" not in args, wait=_opt(args, "--wait", 0, int), collection=_opt(args, "--collection"), confirm=_confirm(_opt(args, "--confirm")),
                      limit=_opt(args, "--limit", None, int), create_collections="--create-collections" in args)
    elif cmd == "verify":
        from . import pipeline; pipeline.verify(args[0], wait=_opt(args, "--wait", 0, int))
    elif cmd == "tag":
        from . import zapi; print(zapi.add_tags(args[0], args[1].split(",")))
    elif cmd == "untag":
        from . import zapi; print(zapi.remove_tags(args[0], args[1].split(","), _opt(args, "--why", "")))
    elif cmd == "collect":
        from . import zapi; print(zapi.add_collection(args[0], args[1]))
    elif cmd == "set":
        from . import zapi
        fields = dict(kv.split("=", 1) for kv in args[1:]); print(zapi.set_fields(args[0], fields))
    elif cmd == "recheck":
        from . import recheck
        only = set(_opt(args, "--only", "").split(",")) - {""} or None
        recheck.recheck(write="--write" in args, only=only, dates="--dates" in args, search="--search" in args)
    elif cmd == "discover":
        from . import discover
        discover.run(days=_opt(args, "--days", 7, int), cats=tuple(_opt(args, "--cat", "cs.RO").split(",")), query=_opt(args, "--query"),
                     tags=tuple(_opt(args, "--tags", "").split(",")), require_all="--all" in args,
                     sources=tuple(_opt(args, "--source", "arxiv,hf").split(",")), max_results=_opt(args, "--max", 400, int))
    elif cmd == "refs":
        from . import citations
        if "--library" in args: citations.library(top=_opt(args, "--top", 20, int))
        else: citations.one(args[0], top=_opt(args, "--top", 15, int))
    elif cmd == "dump":
        from . import localdb; localdb.dump(table="--table" in args)
    elif cmd == "setup":
        from . import setup_check; setup_check.run(args)
    elif cmd == "install":
        from . import install; install.run(args)
    else:
        print(f"unknown command {cmd!r}\n"); print(USAGE); sys.exit(2)
