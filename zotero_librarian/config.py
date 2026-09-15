"""Machine configuration and repository paths. Credentials come from the repo-root .env (not in git); other modules
take paths, credentials and external programs only from here. Ubuntu / macOS / Windows, standard library only.

Layout (ROOT = the parent of this package):
  taxonomy.toml                  collections, tag vocabulary, classification rules, venue abbreviations
  inbox/                         fetch staging area (json/pdf/txt), cleared after saving, not in git
  cache/library_dump.json        library snapshot from `zl.py dump`, not in git
  logs/zotero-organize.log.md    audit log of every write (local, not in git)

.env keys (KEY=VALUE per line):
  ZOTERO_API_KEY     Zotero Web API key (zotero.org/settings/keys/new; Allow library access + Allow write access)
  ZOTERO_LIBRARY_ID  your user library id (zotero.org/settings/keys shows it)
  ZOTERO_DATA_DIR    Zotero data directory; if unset, read from Zotero's prefs.js (extensions.zotero.dataDir),
                     else the platform default (~/Zotero, Windows %USERPROFILE%\\Zotero)
  PDFTOTEXT          path to the pdftotext executable; if unset, searched on PATH and common install locations
  ZC_LLM / ZC_LLM_MODEL / ZC_LLM_URL / ZC_LLM_KEY   local model for classification (see llm.py)
"""
import atexit, glob, os, re, shutil, sqlite3, sys, tempfile
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                                   # repository root
ENV_PATH = os.path.join(ROOT, ".env")
INBOX = os.path.join(ROOT, "inbox")
CACHE = os.path.join(ROOT, "cache")
DUMP = os.path.join(CACHE, "library_dump.json")
LOG = os.path.join(ROOT, "logs", "zotero-organize.log.md")
TAXONOMY_PATH = os.path.join(ROOT, "taxonomy.toml")
SKILLS_SRC = os.path.join(ROOT, ".agents", "skills")           # the skills (Agent Skills format; Codex and others read this)
SKILLS_MIRROR = os.path.join(ROOT, ".claude", "skills")        # verbatim copy — the only place Claude Code looks
IS_WIN = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"

# on Windows a piped stdout defaults to the local code page; printing non-ASCII would raise — force UTF-8
for _s in (sys.stdout, sys.stderr):
    if _s and hasattr(_s, "reconfigure") and (_s.encoding or "").lower().replace("-", "") != "utf8":
        _s.reconfigure(encoding="utf-8", errors="replace")


LOG_HEADER = """# Audit log

Every write to the library is appended here by the scripts (`zl.py add / tidy / tag / untag / collect / set / recheck --write`),
one section per action: `## <date> — <action>` followed by `- <key> | <title> | what changed`. Local to this machine, not in git.
"""


def append_log(*lines):
    """Append to the audit log; the file (and logs/) is created with a header on first use."""
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    new = not os.path.exists(LOG)
    with open(LOG, "a", encoding="utf-8") as f: f.write((LOG_HEADER if new else "") + "\n" + "\n".join(lines) + "\n")


def load_env(path=ENV_PATH):
    env = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f: lines = f.read().splitlines()
        for line in lines:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1); env[k.strip()] = v.strip().strip('"').strip("'")
    env.setdefault("ZOTERO_LIBRARY_ID", "")
    return env


def cred_problems(env):
    """{variable: what is wrong} for the Web API credentials in .env — missing, or still the .env.example placeholder text
    (a real key is one token without spaces, a library id is a number). Empty = usable. Never includes the key's value."""
    out = {}
    key, lib = env.get("ZOTERO_API_KEY", ""), env.get("ZOTERO_LIBRARY_ID", "")
    if not key: out["ZOTERO_API_KEY"] = "missing"
    elif re.search(r"\s", key): out["ZOTERO_API_KEY"] = "is still the .env.example placeholder text"
    if not lib: out["ZOTERO_LIBRARY_ID"] = "missing"
    elif not lib.isdigit(): out["ZOTERO_LIBRARY_ID"] = f"must be your numeric user id, not {lib[:40]!r}"
    return out


# ---------- Zotero data directory ----------
def zotero_profile_prefs():
    """Existing prefs.js candidates for each platform's Zotero profile."""
    if IS_WIN: pats = [os.path.join(os.environ.get("APPDATA", ""), "Zotero", "Zotero", "Profiles", "*", "prefs.js")]
    elif IS_MAC: pats = [os.path.expanduser("~/Library/Application Support/Zotero/Profiles/*/prefs.js")]
    else: pats = [os.path.expanduser("~/.zotero/zotero/*/prefs.js"), os.path.expanduser("~/snap/zotero-snap/common/Zotero/*/prefs.js")]
    return [p for pat in pats for p in glob.glob(pat)]


def data_dir_from_prefs():
    for p in zotero_profile_prefs():
        try:
            with open(p, encoding="utf-8", errors="replace") as f: s = f.read()
        except OSError: continue
        m = re.search(r'user_pref\("extensions\.zotero\.dataDir",\s*"((?:[^"\\]|\\.)*)"\)', s)
        if m:
            d = re.sub(r"\\u([0-9a-fA-F]{4})", lambda u: chr(int(u.group(1), 16)), m.group(1))   # prefs.js escapes Windows paths as C:\\Users\\...
            d = re.sub(r"\\(.)", r"\1", d)
            if os.path.isdir(d): return d
    return None


def default_data_dir():
    return os.path.join(os.environ.get("USERPROFILE", os.path.expanduser("~")), "Zotero") if IS_WIN else os.path.expanduser("~/Zotero")


def sqlite_ro_uri(path):
    """sqlite URI for read-only immutable access; Path.as_uri() produces file:///C:/... correctly on every platform."""
    return Path(path).resolve().as_uri() + "?mode=ro&immutable=1"


_SNAPSHOT = {}                                                 # path -> (signature, connection, temp dir): one copy per library state


def connect_ro(path=None):
    """Open the Zotero database read-only, even while Zotero is running.
    Since Zotero 10 the database is in WAL mode (zotero.sqlite-wal): an immutable open of the main file sees stale data,
    and a normal read-only open hits Zotero's exclusive lock. So when a WAL exists, copy main file + WAL to a temporary
    directory and open the copy — SQLite applies the WAL itself. The copy is retried until mtime/size are unchanged
    before and after, i.e. a consistent snapshot, and reused by every later call until either file changes (a save through
    the connector grows the WAL, so the poll that reads the new item back still copies afresh)."""
    path = path or DB
    wal = path + "-wal"
    if not (os.path.exists(wal) and os.path.getsize(wal) > 0):
        return sqlite3.connect(sqlite_ro_uri(path), uri=True)
    sig = lambda: tuple((os.stat(f).st_mtime_ns, os.stat(f).st_size) for f in (path, wal))
    old = _SNAPSHOT.get(path)
    if old and old[0] == sig(): return old[1]
    d = tempfile.mkdtemp(prefix="zotero-ro-")
    for _ in range(5):
        before = sig()
        shutil.copyfile(path, os.path.join(d, "zotero.sqlite")); shutil.copyfile(wal, os.path.join(d, "zotero.sqlite-wal"))
        if sig() == before: break
    con = sqlite3.connect(os.path.join(d, "zotero.sqlite"))
    con.execute("pragma quick_check").fetchone()
    if old: old[1].close(); shutil.rmtree(old[2], True)
    else: atexit.register(_drop_snapshot, path)
    _SNAPSHOT[path] = (before, con, d)
    return con


def _drop_snapshot(path):
    s = _SNAPSHOT.pop(path, None)
    if s: s[1].close(); shutil.rmtree(s[2], True)


# ---------- pdftotext ----------
def find_pdftotext(explicit=None):
    """Path of the pdftotext executable, or None (pdf.py then falls back to pypdf)."""
    exe = "pdftotext.exe" if IS_WIN else "pdftotext"
    cands = [explicit] if explicit else []
    cands.append(shutil.which("pdftotext"))
    # conda (the running interpreter's environment): Library\bin on Windows, bin elsewhere
    cands += [os.path.join(sys.prefix, "Library", "bin", exe), os.path.join(sys.prefix, "bin", exe)]
    if IS_WIN:
        cands += glob.glob(r"C:\Program Files\poppler*\Library\bin\pdftotext.exe") + glob.glob(r"C:\poppler*\Library\bin\pdftotext.exe") \
               + glob.glob(os.path.expanduser(r"~\scoop\apps\poppler\current\Library\bin\pdftotext.exe")) \
               + glob.glob(r"C:\ProgramData\chocolatey\lib\poppler\tools\*\Library\bin\pdftotext.exe") \
               + glob.glob(os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WinGet", "Packages", "oschwartz10612.Poppler*", "poppler*", "Library", "bin", "pdftotext.exe")) \
               + glob.glob(os.path.expanduser(r"~\miniforge3\Library\bin\pdftotext.exe")) + glob.glob(os.path.expanduser(r"~\miniconda3\Library\bin\pdftotext.exe"))
    elif IS_MAC:
        cands += ["/opt/homebrew/bin/pdftotext", "/usr/local/bin/pdftotext", "/opt/local/bin/pdftotext"]
        cands += glob.glob(os.path.expanduser("~/miniforge3/bin/pdftotext")) + glob.glob(os.path.expanduser("~/miniconda3/bin/pdftotext"))
    else:
        cands += ["/usr/bin/pdftotext", "/usr/local/bin/pdftotext", "/snap/bin/pdftotext"]
        cands += glob.glob(os.path.expanduser("~/miniforge3/bin/pdftotext")) + glob.glob(os.path.expanduser("~/miniconda3/bin/pdftotext"))
    for c in cands:
        if c and os.path.isfile(os.path.expanduser(c)): return os.path.expanduser(c)
    return None


PDFTOTEXT_INSTALL = ("Ubuntu: sudo apt install poppler-utils   macOS: brew install poppler   "
                     "Windows: winget install --id oschwartz10612.Poppler -e (or scoop/choco install poppler; reopen the terminal)   "
                     "any conda environment: conda install -c conda-forge poppler; "
                     "or pip install pypdf (pure-Python fallback, slightly worse text)")

_env = load_env()
DATA_DIR = os.path.expanduser(_env.get("ZOTERO_DATA_DIR") or data_dir_from_prefs() or default_data_dir())
DB = os.path.join(DATA_DIR, "zotero.sqlite")
STORAGE = os.path.join(DATA_DIR, "storage")
PDFTOTEXT = find_pdftotext(_env.get("PDFTOTEXT"))
