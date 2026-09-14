# Notero：Zotero → Notion 单向镜像（现行配置，2026-09-12）

**分工**：Zotero 管元数据 / PDF / 标签 / 阅读进度；Notero 插件把三个分类的条目单向推到 Notion；Notion 只在页面正文里写笔记。
Notion 里凡是 Notero 管的字段（标题、Tags、URL、Collections）改了也会被下次同步覆盖，**要改就改 Zotero**。

## Zotero 侧

- 客户端 Zotero 10.0.2（Ubuntu 工作站）+ Notero 2.1.0（要求 Zotero 10.0.*；Mac/Win 升到 10 后装同一个 xpi、Connect 到同一个库即可，偏好每台各存）。
- Notero 偏好：监视分类 `Dex-Manipulation` `Humanoid` `AI Foundation`（**不含** `Evolution Algorithm`）；Sync when items are modified 开；Sync notes **关**；
  Notion Page Title = **Item Short Title**。
- 同步过的条目会多一个 `notion` 裸标签和一个标题为 `Notion` 的链接附件（linkMode 3，指向 Notion 页面，附件的笔记里存着同步状态）。
  两者都是 Notero 的定位键，**不要删**；脚本里 `notion` 已列为保留裸标签，`Notion` 附件不会混进 dump 的 `pdfs`。
- 触发：条目进分类、条目任何改动（含经 Web API 改、再由客户端同步下来的）→ 2 秒后推一次。实测经 API 改 URL 到 Notion 页面出现约 1 分钟。
  所以我用脚本改标签/分类/标题，Notion 自动跟。**装插件前就在分类里、之后又没改过的条目不会自己同步**（MINT 就是这样），要右键 Sync to Notion 或对分类右键 Sync Items to Notion 一次。删条目 / 移出分类 Notion 页面**不自动删**。
- 页面标题来自 Zotero 的 **Short Title** 字段 = 论文短名：用户昵称（`[ALOHA/ACT]` → `ALOHA/ACT`）> 冒号前的名字（`RL-100`）> 去掉前缀的原名。
  想改 Notion 里的显示名 → 改 Zotero 的 Short Title。`/download` 入库时自动填（`--short` 可覆盖）。
- Zotero 的 **URL 字段 = 项目页**（github.io / 机构博客 / sites.google），没有项目页才放 arXiv 或 DOI 链接。Notion 的 `URL` 列显示的就是它。
  arXiv 号不靠 URL：在 DOI 字段（`10.48550/arXiv.…`）和 PDF 水印里，查重和 `recheck` 都认。`/download` 入库时自动找（`--url` 可覆盖）。
  2026-09-12 已给 74 篇里 63 篇填了项目页（见日志）；PPO、DAgger、ResNet、GAIL、AlexNet、VAE、CVAE、Autoencoders、Flow Matching、MINT、
  Visual-tactile pretraining (SR) 没有项目页，保留原链接。

## Notion 侧

```
Paper Reading                      (页面)
└── Zotero Papers                  (内嵌数据库，原名 All Papers，用户已改名；Notero 唯一写入目标；三个视图 tab：Dex-Manipulation | Humanoid | AI Foundation，
                                    各按 Collections contains <分类名> 过滤，Collections 列在视图里隐藏)
```

`Zotero Papers` 属性（**名字类型一字不差，大小写敏感，不能改名**——Notero 只按固定名字写，改名了它就当这列不存在、静默不填；
自定义属性名是 Notero 未实现的功能 #355。自己想加的属性随便加，Notero 不碰）：

| 属性 | 类型 | 内容 |
|---|---|---|
| `Name` | Title | Zotero Short Title（论文短名） |
| `Collections` | Multi-select | Zotero 分类名；只用于视图过滤，各视图里隐藏 |
| `Tags` | Multi-select | Zotero 全部标签；颜色按家族配好（`method:` `embod:` `tech:` `base:` `modality:` `type:` `status:` 各一色），Notero 不改颜色，新标签出现是随机色要手配。库里还没人贴的值（如 `status:read`）可以先在 Notion 手建选项配好色，之后 Notero 按名字匹配、颜色保留 |
| `URL` | URL | Zotero URL 字段 = 项目页。**列名必须就叫 `URL`**：2026-09-14 发现用户把它改成了 `Project URL`，Notero 从此不再填，81 篇里 78 篇空着；已改回，需对三个分类各右键一次 Sync Items to Notion 回填 |
| `Zotero URI` | URL | 点开 zotero.org 网页库里的这条（回 Zotero 的入口） |

没有 `Date Added`（删了）。**Sync notes 关**（2026-09-12 用户定）：Notion 页面正文完全归用户，Notero 不写正文。开着时它只维护页面里一个 "Zotero Notes" 折叠块（Zotero 笔记的只读镜像，折叠块以外从不碰）；关掉后已有的折叠块留在页面上不再更新，可手动删。
Notero 认识的其他属性（`DOI` `Year` `Authors` `Abstract` `Publication` …共 25 个）以后要就按准确名字加，加完对分类右键 Sync Items to Notion 回填。

## 日常

1. 新论文 `/download` → 进 Zotero 分类 → 几秒后 Notion 出现一行（标题短名、URL 项目页、Tags 全套）。
2. 笔记写 Notion 页面正文。
3. 改显示名 → Zotero Short Title；改链接 → Zotero URL；改标签/分类/进度 → Zotero。Notion 里别动这四列。
4. 跳转：Zotero 条目下双击 `Notion` 附件 → 浏览器打开页面（可"在应用中打开"）；Notion 里点 `Zotero URI` → 网页库。
   项目页：Zotero 条目面板的 URL 字段右侧有 ↗ 按钮直接打开（阅读 PDF 时右侧栏"信息"里也有）；Notion 的 `URL` 列就是它。
5. **Notion 里某列一直空着 → 先看列名是不是被改过**（Notero 认死名字）。改回来后要对分类右键 Sync Items to Notion 才回填（Notero 只在条目改动时推）。
6. 删了 Notion 页面又想重推：先删条目上的 `Notion` 附件再对条目右键 Sync to Notion。
