"""Global install: use the tool from any directory, in any agent.

    python3 zl.py install            # launcher `zl` on PATH + user-level copies of the skills for Claude Code / Codex
    python3 zl.py install --remove   # undo both

Nothing is copied but the launcher and the four SKILL.md files: the code, taxonomy.toml, .env, cache and logs stay in this
checkout, and the launcher just runs `<this python> <this checkout>/zl.py`. The user-level skills are the project skills
with `python3 zl.py` replaced by the launcher, so `/download <link>` works from a session opened anywhere. Re-run after
`git pull` if the skills changed (`zl.py setup` says when they are stale).
"""
import os, shutil, sys

from . import config

ROOT, SRC = config.ROOT, config.SKILLS_SRC
HOME = os.path.expanduser("~")
# user-level skill directories: Claude Code reads ~/.claude/skills; Codex reads ~/.agents/skills
USER_SKILL_DIRS = [os.path.join(HOME, ".claude", "skills"), os.path.join(HOME, ".agents", "skills")]
MARK = "<!-- installed by zl.py install from "


def launcher_path():
    if config.IS_WIN:                                            # %LOCALAPPDATA%\Microsoft\WindowsApps is on PATH by default
        return os.path.join(os.environ.get("LOCALAPPDATA", os.path.join(HOME, "AppData", "Local")), "Microsoft", "WindowsApps", "zl.cmd")
    return os.path.join(HOME, ".local", "bin", "zl")


def on_path(p):
    return os.path.normcase(os.path.dirname(p)) in [os.path.normcase(os.path.normpath(x)) for x in os.environ.get("PATH", "").split(os.pathsep)]


def write_launcher():
    p = launcher_path(); os.makedirs(os.path.dirname(p), exist_ok=True)
    py, entry = sys.executable, os.path.join(ROOT, "zl.py")
    if config.IS_WIN:
        with open(p, "w", encoding="utf-8", newline="") as f: f.write(f'@echo off\r\n"{py}" "{entry}" %*\r\n')   # newline="" keeps the explicit CRLF as written (newline="\r\n" would make it \r\r\n)
    else:
        with open(p, "w", encoding="utf-8") as f: f.write(f'#!/bin/sh\nexec "{py}" "{entry}" "$@"\n')
        os.chmod(p, 0o755)
    return p


def command_for_skills(launcher):
    """What the user-level skills run: the launcher name if its directory is on PATH, else the full command."""
    if on_path(launcher): return "zl"
    return f'"{sys.executable}" "{os.path.join(ROOT, "zl.py")}"'


def install_skills(cmd):
    done = []
    for name in sorted(os.listdir(SRC)):
        src = os.path.join(SRC, name, "SKILL.md")
        if not os.path.isfile(src): continue
        with open(src, encoding="utf-8") as f: text = f.read().replace("python3 zl.py", cmd)
        text = text.replace("\n---\n", f"\n---\n{MARK}{ROOT} -->\n", 1)    # after the frontmatter; lets --remove recognise our copies
        for d in USER_SKILL_DIRS:
            os.makedirs(os.path.join(d, name), exist_ok=True)
            with open(os.path.join(d, name, "SKILL.md"), "w", encoding="utf-8") as f: f.write(text)
            done.append(os.path.join(d, name))
    return done


def remove():
    p = launcher_path()
    if os.path.exists(p): os.remove(p); print(f"removed {p}")
    for d in USER_SKILL_DIRS:
        for name in (sorted(os.listdir(d)) if os.path.isdir(d) else []):
            f = os.path.join(d, name, "SKILL.md")
            if not os.path.isfile(f): continue
            with open(f, encoding="utf-8") as h: ours = MARK in h.read()
            if ours: shutil.rmtree(os.path.join(d, name)); print(f"removed {os.path.join(d, name)}")
        for x in (d, os.path.dirname(d)):                                        # directories we may have created, if now empty
            if os.path.isdir(x) and not os.listdir(x): os.rmdir(x)


def run(argv=()):
    if "--remove" in argv: remove(); return
    p = write_launcher(); cmd = command_for_skills(p)
    print(f"launcher  : {p}" + ("" if cmd == "zl" else f"  (its directory is not on PATH — the skills use the full command instead; add it to PATH and re-run to get `zl`)"))
    for d in install_skills(cmd): print(f"skill     : {d}")
    print(f"\nFrom any directory: `{cmd} add <link>` or, in an agent session, /download <link> (Claude Code) or $download (Codex).")
    print("Configuration stays in this checkout (.env, taxonomy.toml, cache/, logs/). Undo with `python3 zl.py install --remove`.")
