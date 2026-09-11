# zotero-claude

用 Claude Code 维护我的 Zotero 文献库：四个分类、`family:value` 受控标签、`[YYYY-MMDD] [刊/会] 原名` 标题。
规则全在 [`CLAUDE.md`](CLAUDE.md)，Claude 在这个目录开会话时自动加载。

## 新机器

```bash
git clone git@github.com:jxxsteven7/zotero-claude.git ~/zotero-claude
cd ~/zotero-claude
cp .env.example .env && chmod 600 .env     # 填 API key 和 Zotero 数据目录
./setup.sh                                 # 检查 pdftotext / 数据目录 / Zotero 桌面端
claude                                     # 在这个目录里开会话
```

`.env`、`library_dump*.json`、`inbox/` 不进 git（凭据、库内容、论文全文）。

## 日常

- `/download <arXiv/DOI/PDF 链接或本地 PDF 路径>...` —— 收论文：下载、建条目、按规则命名、归类、贴标签，status 默认 `to-read`。
  需要 Zotero 桌面端开着（PDF 走它的本地 connector 接口，因为附件同步是 WebDAV）。
- 存量批量整理（approval mode）：`dump_zotero.py` → 在 `proposal.py` 加行 → `apply.py --dry-run` / `--plan` → 批准后 `--apply`。

## 文件

| 文件 | 作用 |
|---|---|
| `CLAUDE.md` | 唯一规则来源 |
| `.claude/skills/download/` | `/download` skill（项目级） |
| `download.py` | 收论文脚本：fetch / save / collect |
| `venues.py` | 刊/会名 → 缩写表 |
| `dump_zotero.py` | 只读导出全库 → `library_dump.json` |
| `apply.py` + `proposal.py` | 批量整理：提案表 → Web API 写入 |
| `config.py` | 读 `.env`（key、库 ID、数据目录） |
| `zotero-organize.log.md` | 所有写入的审计日志 |
