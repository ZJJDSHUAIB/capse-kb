# -*- coding: utf-8 -*-
r"""
Agent 那一层的跑分 —— 拿多轮对话去问 agent.py,看它接不接得住。

═══ 它和 score_eval.py 的分工 ═══
    score_eval.py   核【老路】:一句一答(词表路由 + 材料拼接/生成)
    agent_eval.py   核【Agent 那一层】:多轮、记忆、指代、工具选择
    ★ 两件事。老路 60/60 的成绩,【说明不了】这一层行不行。

═══ 判分口径(★ 三种,必须都算)═══
      答       —— 答案里【必须含】那几个片段
      反问     —— 该反问而不是猜
      说不成立 —— 用户的前提和数据对不上,系统该说出来

    ⚠ 为什么三种都要:只算"答对"的话,
      一个【什么都不敢答、全反问】的系统也能拿高分。

═══ ★★ 一条口径上的诚实(必须写清)═══
    "必须含"用的是【字面包含】—— 它是个粗尺子:
      · 系统答对了但换了说法 → 可能被判错(假错)
      · 系统把该含的都抄了一遍但答非所问 → 可能被判对(假对)
    ★ 所以这一层的分数【只能当"有没有明显的错"看】,不能当精确准确率。
    ★★ 这和那 60 题的处境一样 —— 而且那 60 题用了大模型判分来补这一层。
      这里【先不做大模型判分】:先看字面尺子能浮出什么,再决定要不要加。
"""
import sys, io, json, sqlite3, argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from paths import DB, DOCS

#  题集在 docs/ 下 —— 它是【真相源】,不该放在 tools/ 里和工具混着
sys.path.insert(0, str(DOCS))
from agent_评估集 import CASES, check as 题集自检    # noqa: E402


def 判一条(期望, 实际文本):
    """一条期望,过不过?返回 (过没过, 为什么)。

    ★ 三种类型用的其实是【同一把尺子】:必须含 / 必须不含 / 必须含任一。
      类型只是【告诉你这一条在考什么】—— 判起来没有区别。
      ★★ 那是有意的:口径越少越好解释。
    """
    缺 = [x for x in 期望.get("必须含", []) if x not in 实际文本]
    禁 = [x for x in 期望.get("必须不含", []) if x in 实际文本]
    任一 = 期望.get("必须含任一")
    if 缺:
        return False, f"缺了 {缺}"
    if 禁:
        return False, f"出现了不该有的 {禁}"
    if 任一 and not any(x in 实际文本 for x in 任一):
        return False, f"没有说出「{任一[0]}」这类意思(试了 {len(任一)} 种说法)"
    return True, ""


def 跑一道(智能体类, con, case):
    """跑一道题(整段对话),返回 (逐步结果, 该题的结论)。"""
    a = 智能体类(con)
    逐步 = []
    for i, (句, 期望) in enumerate(zip(case["对话"], case["期望"]), 1):
        r = a.问(句)
        if r["结局"] == "反问":
            文本 = r["反问"]
            实际类型 = "反问"
        else:
            #  ★ 把这一轮【所有工具的输出】拼起来当"实际答案"
            #    —— 因为不同的问法会走查表或查原文,而期望只关心"说没说出那些内容"
            片 = []
            for _, v in r["结果"].items():
                vv = v["值"]
                if vv is None:
                    continue
                if not isinstance(vv, list):
                    vv = [vv]
                for x in vv:
                    #  ★ 查原文现在交的是 [{"chunk_id":..., "文本":...}] ——
                    #    取"文本";而 str(整个字典) 会把引号转义,判据会判不准。
                    if isinstance(x, dict):
                        片.append(str(x.get("文本") or x.get("chunk_id") or x))
                    else:
                        片.append(str(x))
            #  ★ 记忆补过什么、有没有说不成立,也都要算进去 ——
            #    否则"说了不成立"那一条会因为它在说明里而判不出
            片 += r.get("说明", [])
            文本 = "\n".join(片)
            实际类型 = "答" if not any(
                x in 文本 for x in ("对不上", "不成立", "没有下降", "一模一样")) else "说不成立"
        过, 为什么 = 判一条(期望, 文本)
        逐步.append({"句": 句, "期望类型": 期望["类型"], "实际类型": 实际类型,
                     "过": 过, "为什么": 为什么, "答": 文本[:200]})
    return 逐步, all(x["过"] for x in 逐步)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="", help="这一轮的名字,结果另存")
    ap.add_argument("--only", default="", help="只跑编号以它开头的")
    args = ap.parse_args()

    errs = 题集自检()
    if errs:
        print("✗ 题集自己有问题 —— 先修它,否则跑出来的分没意义:")
        for e in errs:
            print(f"    · {e}")
        return

    from agent import 智能体
    con = sqlite3.connect(DB)

    用例 = [c for c in CASES if c["编号"].startswith(args.only)] if args.only else CASES
    print("=" * 78)
    print(f"  Agent 那一层跑分 —— {len(用例)} 道")
    print("=" * 78)

    结果 = []
    for case in 用例:
        逐步, 全过 = 跑一道(智能体, con, case)
        结果.append({"编号": case["编号"], "考什么": case["考什么"],
                     "全过": 全过, "逐步": 逐步})
        print(f"\n  {'✅' if 全过 else '❌'} {case['编号']}  {case['考什么']}")
        for i, s in enumerate(逐步, 1):
            print(f"      第{i}句:{s['句']}")
            print(f"         期望 {s['期望类型']} / 实际 {s['实际类型']} "
                  f"→ {'过' if s['过'] else '✗ ' + s['为什么']}")
            if not s["过"]:
                print(f"         它答的是:{s['答'][:120]}")

    #  ── 汇总 ──
    n = len(结果)
    ok = sum(r["全过"] for r in 结果)
    from collections import Counter
    按类型 = Counter()
    for case, r in zip(用例, 结果):
        for s in r["逐步"]:
            按类型[s["期望类型"]] += 1
            按类型[s["期望类型"] + "·过"] += s["过"]

    print("\n" + "=" * 78)
    print(f"  整题全对  {ok}/{n}")
    print("  按【期望类型】分开看(★ 这是这份评估最要紧的一栏):")
    for t in ("答", "反问", "说不成立"):
        tot = 按类型[t]
        if tot == 0:
            continue
        print(f"     {t:<6} {按类型[t + '·过']}/{tot}")

    #  ══ ★★ 那一栏为什么最要紧 ══
    print("""
  ★ 为什么要按类型分开看:
      只看总分的话,一个【从不反问、从不说"不成立"】的系统
      照样能把"答"那一类拿满 —— 而它其实是个【什么都不敢负责】的系统。
      分开看,那一类的短板才浮得出来。

  ⚠ 尺子是字面的(必须含那几个片段)—— 它只能照出"有没有明显的错",
    不能当精确准确率。换种说法的正确答案会被它判错。
""")

    if args.tag:
        out = DOCS / f"agent跑分_{args.tag}.json"
        out.write_text(json.dumps(结果, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"  结果写到 {out.name}")


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    main()
