# -*- coding: utf-8 -*-
r"""
第 9 课 · 第二节 · 合并方式的【对照线】—— 这些是"事实",不是判断。

═══ 为什么要有这个文件 ═══
    三条对照线各有【唯一的、写死的】定义,不需要任何人做判断:
        只关键词   —— 系统现在的样子(基准)
        并集填位   —— 关键词优先,没占满的位置用向量按名次补上
        交集       —— 两条路都点名的才要
    它们放这里,是为了让 `my_merge.py`(张君杰的判断)有个【比的对象】。

    ★ 一条判断如果没有对照,就不知道它值多少。

═══ ★ 为什么"并集填位"是主角,不是"并集" ═══
    量出来的:14 道检索题、k=5,关键词给出的结果【空着 40% 的位置】
    (9 道题关键词只给 2 条,#51 只给 1 条)。

    所以最朴素的"并集"在这里 = **把空位填上,不挤掉任何东西** —— 那是免费的。
    只有 5 道题关键词占满了,才需要"挤掉谁" —— 那才是判断。

    ⚠ 所以这三个【不是平等三选一】:
        交集     在 14 道上 = 只用关键词 → 纯粹丢东西(反面教材)
        并集填位 ★ 主角
        按名次   只服务"占满了"的那 5 道

═══ ⚠ 这个文件【不装】张君杰的合并规则 ═══
    他的规则在 my_merge.py。这里只放"不需要判断"的对照线。
"""


def only_keyword(kw_ranked, vec_ranked, k=5):
    """基准 = 系统现在的样子。不合并,直接用关键词排名。"""
    return list(kw_ranked[:k])


def union_fill(kw_ranked, vec_ranked, k=5):
    """并集填位:关键词优先,空位用向量按名次补。

    ★ 关键性质:**它永远不会挤掉关键词的任何一条。**
      所以凡是关键词已经命中的题,这条线不可能让它们变坏 ——
      它只能"在空位上多给点什么"。
      (除非多给的那个东西是噪音 —— 而那要跑了才知道。)
    """
    out = list(kw_ranked[:k])
    for cid in vec_ranked:
        if len(out) >= k:
            break
        if cid not in out:
            out.append(cid)
    return out


def intersect(kw_ranked, vec_ranked, k=5):
    """交集:两条路都点名的才要。

    ★ 反面教材。这一条存在的意义只有一个:
      量出"丢掉关键词没占满的那些位置"值多少。
      预期它会和"只用关键词"一模一样或更差 —— 但那也要量,不许推。
    """
    vs = set(vec_ranked)
    return [cid for cid in kw_ranked if cid in vs][:k]


def union_topk(kw_ranked, vec_ranked, k=5):
    """两条路【各取前 k 条】,合起来去重 —— 结果最多 2k 条。

    ⚠ 我的第一版写的是"关键词全部 + 向量全部",那是【错的】:
      **向量对库里每一块都有意见(vec_ranked 装的是全部 54 块)**
      —— 所以"向量全部" = 整个库,那个"并集"等于把库全倒给大模型,没有意义。

    ★★ 这件事本身就值一课:
      因为向量【谁都能排个名】,所以"并集"在向量这条路上【必须有人为的截断】——
      而"截到第几"就是个判断。**"纯并集"不是一个自然存在的东西。**

    ★ 它代表"多拿"的路线:位置从 5 个变成最多 10 个。
      代价第 7 课量过(那次是 K 从 3 加到 5):
      **多拿的每一条既可能是答案,也可能是噪音 —— 而噪音不是"没用",是"有害"。**
    """
    out = list(kw_ranked[:k])
    for cid in vec_ranked[:k]:
        if cid not in out:
            out.append(cid)
    return out


# 名字 → 函数。给量具和 score_eval 用。
VARIANTS = {
    "只关键词": only_keyword,
    "并集填位": union_fill,
    "交集":     intersect,
    "并集取前k": union_topk,
}


def by_name(name):
    if name in VARIANTS:
        return VARIANTS[name]
    if name in ("你的", "mine"):
        from my_merge import merge_rank
        return merge_rank
    raise KeyError(f"没有这个合并方式:{name}(可选: {list(VARIANTS)} + 你的/mine)")
