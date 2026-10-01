# -*- coding: utf-8 -*-
"""抖动 —— 同一份代码跑 N 遍,哪几道会变、变在哪一层。

═══ 为什么要有这一个 ═══
    实测:agent 那条路同代码两遍,86 道里有 10 道答案不同。
    ★ 而【分数是稳的】(79/79 · 83/83 · 85/85)。
    → 也就是说:光看分数,这个抖动【看不见】。
    ★★ 而它要紧:意味着【别人跑两次会得到不一样的结果】——
       而那正是这个项目一路在防的东西(静默失败)的一个变种:
       不是"答案错了",是"答案不稳"。

═══ 它量什么 ═══
    每道题、每遍,记三样:
        选中  —— 模型选了哪几个工具
        走法  —— 计划路 / 老路 / 反问 / 拒答
        结果  —— 每个工具那一栏的【值长什么样】(前 N 字)
    ★ 于是能分开两种抖动:
       选中不同   → 【选工具】那一层抖(模型)
       选中相同而值不同 → ★ 【工具内部】抖(还是模型,或是检索)
    ⚠ 只报事实,不下"这算不算错"的结论 —— 那要看内容的意思,不是长度。

═══ ⚠ 它花时间 ═══
    一遍 = 86 次 agent 调用(其中不少还会出计划 → 更多次)。
    ★ 所以默认只跑【每类抽 2 道】,用小样本先看形状。
      要看全量就 --全量。

用法:
    python tools/抖动.py                # 抽样,跑 3 遍
    python tools/抖动.py --遍数 5 --全量
"""
import io
import json
import sqlite3
import sys
from pathlib import Path

DOCS = Path(__file__).resolve().parent.parent / "docs"
sys.path.insert(0, str(Path(__file__).resolve().parent))


def 问一遍(con, q):
    """跑一次,把【可比较的三样】抠出来。"""
    from agent import 智能体
    try:
        记 = 智能体(con).问(q)
    except Exception as e:
        return {"选中": f"崩:{type(e).__name__}", "走法": "崩", "结果": str(e)[:60]}
    结果 = 记.get("结果") or {}
    return {
        "选中": "、".join(str(x) for x in (记.get("选中") or [])),
        "走法": 记.get("走法") or (记.get("结局") or ""),
        "结果": " ∥ ".join(
            f"{k}:{str(v.get('值'))[:56]}"
            for k, v in 结果.items() if isinstance(v, dict)),
    }


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--遍数", type=int, default=3)
    ap.add_argument("--全量", action="store_true", help="跑全部 86 道(很慢)")
    ap.add_argument("--每类", type=int, default=2, help="抽样时每类抽几道")
    args = ap.parse_args()

    from check_eval import read_rows, EVAL_IN
    from paths import DB
    con = sqlite3.connect(DB)
    rows = [r for r in read_rows(EVAL_IN) if r["问题"]]

    if not args.全量:
        按类 = {}
        for r in rows:
            按类.setdefault(str(r["类别"]), []).append(r)
        挑 = [r for v in 按类.values() for r in v[:args.每类]]
        #  ★ 再补上【已知会抖的那几道】—— 让抽样别错过样本
        已知 = {"28", "39", "42", "52", "55", "70"}
        for r in rows:
            if str(r["题号"]) in 已知 and r not in 挑:
                挑.append(r)
    else:
        挑 = rows

    print("=" * 78)
    print(f"  抖动 —— 同一份代码跑 {args.遍数} 遍,{len(挑)} 道题")
    print("=" * 78)
    print(f"  ⚠ temperature 已经是 0 —— 所以这个抖动【不是采样温度造成的】。")

    每道 = []
    for r in 挑:
        遍 = [问一遍(con, r["问题"]) for _ in range(args.遍数)]
        每道.append((r, 遍))
        n = len({json.dumps(x, ensure_ascii=False) for x in 遍})
        print(f"  题{r['题号']:>2} [{r['类别']:<8}] "
              + (f"★ {n} 种答案" if n > 1 else "一致"))

    #  ══ 汇总:分层 ══
    抖的 = [(r, 遍) for r, 遍 in 每道
            if len({json.dumps(x, ensure_ascii=False) for x in 遍}) > 1]
    print(f"\n{'=' * 78}")
    print(f"  汇总:{len(抖的)}/{len(挑)} 道【会变】")
    print("=" * 78)
    if not 抖的:
        print("  ★ 全部一致。")
        return 0
    选层 = 工层 = 0
    for r, 遍 in 抖的:
        if len({x["选中"] for x in 遍}) > 1:
            选层 += 1
        elif len({x["结果"] for x in 遍}) > 1:
            工层 += 1
    print(f"    ★ 差在【选工具】那一层:{选层} 道")
    print(f"    ★ 差在【工具内部】(选中一样):{工层} 道")
    print()
    print("  ⚠ 两种都是【模型】造成的 —— temperature=0 也不够,"
          "那是服务端的非确定性(客户端修不掉)。")
    print("  ★ 所以这里能做的只有:① 量出来 ② 说清楚 ③ 尽量把"
          "【顺序敏感的代码】改掉(那能消掉一部分,不是全部)")

    print(f"\n{'─' * 78}")
    print("  会变的那些,逐道看差在哪:")
    print(f"{'─' * 78}")
    for r, 遍 in 抖的:
        print(f"\n  题{r['题号']} {r['问题'][:44]}")
        for i, x in enumerate(遍, 1):
            print(f"     第{i}遍 选中={x['选中'][:34]}")
            print(f"            结果={x['结果'][:96]}")
    return 0


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.exit(main())
