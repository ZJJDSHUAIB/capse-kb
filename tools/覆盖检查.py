# -*- coding: utf-8 -*-
r"""
「一句话里说的几件事，答案覆盖了几件?」—— 第 21 课。

═══ 为什么要有它（实测，不是设想）═══
    ★ 主链在这两道上的表现（`tools/条件题测试.py` 量出来的）:

        「浦东2025Q4表现怎么样，要是不好就说说是哪一项拖后腿」
          → 答了综合得分。而"哪一项拖后腿"【没答】—— 也没说为什么没答。
        「浦东2025Q4排第几，前三名是谁」
          → 答了排名。而"前三名"【没答】—— 也没说为什么没答。

      ★★ 同一个形状:一句话里有两件事，它只做了一件，而【不说】。
      ★★★ 而这和早上修的那个是近亲:
          「浦东近两期…同档平均」→ 2025Q3 没数据 → 整句崩
          修完是"说清哪一期没有，其余照常给你"。
          → 这一次该是"做了一件，另一件为什么没做，说出来"。

═══ ⚠⚠ 判据为什么不在本地算 —— 两条路都量过，都不行 ═══
    ① 标点分段（`，`/`；`/`以及`/`顺便`）
       ★ ①「分析…如果降了…没降…」分【3 段】，而它其实【一件事】（条件）
       ★ ③「浦东和虹桥谁高，低的那家差在哪」分 2 段，而它其实【一件事】（对比）
       → 段数和"几件事"根本不成比例。★ 误导。

    ② 命中几个【量名】（route.量名 的子串）
       ★ 用户说的是口语:「表现怎么样」「哪一项拖后腿」「前三名」
         这些【不含任何库里的量名】→ 算出来 0 个。
       → 也分不开。

    ★★★ 所以这一段【算不出来，要问】——
       但问的方式要【能验】:切段（能算）+ 每段问模型"这段的意思答案里有吗"。

═══ 怎么用 ═══
    python tools/覆盖检查.py            # 拿内置那五道跑一遍
    python tools/覆盖检查.py "问句"      # 单句，答案从主链拿
"""
import sys, io, re, sqlite3, argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from paths import DB

分隔 = re.compile(r'[，,。；;]|以及|顺便|还有')

#  ★ 一句话一次问完 —— 不逐段问（省调用，而且它看得见整句，判得更准）
提示词 = """下面是一个用户的问题，被拆成了几段。
还有一个系统给出的答案。

【用户的问题，拆成几段】
{段}

【系统给的答案】
{答}

★ 请逐段判断:这一段【问的意思】，答案里【有没有】?

只输出 JSON，形如:
{{"覆盖": [true, false, ...]}}   ← 长度必须和段数一样

⚠ 三条:
  · 判的是【这一段问的意思】有没有被答到，不是"字面出现了没有"。
    ★ 比如答案给了"前三名 大兴/虹桥/浦东"，那"前三名是谁"就算【覆盖了】。
  · 那一段如果本来就不是一个问题（比如"分析浦东近两期"只是铺垫），判 true。
  · 拿不准就判 false —— ★ 说"没覆盖"顶多多问一句，说"覆盖了"而其实没有才是坏事。"""


def 切段(q):
    return [x.strip() for x in 分隔.split(q) if x.strip()]


def 查覆盖(问句, 答案):
    """返回 (每段, 每段覆盖没)。★ 答案给空 → 全判没覆盖。"""
    from llm import chat
    import json
    段 = 切段(问句)
    if not 段:
        return [], []
    if not (答案 or "").strip():
        return 段, [False] * len(段)
    清单 = "\n".join(f"  {i}. {s}" for i, s in enumerate(段, 1))
    try:
        原始 = chat(提示词.format(段=清单, 答=str(答案)[:1200]), max_tokens=120).strip()
    except Exception as e:
        return 段, [None] * len(段)          # ★ 判不了就报"判不了",不猜
    m = re.search(r'\{.*\}', 原始, re.S)
    if not m:
        return 段, [None] * len(段)
    try:
        覆盖 = json.loads(m.group(0)).get("覆盖") or []
    except Exception:
        return 段, [None] * len(段)
    覆盖 = (list(覆盖) + [None] * len(段))[:len(段)]
    return 段, 覆盖


def 答了啥(r):
    片 = []
    for _, v in (r.get("结果") or {}).items():
        vv = v.get("值")
        if not vv:
            continue
        for x in (vv if isinstance(vv, list) else [vv]):
            片.append(str(x))
    return "\n".join(片)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("问句", nargs="*")
    a = ap.parse_args()
    con = sqlite3.connect(DB)
    from agent import 智能体
    from 条件题测试 import 题目

    跑 = [(q, None) for q in a.问句] or [(q, 标) for 标, q, _, _ in 题目]

    print("=" * 82)
    print("  覆盖检查:一句话里说的几件事，答案覆盖了几件?")
    print("=" * 82)
    静 = 总 = 0
    for q, 标 in 跑:
        bot = 智能体(sqlite3.connect(DB))
        r = bot.问(q)
        答 = 答了啥(r) if r.get("结局") == "答" else str(r.get("反问") or "（没答）")
        段, 覆盖 = 查覆盖(q, 答)
        print(f"\n{('【' + 标 + '】') if 标 else ''}{q}")
        print(f"  结局={r.get('结局')}")
        漏 = []
        for s, c in zip(段, 覆盖):
            标2 = {True: "✅ 覆盖", False: "★ 漏了", None: "· 判不了"}[c]
            print(f"    {标2}  段:{s[:60]}")
            if c is False:
                漏.append(s)
        总 += 1
        if 漏:
            静 += 1
            print("    ★★ 而【主链的答案里没有说「这一段没答」】—— 这就是静默")
    print("\n" + "=" * 82)
    print(f"  有漏段的题:{静}/{总}")
    print("=" * 82)
    print("""
  ★ 这一把尺子量的是【它有没有把话说完】——
     ⚠ 而"漏了"本身【不是】最要命的;最要命的是【漏了而用户看不出来】。
     ★★ 所以修法的目标不是"一件都不漏"，是【漏的那件要说出来】。
        ★ 那和这个项目一路的判据一致:判不出看得见。""")


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    main()
