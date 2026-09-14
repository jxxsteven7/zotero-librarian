"""新机器体检（Ubuntu / macOS / Windows 通用，只用标准库，不改任何东西）：

    python zc.py setup       # Windows 一般叫 python；Linux/macOS 叫 python3（./setup.sh 会自己挑）

逐项检查：Python 版本、.env、Zotero 数据目录（自动从 prefs.js 探测）、pdftotext / pypdf、HTTPS 证书、
Zotero 桌面端 connector（23119）、Web API key 是否可用（不打印 key）。缺什么就打印对应平台的安装/配置命令。退出码 1 = 有缺项。
"""
import os, ssl, stat, sys, urllib.error, urllib.request

from . import config

OK, BAD, WARN = "✓", "✗", "⚠"
PY = "python" if config.IS_WIN else "python3"


def https(url, ua="zotero-claude/1.0", timeout=10):
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": ua}), timeout=timeout).status


def run(argv=()):
    problems = []
    def report(ok, msg, fix=None, warn=False):
        print(f"{OK if ok else (WARN if warn else BAD)} {msg}" + (f"\n    → {fix}" if fix and not ok else ""))
        if not ok and not warn: problems.append(msg)

    # 1. Python
    v = sys.version_info
    report(v >= (3, 8), f"Python {v.major}.{v.minor}.{v.micro}（{sys.executable}；只用标准库）",
           "需要 3.8+：Ubuntu `sudo apt install python3`，macOS `brew install python`，Windows 装 python.org 或 miniforge 并勾选加入 PATH")
    if config.IS_WIN:
        print(f"    Windows 提示：文档里写的 `python3 xxx.py` 在这里通常要写成 `python xxx.py`（或 `py xxx.py`）")

    # 2. .env
    env = config.load_env()
    if os.path.exists(config.ENV_PATH):
        mode = stat.S_IMODE(os.stat(config.ENV_PATH).st_mode)
        perm_ok = config.IS_WIN or mode == 0o600
        report(True, f".env 存在" + ("" if config.IS_WIN else f"（权限 {mode:o}，应为 600）"))
        if not perm_ok: report(False, ".env 权限不是 600", f"chmod 600 {config.ENV_PATH}", warn=True)
        report(bool(env.get("ZOTERO_API_KEY")), "ZOTERO_API_KEY 已填",
               "在 https://www.zotero.org/settings/keys 新建（个人库 读/写 + 文件访问），写进 .env 的 ZOTERO_API_KEY=")
    else:
        report(False, "缺 .env", "cp .env.example .env（Linux/macOS 再 chmod 600 .env），填 ZOTERO_API_KEY；数据目录不填会自动探测")

    # 3. Zotero 数据目录
    src = "来自 .env" if env.get("ZOTERO_DATA_DIR") else ("来自 Zotero prefs.js 自动探测" if config.data_dir_from_prefs() else "平台默认")
    if os.path.isfile(config.DB):
        report(True, f"Zotero 库 {config.DB}（{src}）")
        try:
            con = config.connect_ro()
            n = con.execute("select count(*) from items where itemID not in (select itemID from deletedItems)").fetchone()[0]
            report(True, f"只读打开成功（{n} 条 items，Zotero 开着也能读）")
        except Exception as e:
            report(False, f"sqlite 只读打开失败：{e}", "确认路径指向 zotero.sqlite 本体；Windows 路径写法如 ZOTERO_DATA_DIR=C:\\Users\\你\\Zotero")
    else:
        hint = {"win32": r"Windows 默认 C:\Users\<你>\Zotero", "darwin": "macOS 默认 ~/Zotero"}.get(sys.platform, "Linux 默认 ~/Zotero")
        report(False, f"找不到 {config.DB}（{src}）",
               f"Zotero 编辑→设置→高级→文件和文件夹 看数据目录（{hint}），写进 .env：ZOTERO_DATA_DIR=<目录>；prefs.js 候选：{config.zotero_profile_prefs() or '未找到 Zotero 配置'}")

    # 4. pdftotext / pypdf
    if config.PDFTOTEXT:
        report(True, f"pdftotext {config.PDFTOTEXT}")
    else:
        try:
            import pypdf; report(True, f"pdftotext 没找到，退到 pypdf {pypdf.__version__}（能用，抽文本质量略差）", warn=True)
        except ImportError:
            report(False, "缺 pdftotext（也没有 pypdf）：/download 抽不了正文，标签判定和刊/会查询会缺证据",
                   config.PDFTOTEXT_INSTALL + "；装在非 PATH 位置就在 .env 写 PDFTOTEXT=<可执行文件路径>")

    # 5. HTTPS（macOS python.org 安装包默认没证书；公司/校园代理也在这里暴露）
    try:
        try: https("https://export.arxiv.org/api/query?search_query=id:2410.24164&max_results=1"); report(True, "HTTPS 出网正常（arXiv API）")
        except (urllib.error.HTTPError, TimeoutError, OSError) as e:                       # export.arxiv.org 常限流（429/超时），换 abs 页面再试
            if isinstance(e, urllib.error.URLError) and not isinstance(e, urllib.error.HTTPError): raise
            https("https://arxiv.org/abs/2410.24164"); report(True, f"HTTPS 出网正常（arXiv API 被限流/超时：{getattr(e, 'code', e)}，fetch 会自动改抓 abs 页面）", warn=True)
    except urllib.error.URLError as e:
        if isinstance(e.reason, ssl.SSLError) or "CERTIFICATE" in str(e):
            fix = ("macOS python.org 安装包：跑一次 /Applications/Python 3.x/Install Certificates.command；"
                   "其他情况：pip install certifi 然后 export SSL_CERT_FILE=$(python -c 'import certifi;print(certifi.where())')")
            report(False, f"HTTPS 证书校验失败：{e.reason}", fix)
        else:
            report(False, f"HTTPS 出网失败：{e.reason}", "检查网络/代理（urllib 认 HTTPS_PROXY 环境变量）")
    except Exception as e:
        report(False, f"HTTPS 出网失败：{e}", "检查网络/代理")

    # 6. Zotero 桌面端 connector
    try:
        st = https("http://127.0.0.1:23119/connector/ping", timeout=3)
        report(st == 200, "Zotero 桌面端在跑（connector 23119）")
    except Exception:
        report(False, "Zotero 桌面端没开（127.0.0.1:23119 不通）", "/download 入库需要它；先开 Zotero。这项在只跑 dump/apply/recheck 时可以忽略", warn=True)

    # 7. Web API key 可用性（不打印 key）
    if env.get("ZOTERO_API_KEY"):
        try:
            req = urllib.request.Request(f"https://api.zotero.org/users/{config.LIBRARY_ID}/items?limit=1&format=keys",
                                         headers={"Zotero-API-Key": env["ZOTERO_API_KEY"], "Zotero-API-Version": "3", "User-Agent": "zotero-claude/1.0"})
            r = urllib.request.urlopen(req, timeout=15)
            report(True, f"Web API key 可用（库 {config.LIBRARY_ID}，远端 version {r.headers.get('Last-Modified-Version')}）")
        except urllib.error.HTTPError as e:
            report(False, f"Web API 返回 {e.code}", "403 = key 无效或没勾读写权限；404 = ZOTERO_LIBRARY_ID 不对")
        except Exception as e:
            report(False, f"Web API 连不上：{e}", "网络问题，同上一项")

    print()
    if problems:
        print(f"还差 {len(problems)} 项（见上面 ✗）。修好后再跑一次 {PY} zc.py setup"); sys.exit(1)
    print(f"都齐了：在这个目录开 claude，/download <链接>")
