#!/usr/bin/env python3
"""The version rule of AGENTS.md, checked on a range of commits (CI runs it on every push / PR; run it before pushing):

    python3 tools/check_commits.py [<rev-range>]        default: origin/main..HEAD

A commit that touches behaviour (zl.py, zotero_librarian/, taxonomy.toml, the skills) must be titled `vX.Y: ...`; such a
title must come with `__version__ = "X.Y"` and a `**vX.Y**` entry in CHANGELOG.md; and only such a commit may change
`__version__`. Each commit is checked against its own tree, so a push with v0.5 followed by v0.6 passes. Merge commits
are skipped. Exit 1 with one line per violation."""
import re, subprocess, sys

INIT, CHANGELOG = "zotero_librarian/__init__.py", "CHANGELOG.md"
BEHAVIOUR = ("zl.py", "zotero_librarian/", "taxonomy.toml", ".agents/skills/", ".claude/skills/")


def git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True, encoding="utf-8", check=True).stdout


def file_at(rev, path):
    try: return git("show", f"{rev}:{path}")
    except subprocess.CalledProcessError: return ""          # root commit's parent, or the file did not exist yet


def version_at(rev):
    m = re.search(r'__version__\s*=\s*"([^"]+)"', file_at(rev, INIT))
    return m.group(1) if m else None


def check(sha):
    title = git("log", "-1", "--format=%s", sha).strip()
    ver, prev = version_at(sha), version_at(sha + "^")
    m = re.match(r"v(\d+\.\d+):", title)
    problems = []
    if m:
        want = m.group(1)
        if ver != want: problems.append(f"title says v{want} but {INIT} has __version__ = {ver!r}")
        if f"**v{want}**" not in file_at(sha, CHANGELOG): problems.append(f"{CHANGELOG} has no **v{want}** entry")
    elif prev is not None and ver != prev:
        problems.append(f"changes __version__ {prev} -> {ver} but the title does not start with `v{ver}:`")
    elif prev is not None:
        touched = [f for f in git("show", "--format=", "--name-only", sha).split() if f.startswith(BEHAVIOUR)]
        if touched: problems.append(f"touches {touched[0]}{' ...' if len(touched) > 1 else ''} without a `vX.Y:` title")
    return [(sha[:7], title, p) for p in problems]


def main(argv):
    rng = argv[0] if argv else "origin/main..HEAD"
    try: shas = git("rev-list", "--no-merges", rng).split()
    except subprocess.CalledProcessError:                    # unknown base (new branch, force push, no origin): the tip only
        shas = git("rev-list", "--no-merges", "-1", rng.split("..")[-1] or "HEAD").split()
    bad = [p for sha in shas for p in check(sha)]
    for sha, title, p in bad: print(f"x {sha} {title[:60]}: {p}")
    print(f"{len(shas)} commit(s) checked, {len(bad)} problem(s)")
    sys.exit(1 if bad else 0)


if __name__ == "__main__": main(sys.argv[1:])
