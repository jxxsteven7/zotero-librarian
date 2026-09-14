# zotero-claude

用 Claude Code 维护我的 Zotero 文献库：四个分类、`family:value` 受控标签、`[YYYY-MMDD] [刊/会] 原名` 标题。
规则全在 [`CLAUDE.md`](CLAUDE.md)，Claude 在这个目录开会话时自动加载。

脚本只用 Python 标准库，Ubuntu / macOS / Windows 通用；外部程序只有 `pdftotext`（没有就退到 `pip install pypdf`）。
库内容和 PDF 通过 Zotero 自己的同步（数据走 zotero.org，附件走 WebDAV）在设备间共享，这个仓库只放规则和脚本。

## 新机器

```bash
git clone git@github.com:jxxsteven7/zotero-claude.git ~/zotero-claude
cd ~/zotero-claude
cp .env.example .env            # 填 ZOTERO_API_KEY；数据目录不填会自动探测（Linux/macOS 再 chmod 600 .env）
./setup.sh                      # 体检：Python / .env / 数据目录 / pdftotext / HTTPS / Zotero 桌面端 / API key，缺什么给对应平台的命令
claude                          # 在这个目录里开会话
```

`./setup.sh` 只是挑一个 Python 去跑 `zc.py setup`；Windows 上（Claude Code 的 Bash 是 Git Bash）直接 `python zc.py setup` 也行。

| 平台 | 装 pdftotext | 备注 |
|---|---|---|
| Ubuntu | `sudo apt install poppler-utils` | 系统 `python3` 3.12 即可 |
| macOS | `brew install poppler` | python.org 安装包的 Python 第一次跑要执行 `Install Certificates.command`，否则 HTTPS 全挂；Homebrew / conda 的 Python 没这问题 |
| Windows | `winget install --id oschwartz10612.Poppler -e`（或 `scoop`/`choco install poppler`），装完重开终端 | 命令是 `python` 不是 `python3`；Zotero 数据目录默认 `C:\Users\你\Zotero`，`.env` 里直接写反斜杠路径 |
| 任一平台 conda | `conda install -c conda-forge poppler` | 用哪个环境的 python 跑脚本，就会在那个环境里找 pdftotext |

`.env`、`cache/`、`inbox/` 不进 git（凭据、库内容、论文全文），每台机器各有一份 `.env`。
Zotero 端要在**每台机器**各做一次的只有一件事：设置里关 `automaticTags`（自动标签）。PDF 文件名模板是库的同步设置，一台设好全部生效。

## 日常

所有命令一个入口：`python3 zc.py <命令>`（`--help` 列全部）。

- `/download <链接…>` —— 在 Claude 里收论文，底下就是 `zc.py add <链接…>`：下载、查重、**自动**定分类贴标签（规则在 `zotero_claude/classify.py`，
  附证据）、按规则命名、经 Zotero 桌面端入库、等云端同步核对、日志 commit+push、打印汇报表。分类拿不准会 ⏸ 停下让人定。
  需要 Zotero 桌面端开着（PDF 走它的本地 connector 接口，因为附件同步是 WebDAV）。
- 改一条：`zc.py verify <key>` / `tag <key> a,b` / `untag <key> a,b --why …` / `collect <key> <分类>` / `set <key> url=… shortTitle=…`（都记日志）。
- `zc.py dump && zc.py recheck [--dates] [--search]` —— 复核库里 arXiv 条目：查中稿改 `[arXiv]` 为会议、核对日期是否 v1；看表批准后加 `--write`。
- 存量批量整理（approval mode）：`zc.py dump` → 在 `proposals/proposal.py` 加行 → `zc.py proposal` → `zc.py apply --dry-run` / `--plan` → 批准后 `--apply`。
- PDF 文件名被标题前缀污染了：Zotero → 工具 → 开发者 → Run JavaScript 跑 `tools/fix_pdf_names.js`（先 DRY 看清单）。
- 调了 `classify.py` 的规则：`python3 tools/eval_classify.py` 用库里已核过标签的条目看精确率/召回率（`--errors` 逐条看）。

## 布局

```
zc.py                       命令行入口
zotero_claude/              代码包：config vocab venues classify pipeline fetch sources pdf published titles connector zapi localdb batch recheck setup_check cli
proposals/proposal.py       批量整理的提案数据
docs/notero.md              Zotero → Notion 镜像（Notero 插件）的现行配置和日常规则
logs/zotero-organize.log.md 所有写入的审计日志
tools/                      fix_pdf_names.js（Zotero 内跑）、eval_classify.py（评估分类规则）
.claude/skills/download/    /download skill
inbox/ cache/               抓取暂存、dump 与全文缓存（不进 git）
```
