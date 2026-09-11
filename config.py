"""本机配置：全部来自同目录 .env（不进 git）。其他脚本只从这里拿路径和凭据。

.env 支持的键（KEY=VALUE 一行一个；也兼容整个文件只写一个裸 API key）：
  ZOTERO_API_KEY     Zotero Web API key（zotero.org/settings/keys，需个人库读写 + 文件权限）
  ZOTERO_LIBRARY_ID  用户库 ID，默认 14568484
  ZOTERO_DATA_DIR    Zotero 数据目录，默认 ~/Zotero（本机是 ~/Documents/Zotero；看 prefs.js 的 extensions.zotero.dataDir）
"""
import os, re

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(HERE, ".env")


def load_env():
    env = {}
    if os.path.exists(ENV_PATH):
        for line in open(ENV_PATH):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1); env[k.strip()] = v.strip().strip('"').strip("'")
        if "ZOTERO_API_KEY" not in env:
            s = open(ENV_PATH).read().strip()
            if re.fullmatch(r"[A-Za-z0-9]{20,40}", s): env["ZOTERO_API_KEY"] = s   # 允许只写裸 key
    env.setdefault("ZOTERO_LIBRARY_ID", "14568484")
    env.setdefault("ZOTERO_DATA_DIR", "~/Zotero")
    return env


_env = load_env()
DATA_DIR = os.path.expanduser(_env["ZOTERO_DATA_DIR"])
DB = os.path.join(DATA_DIR, "zotero.sqlite")
STORAGE = os.path.join(DATA_DIR, "storage")
LIBRARY_ID = _env["ZOTERO_LIBRARY_ID"]
