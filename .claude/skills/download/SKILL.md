# /download — 论文入库

项目级 skill（会话在仓库目录里才有）。判定规则在仓库 `CLAUDE.md`（§2 分类、§3 词表、§4 标题），**判定本身已写进脚本**
（`zotero_claude/classify.py`）：你不用读全文、不用 grep，只跑一条命令、转述结果、处理它标出的 ⏸ / ⚠ / 候选。

参数 `$ARGUMENTS` 是一个或多个链接 / 本地 PDF 路径，空格分隔（arXiv / DOI / OpenReview / PDF 直链 / 项目页 / JMLR 之类的论文页）。
没给参数就问要哪几篇。Windows 上 `python3` 写 `python`。

## 流程

1. 在仓库目录跑（等远端同步最多 150 秒/篇，Bash 超时给 600000）：

   ```
   python3 zc.py add <链接…>
   ```

   脚本对每篇：抓元数据 + PDF + 全文 → 查重 → 自动定分类和标签（附证据）→ 经 Zotero 桌面端入库 → 等云端同步并核对 →
   把日志 commit + push → 最后打印一张 `| key | 标题 | 分类 | 标签 | PDF | 备注 |` 的表。

2. 看输出，按情况处理（多数情况什么都不用做）：
   - **正常入库**：扫一眼"贴"下面的证据行，明显贴错的（证据是相关工作/基线）`python3 zc.py untag <key> 标签 --why 原因`；其余不动。
   - **候选**（脚本不贴、只列出的边缘标签）：写进汇报让用户定；证据明确够 CLAUDE.md 规则的可以直接 `python3 zc.py tag <key> a,b` 补上并在汇报里说明。
   - **⏸ 分类拿不准**（Humanoid / Dex-Manipulation 边界，或 AI Foundation 但有机器人词）：读脚本打印的摘要定分类，
     跑它给出的 `python3 zc.py save <slug> --collection "…" [--also "…"] [--tags …]`（可加 `--drop a,b` 去掉建议里的标签）。
   - **⚠ 重复**：默认跳过，汇报里写库里已有哪条；用户明说要再加才 `--force`。
   - **✗**：链接认不出或元数据取不到，把原因告诉用户，让他换 arXiv/DOI 链接、论文页或直接给 PDF。
   - **刊/会仍是 `[arXiv] ← default`**：脚本已查过 arXiv comment / PDF 首页 / Semantic Scholar / Crossref / 项目页，不用再搜；备注写"未查到录用信息"。
     用户点名要查时再 WebSearch，查到用 `python3 zc.py set <key> title="[日期] [会议] 原名"`。
   - **同步 ⏳ 未确认**：Zotero 客户端还没把条目传上去，稍后 `python3 zc.py verify <key>`；不用轮询。
   - 用户说"先看"：加 `--first`（status:to-read-first）。

3. **汇报**：直接转述脚本打印的表（不要重新组织），表下面最多两三句：候选标签要不要补、⚠ 里需要用户定的事。
   日志和 git 已由脚本处理，不用再写日志、不用再 commit。

## 其他命令

- 只想看不入库：`python3 zc.py fetch <链接>`（完整卡片）→ `python3 zc.py suggest <slug>`（分类/标签建议）→ `python3 zc.py save <slug> …`。
- 存量复核：`python3 zc.py dump && python3 zc.py recheck [--dates] [--search]`，只列表；批准后加 `--write`。

## 不要做的事

- 不改 sqlite，不走 Web API 传 PDF（本机附件同步是 WebDAV，传了客户端也看不到）。
- 不改用户已有条目的标题/标签，不新建分类，不私造词表外的标签。
- 不把 `.env` 里的 API key 打印出来。
