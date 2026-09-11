---
name: download
description: |
  把论文链接收进 Zotero：下载 PDF、建条目、按规则命名（[YYYY-MMDD] [刊/会] 原名）、归入三分类之一、
  按受控词表打标签，status 默认 to-read。用法 /download <链接或本地 PDF 路径>...（arXiv / DOI / OpenReview /
  PDF 直链 / 项目页）。端到端自动完成，不逐篇征求批准，做完给汇总表。
---

# /download — 论文入库

这是本仓库的项目级 skill（会话在仓库目录里才有）。脚本 `download.py`，规则全在仓库 `CLAUDE.md`（分类 §2、标签词表 §3、
标题格式 §4），词表和判定规则以它为准。

参数 `$ARGUMENTS` 是一个或多个链接 / 本地 PDF 路径，空格分隔。没给参数就问要哪几篇。

## 流程（每篇都走完，不要只做一半）

1. **抓取**：`python3 download.py fetch <链接>...`（在仓库目录下）
   每篇打印一张卡片：来源、标题、作者、日期(来源)、刊/会(来源)、建议标题、PDF 是否拿到、全文 txt 路径、摘要，
   以及是否与库里已有条目重复。inbox 文件在 `inbox/<slug>.{json,pdf,txt}`。
   - 卡片报 `✗`：链接认不出或元数据取不到，告诉用户原因，让他换 arXiv/DOI 链接或直接给 PDF。
     （OpenReview 的 API 常被人机验证挡住，脚本会退到 PDF 路线；项目页靠页面上的 PDF 链接 + arXiv 标题搜索认出来。）
   - 报 `⚠ 重复`：**默认跳过**，汇报里说明库里已有哪条；用户明确说要再加才 `--force`。

2. **读论文定标签**：不能只看标题。读摘要 + `grep -n -i "<关键词>" inbox/<slug>.txt` 查实验部分
   （本体：UR5/Franka/ALOHA/dex hand/humanoid/gripper；输入：tactile/depth/point cloud/language；骨干：π0/GR00T；
   机制：flow matching/diffusion/chunk/intervention/reasoning）。按 CLAUDE.md §3 的判定规则决定：
   - 分类：`Evolution Algorithm` / `Dex-Manipulation` / `AI Foundation`，一篇一个；综述才 `--also` 加第二个。
   - `method:` 1–2 个；`embod:` `tech:` `base:` `modality:` 只标真正用到的，判不出留空；`type:` 综述/基准/数据集才贴。
   - `status:` 不用写，脚本默认补 `status:to-read`（用户说"先看"就 `status:to-read-first`）。
   - 词表外的新值不要私造：留空，汇报里写"建议新标签 xxx，理由"。

3. **核对标题前缀**：日期取 arXiv v1 提交日或期刊在线发表日，`YYYY-MMDD`；刊/会用缩写，纯预印本 `[arXiv]`。
   卡片里带 `⚠` 的来源（Crossref 不完整、OpenReview 日期、全名刊物）要自己判断：
   arXiv comment 写了 "Accepted to CoRL 2025" 之类就 `--venue CoRL`；全名刊物查 `venues.py` 没有缩写的，
   按用户习惯造一个缩写（首字母大写）并在汇报里标出来。日期拿不到精确的能到哪写哪，不编造。

4. **入库**：`python3 download.py save <slug> --collection "<分类>" --tags a,b,c [--also "<分类>"] [--venue X] [--date YYYY-MMDD]`
   脚本经 Zotero 桌面端 connector 接口建条目、贴标签、送 PDF，然后从本地库读回 key/分类/标签/PDF 路径打印出来。
   报 "connector 23119 不通" 就是 Zotero 没开，让用户开了再说。`--also` 走 Web API，要等条目同步上去（最多 3 分钟）；
   没等到会打印一条 `download.py collect <key> <分类>` 让稍后补。

5. **汇报**：一张表 `| key | 标题 | 分类 | 标签 | PDF | 备注 |`，备注写拿不准的判断（embod 留空的原因、⚠ 的日期/刊名、
   建议新标签、重复跳过）。日志脚本已自动追加到 `zotero-organize.log.md`，不用再写。

## 不要做的事

- 不改 sqlite，不走 Web API 传 PDF（本机附件同步是 WebDAV，传了客户端也看不到）。
- 不改用户已有条目的标题/标签，不新建分类。
- 不把 `.env` 里的 API key 打印出来。
