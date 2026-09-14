"""规则式自动分类 + 贴标签（CLAUDE.md §2 分类、§3 词表的判定规则写成代码；证据来自标题 + 摘要 + 正文）。

    suggest(title, abstract, text) -> dict(collection, also, sure, maybe, flags, evidence)

三档输出：
  sure  —— 按规则够得上"实质用到"，`zc.py add` 直接贴
  maybe —— 边缘候选（只在正文零星出现、或被排他规则压下去的），不贴，汇报里列给用户讨论后 `zc.py tag` 补
  flags —— 需要人看一眼的提示（分类边界、embod 判不出、没有正文只靠摘要…）
判定原则：标题/摘要里出现 = 论文自己说的，可信；正文里要出现够多次（相关工作/基线里提一嘴通常只有几次）。
阈值是拿库里 129 篇已人工核过标签的条目调出来的（tools/eval_classify.py），改规则后重跑看精确率。
参考文献段先切掉，否则引用的 "Diffusion Policy" "ALOHA" 全会误命中。
"""
import re
from .vocab import EA, DM, HUM, AIF

# ---- 每个标签：pats = [(regex, 权重)]；sure = 正文命中数够这个就贴；maybe = 够这个就列为候选；
#      head = 标题/摘要里出现是否直接算 sure（False 的标签光摘要提到不够，比如 teleop 常是"用遥操收数据"而非贡献）
T = lambda pats, sure, maybe=1, head=True: dict(pats=pats, sure=sure, maybe=maybe, head=head)
RULES = {
 # method
 "method:vla": T([(r"vision[- ]language[- ]action", 2), (r"\bVLAs?\b", 2), (r"\bOpenVLA\b|\bRT-2\b|\bGR00T\b|\bSmolVLA\b", 1)], sure=20, maybe=6),
 "method:policy-learning": T([(r"imitation learning|behaviou?r(al)? cloning|learning from (human )?demonstrations?", 2),
                              (r"diffusion polic(y|ies)|action chunking transformer|visuomotor polic(y|ies)", 1)], sure=20, maybe=4),
 "method:rl": T([(r"reinforcement learning|\bRL\b", 2), (r"\bPPO\b|reward (function|design|shaping)|policy gradient|actor[- ]critic", 1)], sure=24, maybe=6),
 "method:world-model": T([(r"world[- ](action[- ])?models?", 2), (r"(learned |neural )?dynamics model|video prediction|model-based (RL|reinforcement|planning)|imagin(ed|ation) rollouts?", 1)], sure=999, maybe=6),
 "method:foundation-model": T([(r"foundation models?", 2), (r"vision[- ]language models?|\bVLMs?\b|large language models?|\bLLMs?\b|pre-?trained (backbone|encoder|representation)s?|self-supervised (pre-?training|learning)|representation learning", 1)], sure=999, maybe=8),
 "method:teleop": T([(r"teleoperat", 2), (r"retarget|data ?gloves?|exoskeleton|motion capture|\bmocap\b|VR (headset|controller)|Apple Vision Pro|Meta Quest|hand tracking", 1)], sure=999, maybe=8, head=False),
 "method:grasp-synthesis": T([(r"grasp (synthesis|generation)|dexterous grasp(ing|s)?\b", 2), (r"grasp (pose|sampling|detection|proposal)s?|grasp candidates", 1)], sure=999, maybe=6),
 # embod（硬件名在正文里出现够多 = 真用了；只出现几次多半是相关工作/基线）
 "embod:dex-hand": T([(r"dexterous hands?|multi-?finger(ed)? hands?|five-?finger(ed)? hands?|anthropomorphic hands?|robot(ic)? hands?", 2),
                      (r"\bAllegro\b|\bLEAP hand|\bShadow hand|\bInspire\b|\bXHand\b|\bSharpa\b|\bAbility hand|\bDClaw\b|\bLinkerHand|\bWuji\b|\bTesollo\b|\bRobotEra\b|\bDexHand\b|\bBrainCo\b|\bMANO\b|\bDLR hand", 2)], sure=8, maybe=2),
 "embod:gripper": T([(r"parallel[- ]jaw|\bRobotiq\b|2F-85|Franka hand|two-finger grippers?|suction cup", 2), (r"\bgrippers?\b", 1)], sure=10, maybe=3),
 "embod:single-arm": T([(r"single[- ]arm", 2), (r"\bFranka\b|\bPanda\b|\bUR ?5e?\b|\bUR ?10e?\b|\bUR ?7e\b|\bUR ?3e?\b|\bxArm\b|\bKinova\b|\bKUKA\b|\biiwa\b|\bWidowX\b|\bFlexiv\b|\bRizon\b|\bRealMan\b|\bRM-65\b|\bSawyer\b|\bJaco\b|\bPiper\b|\bSO-?10[01]\b|\bKoch\b|\bViperX\b|\b7-DoF arm", 2), (r"robot(ic)? arms?", 1)], sure=6, maybe=2),
 "embod:bimanual": T([(r"bimanual|dual[- ]arm|two[- ]arm(ed|s)?|both arms|two robot hands|two[- ]handed", 2), (r"\bALOHA\b|Mobile ALOHA|\bAgileX\b|\bARX\b|\bBiPi\b", 2)], sure=10, maybe=3),
 "embod:humanoid": T([(r"humanoid robots?|humanoids?\b(?=[^.]{0,40}(robot|control|whole[- ]body|locomotion|loco|polic|platform|teleop|hardware))", 2),
                      (r"\bUnitree (G1|H1)|\bFourier (GR|N1)|\bBooster T1|\bTienKung|\bTien Kung|\bGalaxea R1|\bDexmate\b|\bFigure 0[12]|\bEngineAI\b|\bAgiBot\b|\bBerkeley Humanoid|\bG1 humanoid|\bH1 humanoid", 2)], sure=12, maybe=3),
 # tech（transformer / diffusion 谁都提，只认论文自己说的或正文大量出现）
 "tech:action-chunking": T([(r"action[- ]chunk(ing|s|ed)?|chunked actions?|temporal ensembl", 2)], sure=6, maybe=2),
 "tech:flow-matching": T([(r"flow[- ]matching|rectified flow|conditional flow", 2)], sure=6, maybe=2),
 "tech:diffusion": T([(r"diffusion (polic(y|ies)|models?|transformers?|process|head|decoder)|denoising|\bDDPM\b|\bDDIM\b|score[- ]based", 2)], sure=999, maybe=15),
 "tech:transformer": T([(r"transformer(-based| encoder| decoder| backbone| polic(y|ies)| architecture)|\bViT\b|vision transformer", 2), (r"\btransformers?\b|self-attention|cross-attention", 1)], sure=15, maybe=6),
 "tech:hil": T([(r"human[- ]in[- ]the[- ]loop|human (intervention|correction)s?|interactive imitation|\bHG-DAgger|intervention data|human feedback during", 2)], sure=30, maybe=3),
 "tech:latent-cot": T([(r"chain[- ]of[- ]thought|\bCoT\b|embodied reasoning|latent reasoning|reasoning (tokens|traces|steps)|think(ing)? before act|subtask prediction", 2)], sure=999, maybe=5),
 # base（还要有微调/冻结语境，见 BASE_CTX；标题里就是这个模型 = 论文提出的就是它，不贴）
 "base:pi0": T([(r"\bπ0\b|\bπ_?0\b(?![.\d])|\bpi[_-]?0\b(?![.\d])|\bpi-zero\b", 2)], sure=999, maybe=1, head=False),
 "base:pi0.5": T([(r"π_?0\.5|pi[_-]?0\.5", 2)], sure=999, maybe=1, head=False),
 "base:pi0.6": T([(r"π_?0\.6|pi[_-]?0\.6", 2)], sure=999, maybe=1, head=False),
 "base:gr00t": T([(r"\bGR00T\b|\bGROOT\b", 2)], sure=999, maybe=1, head=False),
 # modality（只标策略真正消费的输入；VLA 一律 vision+language，见下）
 "modality:vision": T([(r"\bRGB\b|wrist cameras?|camera images?|image observations?|visual observations?|visual inputs?|from (raw )?pixels|monocular|stereo cameras?|\bcameras?\b|egocentric|visuomotor", 2)], sure=25, maybe=6),
 "modality:language": T([(r"language[- ]conditioned|language instructions?|text instructions?|natural language (commands?|instructions?|goals?)|instruction[- ]following|language goals?|free-form language|language prompts?", 2), (r"\binstructions?\b", 1)], sure=30, maybe=8),
 "modality:tactile": T([(r"tactile", 2), (r"\bGelSight\b|\bFSR\b|force[- ]torque|\bF/T sensor|contact (force|sensing|sensors?)|touch sens", 1)], sure=25, maybe=5),
 "modality:depth": T([(r"depth (images?|maps?|cameras?|observations?|sensors?)|\bRGB-?D\b", 2)], sure=40, maybe=5),
 "modality:point-cloud": T([(r"point[- ]clouds?", 2), (r"\bLiDAR\b", 1)], sure=20, maybe=5),
 "modality:audio": T([(r"\baudio\b|microphones?|acoustic", 2)], sure=999, maybe=5),
}
BASE_CTX = r"fine-?tun\w*|finetun\w*|initializ\w*|built (up)?on|post-?train\w*|fr(eez|ozen)\w*|starting from|adapt\w*|checkpoints?|pre-?trained weights|as (our|the) (base|backbone|initialization)"
# 分类判定用的题眼（标题 + 摘要；摘要空的老条目再看正文）
EA_RE = re.compile(r"evolutionary|genetic algorithm|particle swarm|swarm intelligence|meta-?heuristic|differential evolution|nature-inspired|bio-inspired|"
                   r"optimization algorithms?|\boptimizer\b|grey wolf|whale optimi|harmony search|bee colony|ant colony|simulated annealing|firefly|cuckoo|"
                   r"multi-objective|benchmark functions|test functions|CEC ?20\d\d|engineering design problems|exploration and exploitation|population-based|fitness", re.I)
ROBOT_RE = re.compile(r"\brobots?\b|robotic|manipulat|grasp|gripper|dexterous|teleoperat|embodied|end[- ]effector|sim-to-real|humanoid", re.I)
HUM_CORE = re.compile(r"whole[- ]body|locomotion|loco-?manipulation|humanoid (control|motion|behavio)|motion (tracking|imitation|retargeting)|walking|\bgait\b|bipedal|legged", re.I)
MANIP_CORE = re.compile(r"manipulat|grasp|dexterous|in-hand|pick[- ]and[- ]place|bimanual|tabletop|assembly|tool use", re.I)
REFS_RE = re.compile(r"\n\s*(references|bibliography)\s*\n", re.I)


def _cut_refs(text):
    """切掉参考文献段（取最后一个 References 标题之后的都扔；附录在它前面的保留）。"""
    if not text: return ""
    hits = list(REFS_RE.finditer(text))
    if not hits: return text
    cut = hits[-1].start()
    return text[:cut] if cut > len(text) * 0.3 else text        # 太靠前的不是真的参考文献标题（比如目录里）


def _snip(text, m, n=70):
    a, b = max(0, m.start() - n), min(len(text), m.end() + n)
    return re.sub(r"\s+", " ", text[a:b]).strip()


def _rx(pat):
    return re.compile(pat, 0 if re.search(r"\\b[A-Z]|[A-Z]{2}", pat) else re.I)   # 含大写专名的模式区分大小写（"Panda" "RL" "ACT"）


NEG_CTX = re.compile(r"(unlike|without|instead of|rather than|compared (to|with)|not (require|rely|need)|beyond|alternative to|in contrast to|limitations? of|"
                     r"prior|existing|previous|conventional|traditional|alternatives? (such as|like)|categorized|strategies|approaches|methods|such as)\b[^.]{0,50}$", re.I)


def _score(tag, title, abstract, body):
    """dict(head=标题/摘要命中数, body=正文命中数, ev=证据片段)。"""
    head = title + "\n" + abstract
    head_hits = body_hits = 0; ev = []
    for pat, w in RULES[tag]["pats"]:
        r = _rx(pat)
        for m in r.finditer(head):
            if w < 2: continue                                              # 弱模式（"instruction" "gripper" 之类）在摘要里出现也不算论文自己说的
            if tag.startswith("method:") and NEG_CTX.search(head[max(0, m.start() - 60):m.start()]): continue   # "unlike imitation learning…" 不算
            head_hits += 1
            if len(ev) < 2: ev.append(("摘要" if m.start() > len(title) else "标题", _snip(head, m)))
        ms = list(r.finditer(body))
        body_hits += len(ms) * w
        if ms and len(ev) < 2: ev.append((f"正文×{len(ms)}", _snip(body, ms[0])))
    return dict(head=head_hits, body=body_hits, ev=ev)


def suggest(title, abstract, text, has_pdf=True):
    title, abstract = title or "", abstract or ""
    body = _cut_refs(text or "")
    head_txt = title + "\n" + abstract
    S = {t: _score(t, title, abstract, body) for t in RULES}
    sure, maybe, flags, evidence = [], {}, [], {}

    def level(tag):
        s, r = S[tag], RULES[tag]
        if (s["head"] and r["head"]) or s["body"] >= r["sure"]: return "sure"
        if s["head"] or s["body"] >= r["maybe"]: return "maybe"
        return None
    def fam(prefix): return [t for t in RULES if t.startswith(prefix)]
    def pick(prefix, why="正文出现 {n} 次、摘要没提，可能只是相关工作/基线"):
        got = []
        for t in fam(prefix):
            lv = level(t)
            if lv == "sure": got.append(t)
            elif lv == "maybe": maybe[t] = why.format(n=S[t]["body"])
        return got

    # ---- type（只看标题和摘要里"我们提出"）----
    for t, rx in (("type:survey", r"\bsurvey\b|\breview\b"), ("type:benchmark", r"benchmarks?\b"), ("type:dataset", r"\bdatasets?\b|\bdatabase\b")):
        if re.search(rx, title, re.I) or (t != "type:survey" and re.search(r"\bwe (introduce|present|release)\b[^.]{0,30}\b(" + rx.strip("\\b") + r")", abstract, re.I)):
            sure.append(t)
    survey = "type:survey" in sure; bench = "type:benchmark" in sure

    # ---- method ----
    meth = pick("method:")
    if "method:teleop" not in meth and S["method:teleop"]["head"]:              # 摘要提遥操：得是贡献（"we ... teleoperation system"），不是"用遥操收数据"
        if re.search(r"teleoperat", title, re.I) or re.search(r"\b(we|our)\b[^.]{0,60}\b(propose|present|introduce|develop|build|design)\b[^.]{0,60}(teleoperat|retarget)|(teleoperation|teleop|retargeting) (system|framework|interface|pipeline|device|setup)", head_txt, re.I):
            meth.append("method:teleop"); maybe.pop("method:teleop", None)
        elif re.search(r"retarget", title, re.I): maybe["method:teleop"] = "标题有 retargeting：人手→机器手重定向算 teleop，但纯仿真/单示范的重定向不算，请定"
        else: maybe["method:teleop"] = "摘要提到遥操，但像是用来收示教数据，不是论文贡献"
    if "method:vla" in meth and "method:policy-learning" in meth:
        maybe["method:policy-learning"] = "有 VLA 骨干时示教学习不另贴（词表：policy-learning = 无大 VLA 骨干的示教学习）"; meth.remove("method:policy-learning")
    if "method:foundation-model" in meth and any(t in meth for t in ("method:vla", "method:policy-learning", "method:rl", "method:teleop", "method:grasp-synthesis")):
        maybe["method:foundation-model"] = "论文本身是动作模型/控制器（foundation-model 只贴本身不是动作模型的 VLM/LLM/骨干，BFM-Zero 也只贴 rl）"; meth.remove("method:foundation-model")
    ranked = sorted(meth, key=lambda t: -(S[t]["head"] * 100 + S[t]["body"]))
    for t in ranked[2:]: maybe[t] = f"method 每篇最多 2 个，它排第 {ranked.index(t) + 1}"
    meth = ranked[:2]

    # ---- embod ----
    emb = pick("embod:", "只在正文出现 {n} 次（可能是相关工作/基线）")
    if "embod:bimanual" in emb and "embod:single-arm" in emb and not (re.search(r"single[- ]arm", head_txt, re.I) or len(re.findall(r"single[- ]arm", body, re.I)) >= 3):
        emb.remove("embod:single-arm"); maybe["embod:single-arm"] = "臂名出现但论文是双臂系统，没有明说 single-arm（多平台才两个都贴）"

    # ---- tech ----
    tech = pick("tech:")
    if "tech:flow-matching" in tech and "tech:diffusion" in tech and not re.search(r"diffusion", title, re.I):
        tech.remove("tech:diffusion"); maybe["tech:diffusion"] = "流匹配论文的摘要里提扩散多半是对比，不是用了扩散"

    # ---- base：要有微调/冻结语境 ----
    base = []
    for t in fam("base:"):
        s = S[t]
        if not s["head"] and not s["body"]: continue
        name = RULES[t]["pats"][0][0]
        if re.search(name, title, re.I): maybe[t] = "标题里就是这个模型——论文提出的就是它本身，不贴 base"; continue
        ctx = _rx(r"(" + BASE_CTX + r")[^.]{0,60}(" + name + r")|(" + name + r")[^.]{0,60}(" + BASE_CTX + r")")
        if survey or bench: maybe[t] = "综述/基准里提到，不是微调"; continue
        hm, bm = list(ctx.finditer(head_txt)), list(ctx.finditer(body))
        if hm: base.append(t); S[t]["ev"] = [("摘要·微调语境", _snip(head_txt, m)) for m in hm[:2]]
        elif len(bm) >= 2: maybe[t] = f"正文 {len(bm)} 处微调/冻结语境但摘要没说，确认是真微调还是基线"; S[t]["ev"] = [("正文·微调语境", _snip(body, bm[0]))]
        else: maybe[t] = "提到了模型名但没看到微调/冻结的语境（架构类似或基线不贴 base）"
    if "base:pi0.5" in base and "base:pi0" in base: base.remove("base:pi0")   # π0.5 的引用里必然带 π0

    # ---- modality（只标策略真正消费的输入）----
    mod = pick("modality:", "正文出现 {n} 次，未确认是策略输入")
    if "method:vla" in meth:                                                   # VLA 按定义吃图像 + 语言
        for t in ("modality:vision", "modality:language"):
            if t not in mod: mod.append(t); maybe.pop(t, None)
    if "modality:vision" in mod and not S["modality:vision"]["head"] and any(t in mod for t in ("modality:point-cloud", "modality:depth")) and "method:vla" not in meth:
        mod.remove("modality:vision"); maybe["modality:vision"] = "相机可能只用来生成点云/深度，摘要没说策略吃 RGB"

    # ---- 分类 ----
    robot_h = len(ROBOT_RE.findall(head_txt)); ea_h = len(EA_RE.findall(head_txt))
    robot_b = len(ROBOT_RE.findall(body)); ea_b = len(EA_RE.findall(body))
    hum = "embod:humanoid" in emb; hum_core = bool(HUM_CORE.search(head_txt)); manip_t = bool(MANIP_CORE.search(title)); manip_a = bool(MANIP_CORE.search(abstract))
    also = None
    if (ea_h >= 2 and robot_h <= 1) or (ea_h + robot_h == 0 and ea_b >= 15 and robot_b <= 3):
        coll = EA; meth, emb, tech, base, mod, maybe = [], [], [], [], [], {}; sure = [t for t in sure if t == "type:survey"]
        flags.append("Evolution Algorithm：按规则只贴 status")
    elif hum and hum_core and not manip_t:
        coll = HUM
        if manip_a: flags.append("Humanoid / Dex-Manipulation 边界：摘要也提操作——研究对象是人形本身才归 Humanoid，在人形上做操作归 Dex-Manipulation（+embod:humanoid）")
    elif emb or robot_h >= 2 or manip_t or (manip_a and robot_h >= 1):
        coll = DM
        if hum and hum_core: flags.append("也涉及人形全身（whole-body/locomotion）：既做灵巧手又做人形全身的可 --also Humanoid")
    else:
        coll = AIF
        if robot_h: flags.append(f"摘要有 {robot_h} 处机器人相关词但没判出本体/操作题眼，确认是否该归 Dex-Manipulation")
        for t in emb: maybe[t] = "归 AI Foundation 的纯 learning 论文，本体词可能只是仿真环境（MuJoCo Humanoid 不算）"
        emb = []; base = []; maybe = {t: w for t, w in maybe.items() if not t.startswith("base:")}   # RL 理论文里的 π0 是初始策略记号，不是 π0 模型
    if coll == DM and survey: also = AIF
    if coll == DM and not emb: flags.append("embod 判不出，留空（Uncertain）")
    if coll in (DM, HUM) and not meth: flags.append("method 判不出，留空")
    if coll == AIF and not meth and not survey: flags.append("method 判不出（经典 ML 论文常常不贴，和库里 VAE/t-SNE 一致）")
    if not has_pdf: flags.append("没有正文，只靠摘要判的：标签偏少，PDF 拖进去后可再 tag 补")

    if survey:                                                                 # 综述：本体/机制/模态都是在讲别人，只留标题/摘要里的 method
        meth = [t for t in meth if S[t]["head"]]; emb, tech, base, mod = [], [], [], []; maybe = {}
        flags.append("综述：只贴 type:survey + 标题/摘要点名的 method，embod/tech/modality 不贴")
    elif bench:                                                                # 基准：本体是真的（跑了实机/仿真），机制/模态/方法是基线的
        meth = [t for t in meth if S[t]["head"]]; tech, base, mod = [], [], []
        maybe = {t: w for t, w in maybe.items() if t.startswith("embod:")}
        flags.append("基准/工具集：贴 type + embod，method 只留标题/摘要点名的；基线用的 VLA/扩散不贴")
    sure = sure + meth + emb + tech + base + mod
    for t in sure: evidence[t] = S[t]["ev"][:2] if t in S else []
    for t in maybe: evidence[t] = S[t]["ev"][:1] if t in S else []
    return dict(collection=coll, also=also, sure=sure, maybe=maybe, flags=flags, evidence=evidence)


def fmt(sg, width=150):
    """打印成人能扫一眼的证据块。"""
    out = [f"  分类    : {sg['collection']}" + (f" + {sg['also']}" if sg["also"] else "")]
    out.append("  贴      : " + (", ".join(sg["sure"]) or "(只有 status)"))
    for t in sg["sure"]:
        for where, s in sg["evidence"].get(t, []): out.append(f"      {t:<24} ← {where}: …{s[:width]}…")
    if sg["maybe"]:
        out.append("  候选    : （不贴，汇报里和用户讨论）")
        for t, why in sg["maybe"].items():
            ev = sg["evidence"].get(t) or []
            out.append(f"      {t:<24} {why}" + (f"  ← {ev[0][0]}: …{ev[0][1][:90]}…" if ev else ""))
    for f in sg["flags"]: out.append(f"  ⚠ {f}")
    return "\n".join(out)
