"""New-machine health check (Ubuntu / macOS / Windows, standard library only, changes nothing):

    python zc.py setup       # `python` on Windows, `python3` on Linux/macOS (./setup.sh picks one)

Checks, one by one: Python version, .env, Zotero data directory (auto-detected from prefs.js), pdftotext / pypdf,
HTTPS, the Zotero desktop connector (port 23119), the Web API key (never printed), the local LLM. Every missing piece
comes with the install / configuration command for this platform. Exit code 1 = something is missing.
"""
import os, ssl, stat, sys, urllib.error, urllib.request

from . import config, llm

OK, BAD, WARN = "ok ", "x  ", "!  "
PY = "python" if config.IS_WIN else "python3"


def https(url, ua="zotero-claude/1.0", timeout=10):
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": ua}), timeout=timeout).status


def run(argv=()):
    problems = []
    def report(ok, msg, fix=None, warn=False):
        print(f"{OK if ok else (WARN if warn else BAD)} {msg}" + (f"\n     -> {fix}" if fix and not ok else ""))
        if not ok and not warn: problems.append(msg)

    # 1. Python
    v = sys.version_info
    report(v >= (3, 11), f"Python {v.major}.{v.minor}.{v.micro} ({sys.executable}; standard library only)",
           "needs 3.11+ (tomllib): Ubuntu `sudo apt install python3`, macOS `brew install python`, Windows python.org or miniforge, with PATH")
    if config.IS_WIN:
        print("     Windows: where the docs say `python3 zc.py ...`, use `python zc.py ...` (or `py zc.py ...`)")

    # 2. .env
    env = config.load_env()
    if os.path.exists(config.ENV_PATH):
        mode = stat.S_IMODE(os.stat(config.ENV_PATH).st_mode)
        perm_ok = config.IS_WIN or mode == 0o600
        report(True, ".env present" + ("" if config.IS_WIN else f" (mode {mode:o}, should be 600)"))
        if not perm_ok: report(False, ".env is not mode 600", f"chmod 600 {config.ENV_PATH}", warn=True)
        report(bool(env.get("ZOTERO_API_KEY")), "ZOTERO_API_KEY set",
               "create one at https://www.zotero.org/settings/keys (personal library read/write + file access) and put ZOTERO_API_KEY=... in .env")
        report(bool(env.get("ZOTERO_LIBRARY_ID")), "ZOTERO_LIBRARY_ID set", "your user id is shown on https://www.zotero.org/settings/keys; put ZOTERO_LIBRARY_ID=... in .env")
    else:
        report(False, ".env missing", "cp .env.example .env (then chmod 600 .env on Linux/macOS) and fill ZOTERO_API_KEY / ZOTERO_LIBRARY_ID; the data directory is auto-detected")

    # 3. Zotero data directory
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

    # 4. taxonomy
    try:
        from . import taxonomy as tx
        report(True, f"taxonomy.toml: {len(tx.COLLECTIONS)} collections, {sum(len(v) for v in tx.VOCAB.values())} tag values, {len(tx.VENUES)} venues")
    except Exception as e:
        report(False, f"taxonomy.toml failed to load: {e}", "fix the TOML syntax (python -c 'import tomllib; tomllib.load(open(\"taxonomy.toml\",\"rb\"))')")

    # 5. pdftotext / pypdf
    if config.PDFTOTEXT:
        report(True, f"pdftotext {config.PDFTOTEXT}")
    else:
        try:
            import pypdf; report(True, f"pdftotext not found; using pypdf {pypdf.__version__} (works, slightly worse text)", warn=True)
        except ImportError:
            report(False, "no pdftotext and no pypdf: no full text, so no venue statements, project links or tag evidence",
                   config.PDFTOTEXT_INSTALL + "; if installed outside PATH, set PDFTOTEXT=<path> in .env")

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
        report(False, "Zotero desktop not running (127.0.0.1:23119 unreachable)", "`zc.py add` needs it for the PDF; start Zotero. Ignore for dump / tidy / recheck", warn=True)

    # 8. Web API key (never printed)
    if env.get("ZOTERO_API_KEY") and env.get("ZOTERO_LIBRARY_ID"):
        try:
            req = urllib.request.Request(f"https://api.zotero.org/users/{config.LIBRARY_ID}/items?limit=1&format=keys",
                                         headers={"Zotero-API-Key": env["ZOTERO_API_KEY"], "Zotero-API-Version": "3", "User-Agent": "zotero-claude/1.0"})
            r = urllib.request.urlopen(req, timeout=15)
            report(True, f"Web API key works (library {config.LIBRARY_ID}, server version {r.headers.get('Last-Modified-Version')})")
        except urllib.error.HTTPError as e:
            report(False, f"Web API returned {e.code}", "403 = key invalid or without write permission; 404 = ZOTERO_LIBRARY_ID wrong")
        except Exception as e:
            report(False, f"Web API unreachable: {e}", "network problem, see above")

    # 9. local LLM
    cfg = llm.settings(); ok, msg = llm.available(cfg)
    if cfg["kind"] == "off": report(True, "local LLM disabled (ZC_LLM=off): rules-only classification", warn=True)
    else: report(ok, f"local LLM: {msg}", "install Ollama (https://ollama.com), `ollama pull " + cfg["model"] + "`, or set ZC_LLM=off / ZC_LLM_URL in .env", warn=True)

    print()
    if problems:
        print(f"{len(problems)} problem(s) above (x). Fix them and run `{PY} zc.py setup` again"); sys.exit(1)
    print(f"All good: run `claude` in this directory and use /download <link>")
