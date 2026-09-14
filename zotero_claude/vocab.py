"""分类与标签词表——与 CLAUDE.md §2/§3 一一对应，是代码里唯一的词表来源。改词表：改 CLAUDE.md 的同时改这里。"""
import re

COLLECTIONS = ("Evolution Algorithm", "Dex-Manipulation", "Humanoid", "AI Foundation")   # 只有四个，不新建
EA, DM, HUM, AIF = COLLECTIONS
FAMILIES = ("method", "embod", "tech", "base", "modality")                                  # 提案表里的五个判定列
VOCAB = {
 "method": {"vla", "policy-learning", "rl", "world-model", "foundation-model", "teleop", "grasp-synthesis"},
 "embod": {"dex-hand", "gripper", "single-arm", "bimanual", "humanoid"},
 "tech": {"action-chunking", "flow-matching", "diffusion", "transformer", "hil", "latent-cot"},
 "base": {"pi0", "pi0.5", "pi0.6", "gr00t"},
 "modality": {"vision", "language", "tactile", "depth", "point-cloud", "audio"},
 "type": {"survey", "benchmark", "dataset"},
 "status": {"to-read-first", "to-read", "skimmed", "read", "to-present", "presented", "to-reproduce", "reproducing", "reproduced"},
}
READ_AXIS = ("to-read-first", "to-read", "skimmed", "read")     # 读进度轴：恰好一个，不降级
KEEP_BARE_TAGS = {"notion"}                                     # Notero 插件自动打的裸标签，不算词表外


def check_tags(tags):
    """词表外的值只警告不拦（用户可能已批准新值）。返回警告列表，同时打印。"""
    warns = []
    for t in tags:
        if t in KEEP_BARE_TAGS: continue
        m = re.fullmatch(r"([a-z]+):([a-z0-9.\-]+)", t)
        if not m: warns.append(f"标签 {t!r} 不是 family:value 形式（照写，但请确认）"); continue
        if m.group(1) not in VOCAB: warns.append(f"标签家族 {m.group(1)!r} 不在词表")
        elif m.group(2) not in VOCAB[m.group(1)]: warns.append(f"{t!r} 不在 CLAUDE.md 词表里（用户批准过才用）")
    for w in warns: print("  ⚠ " + w)
    return warns


def sort_tags(tags):
    """按家族顺序排：method embod tech base modality type status，其余最后。"""
    order = {f: i for i, f in enumerate(FAMILIES + ("type", "status"))}
    return sorted(set(tags), key=lambda t: (order.get(t.split(":")[0], 99), t))
