"""New-machine health check (Ubuntu / macOS / Windows, standard library only, changes nothing):

    python zl.py setup [--sync-skills] [--offline]      # `python` on Windows, `python3` on Linux/macOS (./setup.sh picks one)

Checks, one by one: Python version, .env, Zotero data directory (auto-detected from prefs.js), taxonomy.toml, pdftotext / pypdf,
HTTPS, the Zotero desktop connector (port 23119), the Web API key (never printed), the classifier's adjudicator
(local LLM / agent / off), that .claude/skills mirrors .agents/skills (--sync-skills copies) and that every skill carries
the frontmatter the agents require. Every missing piece comes with the install / configuration command for this platform.
Exit code 1 = something is missing (a stale skill copy or bad frontmatter counts: the repository must stay consistent).

--offline keeps only the checks that need nothing but the repository (Python, taxonomy, pdftotext as a warning, skills):
CI runs it on Ubuntu / macOS / Windows for every pull request, and a contributor without a Zotero library runs it locally.
"""
import filecmp, json, os, shutil, ssl, stat, sys, urllib.error, urllib.request

from . import config                         # taxonomy / llm are imported inside the checks: a broken taxonomy.toml must be reported, not crash the import
from .http import UA_LOCAL

SKILLS_SRC, SKILLS_MIRROR = config.SKILLS_SRC, config.SKILLS_MIRROR
AGENTS = [("Claude Code", "claude", "/download <link>"), ("Codex", "codex", "$download <link>")]


def stale_skills():
    """Names of skills whose Claude Code copy differs from (or is missing next to) the .agents/skills source."""
    stale = []
    for name in sorted(os.listdir(SKILLS_SRC)) if os.path.isdir(SKILLS_SRC) else []:
        a, b = os.path.join(SKILLS_SRC, name, "SKILL.md"), os.path.join(SKILLS_MIRROR, name, "SKILL.md")
        if os.path.isfile(a) and not (os.path.isfile(b) and filecmp.cmp(a, b, shallow=False)): stale.append(name)
    return stale


def skill_problems():
    """Agent Skills format: frontmatter with `name` (= directory name, lowercase) and `description` — Codex refuses a skill without them."""
    out = []
    for name in sorted(os.listdir(SKILLS_SRC)) if os.path.isdir(SKILLS_SRC) else []:
        f = os.path.join(SKILLS_SRC, name, "SKILL.md")
        if not os.path.isfile(f): continue
        with open(f, encoding="utf-8") as h: head = h.read().split("\n---\n", 1)[0]
        if not head.startswith("---"): out.append(f"{name}: no frontmatter"); continue
        if f"name: {name}" not in head: out.append(f"{name}: frontmatter name must be {name!r}")
        if "description:" not in head: out.append(f"{name}: no description")
    return out


def sync_skills():
    for name in stale_skills():
        os.makedirs(os.path.join(SKILLS_MIRROR, name), exist_ok=True)
        shutil.copyfile(os.path.join(SKILLS_SRC, name, "SKILL.md"), os.path.join(SKILLS_MIRROR, name, "SKILL.md")); print(f"copied .agents/skills/{name}/SKILL.md -> .claude/skills/")

OK, BAD, WARN = "ok ", "x  ", "!  "
PY = "python" if config.IS_WIN else "python3"


def https(url, ua=UA_LOCAL, timeout=10):
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": ua}), timeout=timeout).status


def run(argv=()):
    offline = "--offline" in argv
    problems = []
    def report(ok, msg, fix=None, warn=False):
        print(f"{OK if ok else (WARN if warn else BAD)} {msg}" + (f"\n     -> {fix}" if fix and not ok else ""))
        if not ok and not warn: problems.append(msg)

    # 1. Python
    v = sys.version_info
    report(v >= (3, 11), f"Python {v.major}.{v.minor}.{v.micro} ({sys.executable}; standard library only)",
           "needs 3.11+ (tomllib): Ubuntu `sudo apt install python3`, macOS `brew install python`, Windows python.org or miniforge, with PATH")
    if config.IS_WIN:
        print("     Windows: where the docs say `python3 zl.py ...`, use `python zl.py ...` (or `py zl.py ...`)")

    env = config.load_env()
    if offline:
        print(f"{WARN} skipped (--offline): .env, Zotero data directory, HTTPS, desktop connector, Web API key, adjudicator")
    else:
        machine_checks(env, report)

    # 4. taxonomy
    try:
        from . import taxonomy as tx
        report(True, f"taxonomy.toml: {len(tx.COLLECTIONS)} collections, {sum(len(v) for v in tx.VOCAB.values())} tag values, {len(tx.VENUES)} venues")
    except Exception as e:
        report(False, f"taxonomy.toml failed to load: {e}", "fix the TOML syntax (python -c 'import tomllib; tomllib.load(open(\"taxonomy.toml\",\"rb\"))')")
        sys.exit(f"\nnothing else can be checked without the taxonomy; fix it and run `{PY} zl.py setup` again")

    # 5. pdftotext / pypdf
    if config.PDFTOTEXT:
        report(True, f"pdftotext {config.PDFTOTEXT}")
    else:
        try:
            import pypdf; report(True, f"pdftotext not found; using pypdf {pypdf.__version__} (works, slightly worse text)", warn=True)
        except ImportError:
            report(False, "no pdftotext and no pypdf: no full text, so no venue statements, project links or tag evidence",
                   config.PDFTOTEXT_INSTALL + "; if installed outside PATH, set PDFTOTEXT=<path> in .env", warn=offline)

    if not offline: service_checks(env, report)

    # 10. skills: Claude Code reads .claude/skills, everything else .agents/skills — the copies must match
    if "--sync-skills" in argv: sync_skills()
    stale = stale_skills(); bad = skill_problems()
    report(not stale, "skills: .claude/skills mirrors .agents/skills" if not stale else f"skills out of sync: {', '.join(stale)}", f"{PY} zl.py setup --sync-skills")
    report(not bad, "skills: frontmatter valid for every agent" if not bad else "skills: " + "; ".join(bad), "add `name: <dir>` and `description:` between --- lines at the top of SKILL.md")

    # 11. which agent CLIs are installed, and how each one runs a skill (nothing to configure: each reads its own files)
    found = [(name, syntax) for name, exe, syntax in AGENTS if shutil.which(exe)]
    if found: report(True, "agents on PATH: " + "; ".join(f"{n} -> {s}" for n, s in found))
    else: report(True, "no agent CLI on PATH (claude / codex) — install one, or point any agent that reads AGENTS.md at this directory", warn=True)

    print()
    if problems:
        print(f"{len(problems)} problem(s) above (x). Fix them and run `{PY} zl.py setup` again"); sys.exit(1)
    if offline: print("Repository checks pass (--offline: nothing about this machine's Zotero was checked)")
    else: print("All good: open your agent in this directory and use the download skill" + (f", e.g. {found[0][1]}" if found else ""))


def machine_checks(env, report):
    """2-3: credentials and the Zotero data directory (skipped with --offline)."""
    if os.path.exists(config.ENV_PATH):
        mode = stat.S_IMODE(os.stat(config.ENV_PATH).st_mode)
        perm_ok = config.IS_WIN or mode == 0o600
        report(True, ".env present" + ("" if config.IS_WIN else f" (mode {mode:o}{'' if perm_ok else ', should be 600'})"))
        if not perm_ok: report(False, ".env is not mode 600", f"chmod 600 {config.ENV_PATH}", warn=True)
        bad = config.cred_problems(env)                                    # a copied .env.example still holds the placeholder text: not "set"
        report("ZOTERO_API_KEY" not in bad, "ZOTERO_API_KEY " + bad.get("ZOTERO_API_KEY", "set"),
               "create one at https://www.zotero.org/settings/keys/new (tick Allow library access + Allow write access) and put ZOTERO_API_KEY=... in .env")
        report("ZOTERO_LIBRARY_ID" not in bad, "ZOTERO_LIBRARY_ID " + bad.get("ZOTERO_LIBRARY_ID", "set"),
               "your numeric user id is shown on https://www.zotero.org/settings/keys; put ZOTERO_LIBRARY_ID=... in .env (with a valid key, setup prints it below)")
    else:
        report(False, ".env missing", "cp .env.example .env (then chmod 600 .env on Linux/macOS) and fill ZOTERO_API_KEY / ZOTERO_LIBRARY_ID; the data directory is auto-detected")

    src = "from .env" if env.get("ZOTERO_DATA_DIR") else ("auto-detected from Zotero's prefs.js" if config.data_dir_from_prefs() else "platform default")
    if os.path.isfile(config.DB):
        report(True, f"Zotero database {config.DB} ({src})")
        try:
            con = config.connect_ro()
            n = con.execute("select count(*) from items where itemID not in (select itemID from deletedItems)").fetchone()[0]
            report(True, f"read-only open works ({n} items; fine while Zotero is running)")
        except Exception as e:
            report(False, f"sqlite read-only open failed: {e}", "make sure the path points at zotero.sqlite; on Windows write e.g. ZOTERO_DATA_DIR=C:\\Users\\you\\Zotero")
    else:
        hint = {"win32": r"Windows default C:\Users\<you>\Zotero", "darwin": "macOS default ~/Zotero"}.get(sys.platform, "Linux default ~/Zotero")
        report(False, f"{config.DB} not found ({src})",
               f"Zotero > Settings > Advanced > Files and Folders shows the data directory ({hint}); put ZOTERO_DATA_DIR=<dir> in .env. prefs.js candidates: {config.zotero_profile_prefs() or 'no Zotero profile found'}")


def service_checks(env, report):
    """6-9: network, the Zotero desktop connector, the Web API key and the adjudicator (skipped with --offline)."""
    # 6. HTTPS (python.org macOS installers ship without certificates; proxies show up here too)
    try:
        try: https("https://export.arxiv.org/api/query?search_query=id:2410.24164&max_results=1"); report(True, "HTTPS works (arXiv API)")
        except (urllib.error.HTTPError, TimeoutError, OSError) as e:                       # export.arxiv.org rate-limits (429 / timeouts); try the abs page
            if isinstance(e, urllib.error.URLError) and not isinstance(e, urllib.error.HTTPError): raise
            https("https://arxiv.org/abs/2410.24164"); report(True, f"HTTPS works (arXiv API rate-limited / timed out: {getattr(e, 'code', e)}; fetch falls back to abs pages)", warn=True)
    except urllib.error.URLError as e:
        if isinstance(e.reason, ssl.SSLError) or "CERTIFICATE" in str(e):
            fix = ("macOS python.org installer: run /Applications/Python 3.x/Install Certificates.command once; "
                   "otherwise: pip install certifi and export SSL_CERT_FILE=$(python -c 'import certifi;print(certifi.where())')")
            report(False, f"HTTPS certificate verification failed: {e.reason}", fix)
        else:
            report(False, f"HTTPS failed: {e.reason}", "check network / proxy (urllib honours HTTPS_PROXY)")
    except Exception as e:
        report(False, f"HTTPS failed: {e}", "check network / proxy")

    # 7. Zotero desktop connector
    try:
        st = https("http://127.0.0.1:23119/connector/ping", timeout=3)
        report(st == 200, "Zotero desktop is running (connector on 23119)")
    except Exception:
        report(False, "Zotero desktop not running (127.0.0.1:23119 unreachable)", "`zl.py add` needs it for the PDF; start Zotero. Ignore for dump / tidy / recheck", warn=True)

    # 8. Web API key (never printed); with a usable key but no usable id, the API says which user the key belongs to
    bad = config.cred_problems(env)
    hdr = {"Zotero-API-Key": env.get("ZOTERO_API_KEY", ""), "Zotero-API-Version": "3", "User-Agent": UA_LOCAL}
    if "ZOTERO_API_KEY" not in bad and "ZOTERO_LIBRARY_ID" in bad:
        try:
            js = json.loads(urllib.request.urlopen(urllib.request.Request("https://api.zotero.org/keys/current", headers=hdr), timeout=15).read())
            report(True, f"the API key belongs to user id {js.get('userID')} — put ZOTERO_LIBRARY_ID={js.get('userID')} in .env", warn=True)
        except urllib.error.HTTPError as e:
            report(False, f"Web API returned {e.code} for the key", "403 = key invalid (create one at https://www.zotero.org/settings/keys/new)")
        except Exception as e:
            report(False, f"Web API unreachable: {e}", "network problem, see above")
    elif not bad:
        try:
            req = urllib.request.Request(f"https://api.zotero.org/users/{env['ZOTERO_LIBRARY_ID']}/items?limit=1&format=keys", headers=hdr)
            r = urllib.request.urlopen(req, timeout=15)
            report(True, f"Web API key works (library {env['ZOTERO_LIBRARY_ID']}, server version {r.headers.get('Last-Modified-Version')})")
            from . import taxonomy as tx, zapi
            have, _ = zapi.remote_collections(env); missing = [c for c in tx.COLLECTIONS if c not in have]
            report(not missing, "the taxonomy's collections exist in the library" if not missing else f"collections from taxonomy.toml missing in the library: {', '.join(missing)}",
                   f"`{PY} zl.py tidy --create-collections` creates them (or create them in Zotero with exactly these names)", warn=True)
        except urllib.error.HTTPError as e:
            report(False, f"Web API returned {e.code}", "403 = key invalid or without write permission; 404 = ZOTERO_LIBRARY_ID wrong")
        except Exception as e:
            report(False, f"Web API unreachable: {e}", "network problem, see above")

    # 9. who adjudicates the borderline tags
    from . import llm
    cfg = llm.settings(); ok, msg = llm.available(cfg)
    if cfg["kind"] == "off": report(True, "adjudicator: none (ZC_LLM=off) — rules only, borderline tags are listed as candidates", warn=True)
    elif cfg["kind"] == "agent": report(True, "adjudicator: the coding agent (ZC_LLM=agent) — no local model, costs a few hundred tokens per paper", warn=True)
    else: report(ok, f"adjudicator: local model — {msg}", "install Ollama (https://ollama.com) and `ollama pull " + cfg["model"] + "`; or ZC_LLM=agent (the agent decides, costs tokens) / ZC_LLM=off in .env", warn=True)
