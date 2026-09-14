"""批量整理提案（approval mode）。数据即提案：批准后 `zc.py apply` 直接读 P / RENAMES / RETAG / UNTAG / UNCOLLECT。
`python3 zc.py proposal` -> 生成 proposals/proposal.md（不进 git）。
第一轮（2026-09-11）的 122 条已全部写入；现在这个文件的活跃部分是末尾的 RETAG / UNTAG / UNCOLLECT / EXTRA_TAGS（词表改名、纠错）。
"""
from zotero_claude import localdb
from zotero_claude.config import PROPOSAL_MD
rows = {r["key"]: r for r in localdb.load()}

DM, MISC, EA, HUM = "Dex-Manipulation", "AI Foundation", "Evolution Algorithm", "Humanoid"   # Misc 已改名 AI Foundation（分类 key 不变 DU25RH7B）；Humanoid 2026-09-12 新建

# key: (collections, method, embod, tech, base, modality, status, note)
P = {
 # ---- 机器人 / 机器学习 ----
 "TJVEBMX5": ([DM], ["rl"], ["dex-hand","single-arm"], [], [], ["point-cloud"], "to-read", "Allegro+xArm6, RealSense 点云; RL sim-to-real; 需改名"),
 "6N2GIDX8": ([DM], ["vla","policy-learning"], ["single-arm","gripper"], ["transformer"], [], ["vision","language"], "to-read", "22 种本体的数据集 + RT-1-X/RT-2-X; 需改名"),
 "HEPC5DYG": ([DM], ["policy-learning","rl"], ["gripper","bimanual"], ["diffusion"], [], ["point-cloud","tactile"], "to-read", "软夹爪+压阻触觉, 扩散策略→仿真 RL 微调; vision 是否作为策略输入不确定; 需改名"),
 "UHXQKX93": ([MISC], ["foundation-model"], [], ["transformer"], [], ["vision"], "to-read", "第一人称视频→手部/相机运动重建, 非操作策略; 用户原放 Dex-Hand, 按规则字面归 Misc, 请定; 需改名"),
 "6Z789W2Q": ([DM], ["foundation-model"], ["gripper","single-arm","bimanual"], [], [], ["vision","language"], "to-read", "VLM 智能体输出离散语义动作, 非 VLA; Franka / AgileX; 需改名"),
 "G4N8QAK5": ([DM], ["vla","rl"], ["single-arm","bimanual","dex-hand","gripper"], ["action-chunking","flow-matching","hil"], ["pi0.5"], ["vision","language"], "to-read", "UR5e 夹爪 / UR5e+LinkerHand L20 / Franka / 双 UR5e; 干预引导; 需改名"),
 "T4VUCZU3": ([MISC], ["rl"], [], [], [], [], "to-read", ""),
 "VSSQFTYT": ([MISC], ["policy-learning"], [], ["hil"], [], [], "to-read", "DAgger: 专家在线纠正, hil 按定义可贴"),
 "QNI7AFYZ": ([MISC], ["foundation-model"], [], [], [], [], "to-read", "通用视觉骨干"),
 "JPHILPLZ": ([MISC], [], [], [], [], [], "to-read", "数据集论文, 无 method 可贴"),
 "XXP5G5JF": ([MISC], ["rl","policy-learning"], [], [], [], [], "to-read", ""),
 "GELETITA": ([MISC], ["foundation-model"], [], ["transformer"], [], ["vision","language"], "to-read", "VLM 设计研究(OpenVLA 骨干), 未直接用于操作→Misc; 现有 VLA 分类保留"),
 "LHQ8VQN8": ([DM], ["policy-learning"], ["single-arm","gripper"], ["transformer"], [], ["vision","language"], "to-read", "Everyday Robots 移动操作臂; 从零训练, 非预训练 VLA"),
 "SS68RB8P": ([DM], ["vla"], ["single-arm","gripper"], ["transformer","latent-cot"], [], ["vision","language"], "to-read", "§4.4 有显式 CoT 变体实验"),
 "4LMBA5EH": ([DM], [], ["dex-hand","single-arm"], [], [], ["point-cloud"], "to-read", "抓取合成, 无合适 method → 提议 method:grasp-synthesis; 实机 xArm6+LEAP"),
 "DY3EK5IJ": ([DM, MISC], ["vla"], [], [], [], [], "to-read", "综述"),
 "LM59K4S9": ([DM], ["vla"], ["single-arm","gripper"], ["transformer"], [], ["vision","language"], "read", "18 条批注; WidowX / Google Robot / Franka"),
 "76P65UU8": ([DM], [], ["dex-hand","single-arm"], ["diffusion"], [], ["point-cloud"], "to-read", "图扩散抓取合成 → 提议 method:grasp-synthesis; 实机 xArm7+XHand/LEAP"),
 "TVGP9VKA": ([DM], ["rl"], ["dex-hand","single-arm"], ["diffusion"], [], [], "to-read", "Allegro+Franka; RL 预训练运动原语+扩散控制器, 遥操上层 → 也适用提议的 method:teleop"),
 "YDHBZJLQ": ([DM], [], ["dex-hand"], [], [], [], "to-read", "程序化抓取合成(无学习), Shadow/LEAP/Allegro/DClaw → 提议 method:grasp-synthesis"),
 "FGJSCC74": ([DM], ["rl","policy-learning"], ["dex-hand","bimanual"], [], [], [], "to-read", "仿真, Inspire/Shadow/MANO 浮动手无臂, bimanual 指双手"),
 "NSQ8FPP4": ([DM], ["policy-learning"], ["gripper","single-arm","bimanual"], ["diffusion","action-chunking"], [], ["vision","tactile"], "to-read", "Flexiv Rizon + GelSight Mini/MCTac; TactAR 遥操"),
 "XSU4KP7E": ([DM], ["policy-learning"], ["dex-hand"], ["diffusion","transformer"], [], ["point-cloud","tactile"], "to-read", "Shadow Hand, Kinect Azure 点云"),
 "G2KU4YKI": ([DM], ["rl"], ["dex-hand"], [], [], [], "to-read", "采样式物理重定向, method:rl 存疑; 人形 Fourier N1/H1-2/Booster T1 + XHand/Ability/Inspire → 提议 embod:humanoid, method:teleop"),
 "H4WFCLBL": ([HUM], ["rl"], ["humanoid"], [], [], [], "to-read", "BFM-Zero 人形全身控制的行为基础模型；2026-09-12 用户新建 Humanoid 分类，从 AI Foundation 移入"),
 "UCJ6JZJN": ([DM], ["policy-learning"], ["gripper","bimanual"], ["diffusion"], [], ["point-cloud","tactile"], "to-read", "鳍形软夹爪+触觉阵列, 3D 统一表征"),
 "Y5MYSGWE": ([DM], ["rl"], ["dex-hand"], [], [], ["point-cloud","tactile"], "read", "10 条批注; Allegro + 16 FSR"),
 "9K8NGI3X": ([DM], ["rl"], ["dex-hand"], [], [], ["tactile"], "to-read", "Allegro + FSR, 纯触觉无视觉"),
 "5A53QKFV": ([DM], ["rl"], ["dex-hand"], [], [], ["vision","tactile"], "to-read", "Shadow Hand(+LEAP); 视触觉预训练 + 在线多任务 RL"),
 "BYUSC5W3": ([MISC], ["rl"], [], [], [], [], "to-read", "赵世钰 RL 数学教材"),
 "BYQVDN6Z": ([DM], ["rl"], ["dex-hand","single-arm"], [], [], [], "to-read", "Sharpa + KUKA iiwa 14; 策略输入为物体位姿(FoundationPose 由 RGB-D 得到), modality 留空 [Uncertain]"),
 "JCNCQUXH": ([DM], ["rl"], ["dex-hand","single-arm"], [], [], ["vision"], "to-read", "xArm6+LEAP; 点轨迹来自 RGB 视频 CoTracker; RL+DAgger 蒸馏(仿真专家, 非人类)"),
 "B6GDMCM5": ([DM], ["rl"], ["dex-hand","single-arm","bimanual"], [], [], [], "to-read", "仿真 Allegro+Kuka, 单/双臂系统"),
 "Q9YJCM43": ([DM], ["rl"], ["dex-hand","bimanual"], ["transformer"], [], [], "to-read", "PPO; 仿真 Allegro/ArtiMano/Shadow 双手"),
 "6HWH2J5Y": ([DM], [], ["dex-hand","single-arm"], [], [], ["vision","depth"], "to-read", "遥操系统 → 提议 method:teleop; 模态指手部追踪输入 RGB(-D)"),
 "TC8RWRFC": ([DM], [], ["dex-hand","single-arm"], [], [], [], "read", "8 条批注 ✅; Allegro/LEAP+Franka, Manus 手套 → 提议 method:teleop"),
 "AP8LAAEQ": ([DM], ["vla","rl"], ["dex-hand","bimanual"], ["flow-matching"], ["pi0"], ["vision","language","tactile"], "to-read", "Sharpa 双臂, 10 指尖 6D 力; π0 骨干 + MoDE; RL 原子技能辅助遥操"),
 "U2WSL7NZ": ([DM], ["policy-learning"], ["dex-hand","gripper","single-arm"], ["transformer"], [], ["point-cloud"], "to-read", "UR5e + Azure Kinect; Inspire/LEAP/夹爪, 11 种末端; 3D 卷积"),
 "U78XLQT8": ([DM], ["policy-learning"], ["dex-hand","single-arm"], [], [], ["vision","tactile"], "to-read", "人手数据采集系统; 实机 RealMan RM-65 + Inspire RH56DFTP"),
 "BZVNNFPP": ([DM], ["vla"], ["dex-hand","bimanual"], ["flow-matching","transformer","action-chunking"], [], ["vision","language"], "to-read", "架构类 GR00T N1 但非微调 → 不贴 base; Galaxea R1Pro+Sharpa, Unitree G1 三指"),
 "MWAF9GHZ": ([DM], ["vla","rl"], ["gripper","bimanual"], ["action-chunking","hil"], [], ["vision","language"], "to-read", "1 条批注; 冻结 π0.6 → 提议 base:pi0.6; PI 双臂夹爪"),
 "AFZQFYKE": ([DM], ["vla"], ["gripper","bimanual"], ["flow-matching","action-chunking","latent-cot"], [], ["vision","language"], "to-read", "TRI LBM; 双 Franka; 显式 CoT 条件是实验变量之一"),
 "P8FKX826": ([DM], ["rl"], ["gripper","single-arm"], [], [], ["vision"], "to-read", "UR7e + Robotiq 2F-85, 无灵巧手; 蒸馏到 RGB 策略"),
 "FR9BMARE": ([DM], ["rl"], ["dex-hand"], [], [], ["tactile"], "to-read", "Columbia 自研手, 本体+二值触觉"),
 "SMPNMTCV": ([DM], ["policy-learning"], ["dex-hand"], ["transformer"], [], [], "to-read", "LEAP, BC 蒸馏专家策略"),
 "N84MPX5T": ([DM], ["vla","rl"], ["gripper","bimanual"], ["flow-matching","action-chunking","hil"], [], ["vision","language"], "to-read", "RECAP; π0.6 源自 π0.5 故贴 base:pi0.5; 静态双臂+移动"),
 "DS2CBILL": ([MISC], ["foundation-model"], [], [], [], [], "to-read", "1 条批注"),
 "7EUPJN44": ([DM], ["rl","foundation-model"], ["dex-hand"], [], [], [], "to-read", "LLM 写奖励; 仿真 Shadow Hand 转笔 + Isaac Gym 任务"),
 "N7NPRGW8": ([DM], [], ["dex-hand","bimanual"], [], [], ["vision","tactile"], "to-read", "双 UR7e + Sharpa Wave, Quest 3 → 提议 method:teleop"),
 "XDTPUAGX": ([DM], ["rl"], ["dex-hand"], [], [], [], "to-read", "仿真, Allegro/MANO/Sharpa Wave 各训一策略"),
 "6VBEISKD": ([DM], [], ["dex-hand","single-arm","bimanual"], [], [], [], "to-read", "MuJoCo 基准 Franka+Allegro, 含双手任务; 基线 π0/GR00T 不贴 base → 提议 type:benchmark"),
 "DEBKIIKT": ([DM], [], ["gripper","bimanual"], [], [], [], "to-read", "ARX X5 双臂仿真+实机基准 → 提议 type:benchmark"),
 "U3HFYV4Q": ([DM], ["rl"], ["dex-hand","single-arm"], [], [], [], "to-read", "Franka FR3 + LEAP/Sharpa Wave; RL 手-物共跟踪控制器 → 也提议 method:teleop"),
 "WI9XJC22": ([DM], ["rl","policy-learning"], ["dex-hand"], [], [], [], "read", "28 条批注 ✅; Allegro; 感知运动策略输入以本体为主, modality 留空"),
 "HHNYRU6X": ([DM], ["rl"], ["dex-hand"], [], [], [], "to-read", "2 条批注; Wuji Hand → 也提议 method:teleop(重定向)"),
 "62YYTP7B": ([DM], ["rl","world-model"], ["dex-hand"], [], [], [], "to-read", "LEAP; 关节级神经动力学模型补 sim-to-real"),
 "IHBAME45": ([DM], ["vla"], ["single-arm","bimanual","gripper","dex-hand"], ["latent-cot","flow-matching","transformer","action-chunking"], [], ["vision","language"], "read", "27 条批注; Janus-Pro/DeepSeek-LLM 1.5B 骨干; 10 实机任务含单/双臂/移动/灵巧手(正文已核)"),
 "SKVYZF8Z": ([DM], ["vla","world-model"], ["bimanual","gripper","dex-hand"], ["latent-cot","transformer","flow-matching"], [], ["vision","language"], "to-read", "Galaxea R1 Lite / Tianji Marvin / +WUJI; 辅助动作条件世界模型"),
 "QNGIGW87": ([DM], ["world-model"], ["gripper","single-arm"], ["transformer"], [], [], "to-read", "执行器动力学模型, method:world-model 是最接近项 [Uncertain]; OpenManipulator-X / SO-101 / Franka"),
 "493QZDBC": ([DM], ["vla"], ["gripper","bimanual"], ["flow-matching","action-chunking","latent-cot"], [], ["vision","language"], "to-read", "π 系列新模型本身, 不贴 base; 子任务语言/子目标图像预测计入 latent-cot; UR5e 双臂/BiPi/移动"),
 "FD8M3XF9": ([DM], ["rl","policy-learning"], ["gripper","dex-hand","single-arm","bimanual"], ["diffusion","action-chunking"], [], ["vision","point-cloud"], "to-read", "UR5 / Franka+LeapHand / xArm; 实机 RL; 无 hil"),
 "FBQP3MT6": ([DM], ["vla"], ["dex-hand","bimanual"], ["flow-matching","transformer","action-chunking"], [], ["vision","language","tactile"], "to-read", "❗; Dexmate Vega-1 + 2×Sharpa Wave; Qwen3VL-2B 骨干"),
 "6Z4ZT39B": ([DM], ["policy-learning"], ["bimanual","gripper"], ["action-chunking","transformer"], [], ["vision"], "read", "13 条批注; ALOHA 硬件, 无语言"),
 "NGHC33K8": ([MISC], [], [], ["flow-matching"], [], [], "to-read", "生成模型基础"),
 "TUJ2QVRF": ([MISC], [], [], [], [], [], "to-read", ""),
 "LBVV96ZC": ([MISC], [], [], [], [], [], "to-read", ""),
 "F3S4VXE6": ([MISC], [], [], [], [], [], "to-read", ""),
 "YDF9BT4L": ([DM], ["policy-learning"], ["single-arm","gripper"], ["flow-matching","action-chunking"], [], ["vision"], "to-read", "1 条批注; Franka 实机 + RoboVerse/LIBERO"),
 "ESK4SDNZ": ([DM, MISC], ["world-model"], [], [], [], [], "to-read", "综述"),
 "Q2IUL8SA": ([DM], ["policy-learning"], ["dex-hand","bimanual"], ["transformer"], [], ["vision","tactile"], "to-read", "❗; 2×Sharpa Wave, ZED 立体+腕部视角"),
 "9NRZ28N7": ([DM], ["rl"], ["dex-hand","single-arm"], [], [], [], "to-read", "❗; LEAP/WUJI; 单示范重定向 + 残差 RL"),
 "L23X3VK2": ([DM], ["world-model","policy-learning"], ["dex-hand","bimanual"], ["flow-matching","action-chunking","transformer"], [], ["vision","tactile"], "to-read", "❗; 双臂双 Sharpa Wave + 触觉; language 是否为输入不确定"),
 "JZIDFYCI": ([DM], ["policy-learning"], ["dex-hand","single-arm"], [], [], ["tactile"], "to-read", "RealMan + Inspire 触觉手(1062 维); 人手手套数据; vision 是否输入不确定"),
}

# ---- 进化算法 (全部 Evolution Algorithm, 只贴 status:to-read) ----
EA_KEYS = [k for k, r in rows.items() if EA in r["collections"] or k == "Z6QB6YQG"]
for k in EA_KEYS:
    P[k] = ([EA], [], [], [], [], [], "to-read", "")
P["Z6QB6YQG"] = ([EA], [], [], [], [], [], "to-read", "原未归类")
P["KNFD9629"] = ([EA], [], [], [], [], [], "to-read", "与 GUHVP29Z 同一 PDF(重复条目), 规则不删, 请定")
P["GUHVP29Z"] = ([EA], [], [], [], [], [], "to-read", "与 KNFD9629(HS2001) 重复; 需改名")

# ---- 2026-09-11 用户批准后的修订（AskUserQuestion 答复）----
# H4WFCLBL 的 2026-09-11 修订（归 AI Foundation）已被 2026-09-12 的 Humanoid 分类取代，见上面 P 里的行
P["UHXQKX93"] = ([DM], ["foundation-model"], [], ["transformer"], [], ["vision"], "to-read", "用户指示归 Dex-Manipulation; 需改名")
def _add(key, fam, val):
    c, m, e, t, b, mo, s, n = P[key]; fams = {"method": m, "embod": e, "tech": t, "base": b, "modality": mo}
    if val not in fams[fam]: fams[fam].append(val)
    P[key] = (c, fams["method"], fams["embod"], fams["tech"], fams["base"], fams["modality"], s, n)
for k in ("6HWH2J5Y", "TC8RWRFC", "N7NPRGW8", "U3HFYV4Q", "HHNYRU6X", "G2KU4YKI", "TVGP9VKA", "AP8LAAEQ"):
    _add(k, "method", "teleop")
P["G2KU4YKI"] = ([DM, HUM], ["teleop"], *P["G2KU4YKI"][2:])   # SPIDER: 去掉存疑的 rl；2026-09-12 用户定：灵巧手重定向 + 人形全身重定向各半，两个分类都放
for k in ("4LMBA5EH", "76P65UU8", "YDHBZJLQ"):
    _add(k, "method", "grasp-synthesis")
for k in ("H4WFCLBL", "G2KU4YKI", "BZVNNFPP"):
    _add(k, "embod", "humanoid")
_add("MWAF9GHZ", "base", "pi0.6")
# 2026-09-12 用户批准（翻正文核过）：SPIDER 3 个双手数据集/8 个双手任务；Eureka 的 Dexterity 套件是 20 个双 Shadow Hand 仿真任务
_add("G2KU4YKI", "embod", "bimanual")
_add("7EUPJN44", "embod", "bimanual")
# 2026-09-12 全库复核（/goal "确保无误"），正文核过：
_add("NSQ8FPP4", "method", "teleop")          # RDP：TactAR 遥操系统是论文列出的贡献之一
_add("6Z4ZT39B", "method", "teleop")          # ALOHA/ACT：ALOHA 遥操硬件是贡献之一
_add("FBQP3MT6", "tech", "diffusion")         # T-Rex："we propose a visual-tactile diffusion policy" 做高频触觉反应细化
_add("6Z789W2Q", "tech", "action-chunking")   # Show-Harness："Action Chunking" 是 Harness 的组件之一
UNTAG = {"N84MPX5T": ["base:pi0.5"]}           # π0.6 论文：π0.6 是新模型（Gemma 3 4B 骨干，"derived from π0.5" 指配方），不是微调 π0.5 → 按规则不贴
# type: 轴（与 method 正交）
EXTRA_TAGS = {"DY3EK5IJ": ["type:survey"], "ESK4SDNZ": ["type:survey"],
              "6VBEISKD": ["type:benchmark"], "DEBKIIKT": ["type:benchmark"],
              "6N2GIDX8": ["type:dataset"], "JPHILPLZ": ["type:dataset"]}
APPROVED_NEW = {"method:teleop", "method:grasp-synthesis", "embod:humanoid", "base:pi0.6", "type:survey", "type:benchmark", "type:dataset"}

# ---- 标题补前缀 (只针对仍是导入原始标题的条目) ----
UNCOLLECT = {"H4WFCLBL": [MISC]}   # 从分类里移出（apply 唯一会摘分类的路径）：BFM-Zero 移到 Humanoid 后不再留在 AI Foundation
RETAG = {"embod:dual-arm": "embod:bimanual"}   # 词表改名：apply 会把库里所有旧标签换成新标签（含 P 之外的条目），2026-09-12 用户合并 dual-arm→bimanual
RENAMES = {}   # 第一轮的 15 条改名已于 2026-09-11 写入并被之后的全库 [YYYY-MMDD] 改名覆盖（老→新对照在日志里）；再放东西进来前先看现有标题

NEW_TAGS = []   # 第一轮提议的 teleop/grasp-synthesis/humanoid/pi0.6/type:* 已于 2026-09-11 批准并写进 CLAUDE.md 词表；再提新标签放这里（tag, 理由, 需要它的条目）

def short(r):
    t = r["title"]
    return (t[:58] + "…") if len(t) > 60 else t

def md():
    out = ["# Zotero 整理提案 — 第一轮（未写入任何内容）", "",
           f"共 {len(P)} 条 = 库中全部 {len(rows)} 篇。分类只增不减：原有 Dex-Hand / VLA / AI Learning / World Model 归属全部保留。",
           "`status:` 规则：有 ≥8 条高亮批注 → `read`，其余 `to-read`。", ""]
    out += ["## A. 机器人 / 机器学习（73 篇）", "",
            "| # | Title | Collection(s) | method: | embod: | tech: | base: | modality: | status: | Note |",
            "|---|-------|---------------|---------|--------|-------|-------|-----------|---------|------|"]
    i = 0
    order = [k for k in P if EA not in P[k][0] and k in rows]   # 回收站里的（如 Z6QB6YQG）不在 dump 里，跳过
    for k in order:
        i += 1; c, m, e, t, b, mo, s, n = P[k]; r = rows[k]
        d = lambda l: ", ".join(l) if l else "—"
        out.append(f"| {i} | {short(r)} `{k}` | {', '.join(c)} | {d(m)} | {d(e)} | {d(t)} | {d(b)} | {d(mo)} | {s} | {n} |")
    out += ["", "## B. 进化算法（49 篇，含原未归类的 NSM-SFS 2023）", "",
            "全部 → `Evolution Algorithm` + `status:to-read`；method/embod/tech/modality 家族对这批不适用，留空。", "",
            "| # | Title | Note |", "|---|-------|------|"]
    for k in [k for k in P if EA in P[k][0] and k in rows]:
        i += 1; out.append(f"| {i} | {short(rows[k])} `{k}` | {P[k][7]} |")
    out += ["", "## C. 标题补前缀（仅原始导入标题，你自己起过名的一律不动）", "",
            "格式按你说的 `[date] [刊/会] xxx`。arXiv 论文取 v1 提交日；期刊论文只有年月，写 `[YYYY-MM]`；无会议/期刊的纯 arXiv 省略第二个括号（与你现有 `[2026-0831] ❗ Motus2` 一致）。",
            "注意：你在进化算法分类里已有的是另一套 `[ESWA] [2024] EEFO` 风格，第 7–15 行若想改成那种，告诉我即可。", "",
            "| # | key | 现标题 | 提议标题 |", "|---|-----|--------|----------|"]
    for j, (k, new) in enumerate(RENAMES.items(), 1):
        out.append(f"| {j} | `{k}` | {rows[k]['title'][:70]} | {new} |")
    out += ["", "## D. 分类结构（需批准）", "",
            "1. 新建根分类 `Misc`（规则 §1 要求存在，库里目前没有）。",
            "2. 每篇加入对应根分类；**不移除**任何现有分类归属。",
            "3. 可选：把 `Dex-Hand`、`VLA`、`World Model` 挂为 `Dex-Manipulation` 的子分类，`AI Learning` 挂为 `Misc` 的子分类——规则说子分类可提议不可擅建，你点头我再动。",
            "4. `Humanoid` / `Imitation Learning` / `Reinforcement Learning` 三个分类是空的，规则不许删，仅告知。",
            "5. `KNFD9629`(HS2001) 与 `GUHVP29Z` 是同一篇 Harmony Search 的重复条目，规则不许删，仅告知。", "",
            "## E. 提议新增标签（未获批前不会使用）", "",
            "| 标签 | 理由 | 需要它的条目 |", "|------|------|--------------|"]
    for tag, why, items in NEW_TAGS:
        out.append(f"| `{tag}` | {why} | {items} |")
    out += ["", "## F. Uncertain（按规则留空不猜）", "",
            "- `BYQVDN6Z` SimToolReal：策略输入是物体位姿，RGB-D 只在上游管线，modality 留空",
            "- `QNGIGW87` NeuralActuator：执行器动力学模型，`method:world-model` 是最接近但不精确",
            "- `G2KU4YKI` SPIDER：采样式物理重定向，`method:rl` 存疑",
            "- `HEPC5DYG` VT-Refine / `L23X3VK2` Motus2 / `JZIDFYCI` UniTacHand：vision / language 是否为策略输入未在正文确认",
            "- `H4WFCLBL` BFM-Zero / `UHXQKX93` MINT：按规则归 Misc，但你原来放在 Dex-Hand，请定",
            ""]
    return "\n".join(out)

def run(argv=()):
    open(PROPOSAL_MD, "w", encoding="utf-8").write(md())
    n_dm = sum(1 for v in P.values() if DM in v[0]); n_misc = sum(1 for v in P.values() if MISC in v[0]); n_ea = sum(1 for v in P.values() if EA in v[0])
    print(f"rows={len(P)} (lib={len(rows)}) | Dex-Manipulation={n_dm} Misc={n_misc} EA={n_ea} | renames={len(RENAMES)}")
    missing = set(rows) - set(P); extra = set(P) - set(rows)
    print("missing:", missing, "extra:", extra)
