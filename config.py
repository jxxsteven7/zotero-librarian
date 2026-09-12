"""本机配置：全部来自同目录 .env（不进 git）。其他脚本只从这里拿路径、凭据和外部程序。
Ubuntu / macOS / Windows 三个平台通用，只用标准库。

.env 支持的键（KEY=VALUE 一行一个；也兼容整个文件只写一个裸 API key）：
  ZOTERO_API_KEY     Zotero Web API key（zotero.org/settings/keys，需个人库读写 + 文件权限）
  ZOTERO_LIBRARY_ID  用户库 ID，默认 14568484
  ZOTERO_DATA_DIR    Zotero 数据目录。不写就自动从 Zotero 的 prefs.js 里读 extensions.zotero.dataDir，
                     再不行用各平台默认（Linux/macOS ~/Zotero，Windows %USERPROFILE%\\Zotero）
  PDFTOTEXT          pdftotext 可执行文件路径。不写就在 PATH 和常见安装位置里找
"""
import glob, os, re, shutil, sys
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(HERE, ".env")
IS_WIN = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"

# Windows 上 stdout 被管道接走时默认是本地代码页（GBK），打印 ✓ ⚠ − 会直接 UnicodeEncodeError；统一成 UTF-8
for _s in (sys.stdout, sys.stderr):
    if _s and hasattr(_s, "reconfigure") and (_s.encoding or "").lower().replace("-", "") != "utf8":
        _s.reconfigure(encoding="utf-8", errors="replace")


def load_env():
    env = {}
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH, encoding="utf-8") as f: raw = f.read()
        for line in raw.splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1); env[k.strip()] = v.strip().strip('"').strip("'")
        if "ZOTERO_API_KEY" not in env and re.fullmatch(r"[A-Za-z0-9]{20,40}", raw.strip()):
            env["ZOTERO_API_KEY"] = raw.strip()   # 允许只写裸 key
    env.setdefault("ZOTERO_LIBRARY_ID", "14568484")
    return env


# ---------- Zotero 数据目录 ----------
def zotero_profile_prefs():
    """各平台 Zotero 配置文件 prefs.js 的候选路径（存在的）。"""
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
            d = re.sub(r"\\u([0-9a-fA-F]{4})", lambda u: chr(int(u.group(1), 16)), m.group(1))   # prefs.js 里 Windows 路径写成 C:\\Users\\…
            d = re.sub(r"\\(.)", r"\1", d)
            if os.path.isdir(d): return d
    return None


def default_data_dir():
    return os.path.join(os.environ.get("USERPROFILE", os.path.expanduser("~")), "Zotero") if IS_WIN else os.path.expanduser("~/Zotero")


def sqlite_ro_uri(path):
    """只读 + immutable 打开的 sqlite URI。Windows 路径要写成 file:///C:/…，Path.as_uri() 三个平台都对。"""
    return Path(path).resolve().as_uri() + "?mode=ro&immutable=1"


def connect_ro(path=None):
    """只读打开 Zotero 库，Zotero 运行中也能用。
    Zotero 10 起数据库是 WAL 模式（zotero.sqlite-wal），immutable 只读主文件会看到旧数据；而普通只读打开又被 Zotero 的
    exclusive 锁挡住（database is locked）。所以有 WAL 时把主文件 + WAL 拷到临时目录再打开拷贝，SQLite 自己把 WAL 应用上去。
    拷贝前后核对两个文件的 mtime/size 没变才算一致快照，变了就重拷。"""
    import shutil, sqlite3, tempfile, atexit
    path = path or DB
    wal = path + "-wal"
    if not (os.path.exists(wal) and os.path.getsize(wal) > 0):
        return sqlite3.connect(sqlite_ro_uri(path), uri=True)
    d = tempfile.mkdtemp(prefix="zotero-ro-"); atexit.register(shutil.rmtree, d, True)
    for _ in range(5):
        st = lambda: tuple((os.stat(f).st_mtime_ns, os.stat(f).st_size) for f in (path, wal))
        before = st()
        shutil.copyfile(path, os.path.join(d, "zotero.sqlite")); shutil.copyfile(wal, os.path.join(d, "zotero.sqlite-wal"))
        if st() == before: break
    con = sqlite3.connect(os.path.join(d, "zotero.sqlite"))
    con.execute("pragma quick_check").fetchone()
    return con


# ---------- pdftotext ----------
def find_pdftotext(explicit=None):
    """返回 pdftotext 可执行文件路径；找不到返回 None（download.py 会退到 pypdf）。"""
    exe = "pdftotext.exe" if IS_WIN else "pdftotext"
    cands = [explicit] if explicit else []
    cands.append(shutil.which("pdftotext"))
    # conda（当前解释器所在环境）：Windows 装在 Library\bin，Linux/macOS 在 bin
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
                     "Windows: winget install --id oschwartz10612.Poppler -e（或 scoop/choco install poppler；装完重开终端）   "
                     "任一平台的 conda 环境: conda install -c conda-forge poppler；"
                     "都不想装就 pip install pypdf（纯 Python 退路，抽文本质量略差）")

_env = load_env()
DATA_DIR = os.path.expanduser(_env.get("ZOTERO_DATA_DIR") or data_dir_from_prefs() or default_data_dir())
DB = os.path.join(DATA_DIR, "zotero.sqlite")
STORAGE = os.path.join(DATA_DIR, "storage")
LIBRARY_ID = _env["ZOTERO_LIBRARY_ID"]
PDFTOTEXT = find_pdftotext(_env.get("PDFTOTEXT"))
