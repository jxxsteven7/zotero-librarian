# Zotero 文献库整理工作区（~/zotero-claude）

用户是机器人/机器人学习方向博士生，用中文交流。这里存放整理 Zotero 库的脚本、提案和日志。
**本文件是唯一规则来源**（原 `zotero-organize.md` 已并入并删除）。

## 1. 库在哪、怎么读写

- 数据目录由 `config.py` 决定：`.env` 的 `ZOTERO_DATA_DIR` > 本机 Zotero `prefs.js` 的 `extensions.zotero.dataDir`（三平台的 profile 位置都会找）> 平台默认
  （`~/Zotero`，Windows `C:\Users\你\Zotero`）；这台 Ubuntu 工作站是 `~/Documents/Zotero`。主库 `zotero.sqlite`，PDF 在 `storage/<附件key>/`。不改 PDF。
- **读**：`python3 dump_zotero.py` → `library_dump.json`（标题/作者/分类/标签/PDF 路径/笔记/批注；不进 git）。
  sqlite 一律用 `config.connect_ro()` 打开：**Zotero 10 起数据库是 WAL 模式**（`zotero.sqlite-wal`），老办法 `?mode=ro&immutable=1` 只读主文件、
  看到的是几小时前的旧数据（2026-09-12 踩过：远端 3287 本地一直读出 3270），普通只读又被 Zotero 的 exclusive 锁挡住；`connect_ro()` 把主文件 + WAL
  拷到临时目录再打开，Zotero 运行中也能拿到最新状态。别再自己写 `sqlite3.connect(...)`。
  凭据在 `.env`（`config.py` 读，每台机器各一份）。
- **三平台通用**（Ubuntu / macOS / Windows，2026-09-12 起）：脚本只用标准库；平台差异全收在 `config.py`——数据目录探测、
  `pdftotext` 查找（PATH → 当前 Python 所在 conda 环境 → Homebrew/winget/scoop/choco 常见位置 → `.env` 的 `PDFTOTEXT`），找不到退到 `pypdf`；
  所有文件读写显式 UTF-8，stdout 强制 UTF-8（否则 Windows 管道下打 ✓⚠− 会崩）。**Windows 上命令是 `python` 不是 `python3`**（Claude Code 的 Bash 是 Git Bash，
  grep/sed 都有）。新机器先 `./setup.sh`（= `python setup.py`）体检，缺什么打印对应平台的安装命令；仓库 `.gitattributes` 钉死 LF。
- **写**：只走 Zotero Web API（库 ID 14568484），**绝不直接改 sqlite**——Zotero 常驻运行且开着同步。
  本地 API（23119）是只读的且没开；`zotero-skills` 插件底层也是同一个 Web API，没装、不需要。
  key 在 `.env`（600 权限，裸 key 一行），个人库已开写权限。**永远不要把 key 打印到对话或日志。** 缺 key 就停下来问。
  批量 POST 是 PATCH 语义，但 `tags` / `collections` 是整体替换：载荷必须以远端当前状态为基础只增不减。
  写前先 `GET` 远端版本，用远端 `version` 做乐观锁；本地 `items.version` 常比远端高 1–4，那是客户端记账差异，
  判断本地有没有未上传改动看 `synced=0`。
- **新条目 + PDF 走桌面端 connector 接口**（`http://127.0.0.1:23119/connector/*`，浏览器插件保存文献用的就是它，Zotero 开着就在）：
  本机附件同步是 **WebDAV（坚果云）**，Web API 上传的文件客户端拿不到，所以 PDF 必须让 Zotero 自己存。
  用法在 `download.py`：`saveItems`（建条目；载荷里的 tags 会被记成自动标签、attachments 被忽略，所以都不放那儿）→
  `updateSession`（`target: "C<本地collectionID>"` + `tags` 数组 → 手动标签、进分类）→ `saveAttachment`（`X-Metadata` 头 + `application/pdf` 原始字节）。
  请求 UA 不能以 `Mozilla/` 开头，Host 必须是 127.0.0.1。saveItems 不返回 key，写完按标题从本地 sqlite 读回核对。
- 客户端自动同步很快（写完几分钟内 `libraries.version` 追平），写完重跑 dump 核对。
- **`DELETE /items` 是永久删除**（不进回收站，本地 PDF 一并清掉）；想留退路用 PATCH `deleted: 1` 扔进回收站。
- `prefs.js` 只能在 Zotero 退出后改，否则退出时被覆写。`extensions.zotero.automaticTags` 应为 false（用户在设置里关）。

## 2. 分类：只有四个，不再新建

| 分类 | 放什么 |
|---|---|
| `Evolution Algorithm` | 进化 / 遗传 / 群体智能优化 |
| `Dex-Manipulation` | 机器人操作：VLA、IL/RL 策略、面向控制的世界模型、灵巧手、双臂、遥操/重定向、抓取合成、手部重建、操作基准 |
| `Humanoid` | **论文的研究对象是人形机器人本身**：全身控制、运动/loco-manipulation、人形遥操与全身重定向、人形行为基础模型（2026-09-12 用户新建，key `9XEMXMX9`） |
| `AI Foundation` | **纯 learning**：通用 ML/AI 经典（PPO/DAgger/GAIL/ResNet/VAE…）、未用于操作的基础模型、生成建模、综述、工具、教材（原名 `Misc`，用户 2026-09-11 改名，key 不变 `DU25RH7B`） |

每篇至少在一个里；综述可同时在 Dex-Manipulation + AI Foundation。**Dex-Manipulation 和 Humanoid 的边界看问题不看硬件**：
在人形上做操作的论文（EgoScale、LaST-0）归 Dex-Manipulation，靠 `embod:humanoid` 检索；一篇既做灵巧手又做人形全身的（SPIDER）可以两个都放。
用户明确要求只保留这四个（旧的 Dex-Hand / VLA / AI Learning / World Model 等已删），**不建新分类、不建子分类**，细分一律靠标签。

## 3. 标签：受控词表，全小写连字符，`family:value`

| 家族 | 值 | 规则 |
|---|---|---|
| `method:` | vla · policy-learning · rl · world-model · foundation-model · teleop · grasp-synthesis | 问题类型/学习范式，每篇 1–2 个。vla = 预训练视觉-语言-动作骨干；policy-learning = 无大 VLA 骨干的示教学习（BC/ACT/扩散/流策略）；rl 含对 VLA 的 RL 后训练（同时贴 vla+rl）；world-model = 用于规划/仿真/训练的学习动力学模型；foundation-model = 本身不是动作模型的 VLM/LLM/骨干；teleop = 遥操系统与人手→机器手重定向；grasp-synthesis = 抓取姿态合成 |
| `embod:` | dex-hand · gripper · single-arm · bimanual · humanoid | 实验中的本体，任意个。末端（dex-hand/gripper）与臂数（single-arm/bimanual）独立，通常各一个；**bimanual = 实验里用了两条臂/两只手**，不再区分双臂协同还是各干各的（原 `dual-arm` 已于 2026-09-12 并入 bimanual）；无臂的双浮动手也贴 bimanual；多平台全贴；纯仿真按仿真本体贴。**humanoid = 策略部署在人形机器人整机上**（TienKung、Galaxea R1Pro、Unitree G1/H1、Fourier 之类，轮式人形也算），只用上肢也贴；两条臂装在固定躯干架上的"semi-humanoid"/ALOHA 不算，仿真里的 Humanoid 跑步环境不算。humanoid 只说硬件，分类看问题：在人形上做操作 → Dex-Manipulation；人形全身控制/运动 → Humanoid |
| `tech:` | action-chunking · flow-matching · diffusion · transformer · hil · latent-cot | 值得跨论文检索的机制，任意个。**只标论文贡献的实质组件，related work 里提到不算**；hil = 训练中的人类纠正/干预；latent-cot = 行动前的隐式或显式推理 |
| `base:` | pi0 · pi0.5 · pi0.6 · gr00t | 真正微调/冻结的预训练骨干；从零训练或"架构类似"不贴 |
| `modality:` | vision · language · tactile · depth · point-cloud · audio | **只标策略/模型真正消费的输入**，不默认贴 vision/language |
| `type:` | survey · benchmark · dataset | 文献类型，与 method 正交 |
| `status:` | 读进度轴（恰好一个）：to-read-first → to-read → skimmed → read；展示轴（可选）：to-present · presented；复现轴（可选）：to-reproduce → reproducing → reproduced | 新条目默认 `to-read`；**不降级**（read→skimmed 之类需用户批准）；展示/复现轴不主动碰 |

- 判定依据：摘要 + 正文实验部分（`pdftotext <pdf> - | grep -n -i …` 定点查；库里 PDF 的路径在 dump 的 `pdfs` 字段），**不能只看标题**。
  embod/modality 判不出就留空并标 Uncertain，不猜；四个分类都不贴切就放 AI Foundation 并标记。
- 标签是**库级**的，Zotero 里不存在"某个分类私有的标签"；词表按机器人学习设计，所以 method/embod/tech/base/modality 实际上
  只出现在 Dex-Manipulation / Humanoid / AI Foundation 的条目上，Evolution Algorithm 的条目只有 `status:`（不需要硬贴）。
  标签选择器默认只显示当前分类里条目带的标签，要看全部得勾 "Display All Tags in This Library"。
- 需要词表外的新标签：写进提案的"Proposed new tags"，用户批准后再用，不私造；不用无前缀的裸标签。
- **arXiv 自动标签一律删除**（用户要求）。不改用户已有标签名。除 `notion` 外不再有裸标签（用户手打的 `Dex-Hand` 已于 2026-09-12 按其要求删除）。
- `notion` 是 **Notero 插件**自动打的裸标签（2026-09-12 起，Dex-Manipulation / Humanoid / AI Foundation 三个分类的条目都有），保留、不算词表外；
  同一批条目下各有一个标题为 `Notion` 的链接附件（linkMode 3，指向该条的 Notion 页面），是 Notero 定位页面的键，**不要删**。Notero 只单向推 Zotero → Notion，
  我经 Web API 改的东西同步下来后也会自动推过去。配置和日常规则在 `notero.md`。

彩色标签（库设置 `tagColors`，选中条目按数字键切换，`to-read` 不着色）：

| 键 | 标签 | 颜色 |
|---|---|---|
| `1` | `status:to-read-first` | 红 `#FF6666` |
| `2` | `status:skimmed` | 浅蓝 `#A6DFF5` |
| `3` | `status:read` | 绿 `#5FB236`（不用浅绿，和浅蓝分不清） |
| `4` | `status:to-present` | 黄 `#FFD400` |
| `5` | `status:presented` | 棕 `#A0522D` |

## 4. 标题格式：`[YYYY-MMDD] [刊/会] 原名`

- 日期精确到天，含义是**这篇最早出现在学术界的日子**（用户 2026-09-12 定）。arXiv 论文用 **v1 提交日**（arXiv API `published`，UTC），
  **之后作者更新版本、用户重下最新版、中稿改了第二个括号，日期都不动**。期刊/会议论文**若有更早的 arXiv 预印本，也用预印本 v1**
  （`recheck --dates --search` 会按标题去 arXiv 搜；RL-100 就是 SR 2026 但 arXiv 2025-10）；机构自己官网先发、后传 arXiv 的（PI 的 RL Token）用官网日。
  没有预印本的期刊用**在线发表日**——PDF 首页印的 "Available online / Published online / Date of publication"，其次 Crossref `published-online`；
  Crossref `created` 只在与出版年相差 ≤1 时可用（老论文的 created 是 DOI 登记日，不可信）；
  PDF 正文里抓到的日期要和出版年对得上，否则是引用噪音。拿不到精确日期就能到哪写哪（`[1999-07]`、`[1987]`），**不编造日子**。
- 刊/会用缩写：CoRL RSS ICRA IROS ICLR ICML NeurIPS CVPR AISTATS · ESWA EAAI KBS ASOC SWEVO INS AES CAIE NCA JOGO
  CMAME ATE SOCO TEVC AMM CACM Access SR IJRR CEC · Book · TechReport；纯 arXiv 预印本写 `[arXiv]`，中稿后改。
  来源优先级：用户已写 > Zotero 字段 > 笔记/arXiv comment 里的 "Accepted to …" > PDF 首页出版声明 > Semantic Scholar（只认
  type=conference 或非 arXiv DOI）> Crossref 标题搜索（RSS/IEEE 有 DOI）> 项目页/README（arXiv comment、摘要、PDF 首页里的链接，
  找 "Accepted to …" 或页头徽章 "CoRL 2025"；写 under review/anonymous 的记下）> WebSearch > 常识（标 ⚠ 请用户过目）。
  **用户习惯下 arXiv 最新版，但已中稿的要写会议不写 `[arXiv]`**；`download.py fetch` 收新论文时自动跑这条链，
  `download.py recheck [--dates]` 给存量 `[arXiv]` 补查（`--dates` 同时核对日期是不是 v1）。DBLP 和 OpenReview 都有人机验证，脚本用不了。
  查不到就保留 `[arXiv]`，不凭印象填会议。
- 用户自己写的部分（短名 `GWO 2014`、昵称 `[VAE]` `[ALOHA/ACT]`、标记 ✅❗、`[ICRA-Best]`）**原样保留在两个括号之后，绝不改**。
- **Short Title 字段 = 论文短名**（2026-09-12 起，Notero 拿它当 Notion 页面标题）：用户昵称 `[ALOHA/ACT]` → `ALOHA/ACT` > 冒号前的名字（`RL-100`）>
  去掉前缀的原名。`download.short_title()` 算，`/download` 入库自动填（`--short` 覆盖）；改标题时 Short Title 不用跟着动（它本来就不含前缀）。
- **URL 字段 = 项目页**（github.io / 机构博客 / sites.google.com/view），没有项目页才放 arXiv abs 或 DOI 链接（Notion 的 `URL` 列显示的就是它）。
  `fetch` 从 arXiv comment、摘要、PDF 首页正文和 PDF 超链接注释（`/URI`）里找，卡片打印"项目页"，`save` 默认用它（`--url` 覆盖）。
  arXiv 号不靠 URL：查重和 `recheck` 认 DOI 字段 `10.48550/arXiv.…` 和 PDF 水印。存量 74 篇（三个分类）已于 2026-09-12 改完，Evolution Algorithm 的没动。
- **标题前缀只是显示用，PDF 文件名不要带**。Zotero 7+ 默认 `autoRenameFiles.onMetadataChange=true`：父条目标题一改，
  凡是文件名还是模板生成的附件就会跟着改名（2026-09-12 发现约 50 个 PDF 已经被改成 `作者 - 年 - [日期] [刊] 原名.pdf`）。
  解决：文件名模板（设置 → 通用 → 文件重命名 → 自定义）改成去掉前两个方括号：
  `{{ firstCreator suffix=" - " }}{{ year suffix=" - " }}{{ title replaceFrom="^\[[^\]]*\] *(\[[^\]]*\] *)?" replaceTo="" truncate="120" }}`
  这是库的**同步设置**（`attachmentRenameTemplate`），用户 2026-09-12 已设好，其他设备的 Zotero 会自动跟上，不用每台再设。
  之后改标题文件名不再变；已经带前缀的用 Run JavaScript 跑仓库里的 `fix_pdf_names.js` 一次性改回（只动文件名里有 ` - [` 的，不碰用户手工命名的 `NOA 2023.pdf` 之类）。
- 缩写表在 `venues.py`，新缩写只加那里。存量 110 条已于 2026-09-11 批量改完（老→新对照在日志里），当时的 retitle 脚本和中间数据已删。

## 5. 工作流（approval mode）

1. `dump_zotero.py` 刷新 → 新条目在 `proposal.py` 的 `P` 里加行（`type:` 放 `EXTRA_TAGS`），`python3 proposal.py` 生成提案表。
2. `apply.py --dry-run`（离线构造载荷）→ `--plan`（联网只读核对远端版本）→ 把提案表给用户。
   提案表格式：`| # | Title | Collection(s) | method: | embod: | tech: | base: | modality: | status: | Note |`，另附 Uncertain 与 Proposed new tags。
3. **用户批准后**才 `--apply`，只写批准的行；用户可以逐行改。用户没说 "autonomous mode" 前一直是 approval mode；
   说了以后新条目可端到端处理，但仍要逐笔记日志并标出拿不准的。
4. 写完回读远端逐条比对，再重跑 dump 确认客户端同步。
5. 每批写入都追加 `zotero-organize.log.md`：
   ```
   ## <日期> — batch <n>
   ### Applied      - <key> | <title> | +collection: … | +tags: … | −tags: …
   ### Uncertain    - <key> | <title> | 哪里拿不准
   ### Proposed new tags   - <tag> | 理由 | 需要它的条目
   ```
6. 不删条目、不删笔记、不删分类；删东西只在用户明说时做，做前把成员快照写进日志，并优先扔回收站而非永久删。
7. 词表改名/合并标签：在 `proposal.py` 写 `RETAG = {"旧标签": "新标签"}`，`apply.py` 会对库里**所有**带旧标签的条目摘旧补新
   （含 P 之外、`/download` 收的条目），日志记 `−tags:`。这是唯一会从条目上摘标签的路径。回收站里的条目自动跳过。

**新论文入库走 `/download`**（项目级 skill `.claude/skills/download/SKILL.md`，会话要开在仓库目录；脚本 `download.py`）——这条是用户授权的端到端自动流程，
不逐篇征求批准：`fetch <链接>`（arXiv / DOI / OpenReview / PDF 直链 / 本地 PDF / 项目页 → 元数据 + PDF + 全文 txt + 查重 + 建议标题）
→ 读摘要和实验部分定分类与标签 → `save <slug> --collection … --tags …`（status 默认 `to-read`）→ 汇总表。
重复条目默认跳过；词表外标签不私造；付费期刊抓不到 PDF 时条目照建，让用户把 PDF 拖进去或给本地路径重跑。日志自动追加。

## 6. 现状与遗留（2026-09-12）

- 仓库在 GitHub 私有库 `jxxsteven7/zotero-claude`，Ubuntu / macOS / Windows 三台共用；新机器按 README 走一遍 `setup.sh`。
  `.env`、`library_dump*.json`、`inbox/` 不进 git。Zotero 端每台机器要各做一次的只有关 `automaticTags`（客户端偏好，不同步）；
  标签颜色和 PDF 文件名模板都是库的同步设置，已经设好。

- 2026-09-12 `embod:dual-arm` 并入 `embod:bimanual`（23 条摘旧标签，其中 4 条补 bimanual）；同日新建 `Humanoid` 分类，BFM-Zero 从 AI Foundation 移入，
  SPIDER 两个分类共享。`recheck` 查出 6 篇已中稿的 `[arXiv]` 改成 RSS/IROS/ICRA（证据是 DOI）；其余 29 篇 API 和项目页都查不到录用信息，保留。
  同日 `/goal` 全库复核完成：21 条日期改成 v1；5 条期刊/会议条目改成更早的预印本 v1（FR9BMARE、π0.6、π0.7、RL-100、Prismatic）；
  32 条非 arXiv 刊/会标签经 S2/Crossref/PDF 首页核实一致，0 条矛盾；标签补 4 摘 2（RDP、ALOHA +teleop；T-Rex +diffusion；Show-Harness +action-chunking；
  π0.6 −base:pi0.5；UniTacHand 去掉多余的 status:to-read）。PDF 文件名用户已按 §4 改好模板并跑过改回脚本，全库只剩三个昵称括号在文件名里（按设计）。
- **留给用户的**：`NWMWYY4Z` EEFO 下面挂着一个 `ABC_2007.pdf`（内容是 Karaboga 2007 ABC，`JM8BGX33` 已有），疑似误挂；
  `DS2CBILL` AlexNet 收的是 CACM 2017 重印版，原文是 NeurIPS 2012；`ESK4SDNZ` 的 `[IJRR]` 是用户自己写的，API/PDF 里查不到；
  `AP8LAAEQ` MoDE-VLA 有 3 个 method（rl/vla/teleop，teleop 是用户 09-11 批的）；`UHXQKX93` MINT 无机器人本体，embod 留空。
- 121 篇（用户自己把 `Z6QB6YQG` NSM-SFS 2023 扔进了回收站）全部贴齐标签、归入分类、标题统一格式；arXiv 自动标签已清空；
  4 个无父条目的孤立 PDF 已按用户要求永久删除。之后用户自己加了 VLA-Precision（`G4N8QAK5`），`/download` 测试时收了 π0（`HKWZ6MV2`）。
- `KNFD9629`（HS2001）与 `GUHVP29Z` 是同一篇 Harmony Search 的重复条目，留给用户处理。
- 2026-09-12 本机 Zotero 升到 10.0.2（数据库 userdata 125→129，旧程序和备份已按用户要求删除）；Notion 侧改用 Notero 2.1.0 单向镜像三个分类，
  现行配置见 `notero.md`（74 篇已推到 Notion `All Papers`，URL 改项目页 63 条、Short Title 补 33 条，日志有）。
- `extensions.zotero.automaticTags` 还没关（需用户在 Zotero 设置里操作，或退出 Zotero 后由我改 prefs.js）。
