# Zotero 文献库整理工作区（~/zotero-claude）

用户是机器人/机器人学习方向博士生，用中文交流。这里存放整理 Zotero 库的脚本、提案和日志。
**本文件是唯一规则来源**（原 `zotero-organize.md` 已并入并删除）。

## 1. 库在哪、怎么读写

- 数据目录 `~/Documents/Zotero/`，主库 `zotero.sqlite`，PDF 在 `storage/<附件key>/`。不改 PDF。
- **读**：`python3 dump_zotero.py` → `library_dump.json`（标题/作者/分类/标签/PDF 路径/笔记/批注；不进 git）。
  sqlite 用 `file:...?mode=ro&immutable=1` 打开，Zotero 运行中也能读，不用拷贝。
  本机路径和凭据都在 `.env`（`config.py` 读；`ZOTERO_DATA_DIR` 本机是 `~/Documents/Zotero`，别的机器看 prefs.js）。
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

## 2. 分类：只有三个，不再新建

| 分类 | 放什么 |
|---|---|
| `Evolution Algorithm` | 进化 / 遗传 / 群体智能优化 |
| `Dex-Manipulation` | 机器人操作：VLA、IL/RL 策略、面向控制的世界模型、灵巧手、双臂、遥操/重定向、抓取合成、手部重建、操作基准 |
| `AI Foundation` | 其他：通用 ML/AI、未用于操作的基础模型、人形全身控制、综述、工具（原名 `Misc`，用户 2026-09-11 改名，key 不变 `DU25RH7B`） |

每篇至少在一个里；综述可同时在 Dex-Manipulation + AI Foundation。用户明确要求只保留这三个（旧的 Dex-Hand / VLA /
AI Learning / World Model / Humanoid 等已删），**不建新分类、不建子分类**，细分一律靠标签。

## 3. 标签：受控词表，全小写连字符，`family:value`

| 家族 | 值 | 规则 |
|---|---|---|
| `method:` | vla · policy-learning · rl · world-model · foundation-model · teleop · grasp-synthesis | 问题类型/学习范式，每篇 1–2 个。vla = 预训练视觉-语言-动作骨干；policy-learning = 无大 VLA 骨干的示教学习（BC/ACT/扩散/流策略）；rl 含对 VLA 的 RL 后训练（同时贴 vla+rl）；world-model = 用于规划/仿真/训练的学习动力学模型；foundation-model = 本身不是动作模型的 VLM/LLM/骨干；teleop = 遥操系统与人手→机器手重定向；grasp-synthesis = 抓取姿态合成 |
| `embod:` | dex-hand · gripper · single-arm · bimanual · humanoid | 实验中的本体，任意个。末端（dex-hand/gripper）与臂数（single-arm/bimanual）独立，通常各一个；**bimanual = 实验里用了两条臂/两只手**，不再区分双臂协同还是各干各的（原 `dual-arm` 已于 2026-09-12 并入 bimanual）；无臂的双浮动手也贴 bimanual；多平台全贴；纯仿真按仿真本体贴。**humanoid = 策略部署在人形机器人整机上**（TienKung、Galaxea R1Pro、Unitree G1/H1、Fourier 之类，轮式人形也算），只用上肢也贴；两条臂装在固定躯干架上的"semi-humanoid"/ALOHA 不算，仿真里的 Humanoid 跑步环境不算。humanoid 只说硬件，分类看问题：在人形上做操作 → Dex-Manipulation；人形全身控制/运动 → AI Foundation |
| `tech:` | action-chunking · flow-matching · diffusion · transformer · hil · latent-cot | 值得跨论文检索的机制，任意个。**只标论文贡献的实质组件，related work 里提到不算**；hil = 训练中的人类纠正/干预；latent-cot = 行动前的隐式或显式推理 |
| `base:` | pi0 · pi0.5 · pi0.6 · gr00t | 真正微调/冻结的预训练骨干；从零训练或"架构类似"不贴 |
| `modality:` | vision · language · tactile · depth · point-cloud · audio | **只标策略/模型真正消费的输入**，不默认贴 vision/language |
| `type:` | survey · benchmark · dataset | 文献类型，与 method 正交 |
| `status:` | 读进度轴（恰好一个）：to-read-first → to-read → skimmed → read；展示轴（可选）：to-present · presented；复现轴（可选）：to-reproduce → reproducing → reproduced | 新条目默认 `to-read`；**不降级**（read→skimmed 之类需用户批准）；展示/复现轴不主动碰 |

- 判定依据：摘要 + 正文实验部分（`pdftotext <pdf> - | grep -n -i …` 定点查；库里 PDF 的路径在 dump 的 `pdfs` 字段），**不能只看标题**。
  embod/modality 判不出就留空并标 Uncertain，不猜；三个分类都不贴切就放 AI Foundation 并标记。
- 需要词表外的新标签：写进提案的"Proposed new tags"，用户批准后再用，不私造；不用无前缀的裸标签。
- **arXiv 自动标签一律删除**（用户要求），手动打的无前缀标签（如 `Dex-Hand`）保留。不改用户已有标签名。

彩色标签（库设置 `tagColors`，选中条目按数字键切换，`to-read` 不着色）：

| 键 | 标签 | 颜色 |
|---|---|---|
| `1` | `status:to-read-first` | 红 `#FF6666` |
| `2` | `status:skimmed` | 浅蓝 `#A6DFF5` |
| `3` | `status:read` | 绿 `#5FB236`（不用浅绿，和浅蓝分不清） |
| `4` | `status:to-present` | 黄 `#FFD400` |
| `5` | `status:presented` | 棕 `#A0522D` |

## 4. 标题格式：`[YYYY-MMDD] [刊/会] 原名`

- 日期精确到天。arXiv 论文用 **v1 提交日**（arXiv API `published`）；期刊用**在线发表日**——PDF 首页印的
  "Available online / Published online / Date of publication"，其次 Crossref `published-online`；
  Crossref `created` 只在与出版年相差 ≤1 时可用（老论文的 created 是 DOI 登记日，不可信）；
  PDF 正文里抓到的日期要和出版年对得上，否则是引用噪音。拿不到精确日期就能到哪写哪（`[1999-07]`、`[1987]`），**不编造日子**。
- 刊/会用缩写：CoRL RSS ICRA IROS ICLR ICML NeurIPS CVPR AISTATS · ESWA EAAI KBS ASOC SWEVO INS AES CAIE NCA JOGO
  CMAME ATE SOCO TEVC AMM CACM Access SR IJRR CEC · Book · TechReport；纯 arXiv 预印本写 `[arXiv]`，中稿后改。
  来源优先级：用户已写 > Zotero 字段 > 笔记/arXiv comment 里的 "Accepted to …" > PDF 页眉出版声明 > 常识（标 ⚠ 请用户过目）。
- 用户自己写的部分（短名 `GWO 2014`、昵称 `[VAE]` `[ALOHA/ACT]`、标记 ✅❗、`[ICRA-Best]`）**原样保留在两个括号之后，绝不改**。
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

- 仓库在 GitHub 私有库 `jxxsteven7/zotero-claude`，多台设备共用；新机器按 README 走一遍 `setup.sh`。
  `.env`、`library_dump*.json`、`inbox/` 不进 git。

- 2026-09-12 `embod:dual-arm` 并入 `embod:bimanual`（23 条摘旧标签，其中 4 条补 bimanual），远端 lib-version 3118。
- 121 篇（用户自己把 `Z6QB6YQG` NSM-SFS 2023 扔进了回收站）全部贴齐标签、归入三分类、标题统一格式；arXiv 自动标签已清空；
  4 个无父条目的孤立 PDF 已按用户要求永久删除。之后用户自己加了 VLA-Precision（`G4N8QAK5`），`/download` 测试时收了 π0（`HKWZ6MV2`）。
- `KNFD9629`（HS2001）与 `GUHVP29Z` 是同一篇 Harmony Search 的重复条目，留给用户处理。
- `extensions.zotero.automaticTags` 还没关（需用户在 Zotero 设置里操作，或退出 Zotero 后由我改 prefs.js）。
