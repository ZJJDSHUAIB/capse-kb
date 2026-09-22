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


def 期望自查(con, cases):
    """★ 期望里写的数字,库里真的找得到吗?

    ═══ 为什么必须做 ═══
        那 60 题有一套核对机制:张君杰写标准答案 + 脚本拿他的出处去库里取值逐字比。
        ★ 而这 19 道的期望【是我手写的】,没人核过 ——
          如果我把某个数写错了,那一道就永远判不对,而且【看不出来】。
        ★★ 那正是这个项目的主题:题目错了,整把尺子就废了 —— 而且是静默地废。

    ═══ 判据 ═══
        期望里每条"必须含"里的片段,如果是【数字形态】,就去库里找一遍:
          在所有表的所有文本/数值列里,有没有出现过这个串。
        ★ 找不到 → 报出来。**不自动改** —— 因为"库里没有"也可能是
          "这个数本该由系统算出来"(比如两个数之差),那要人看。
    """
    import re
    数字形 = re.compile(r'^[\d,\.]+$')
    库里 = set()
    for (t,) in con.execute("SELECT name FROM sqlite_master WHERE type='table'"):
        try:
            cols = [r[1] for r in con.execute(f"PRAGMA table_info({t})")]
            for row in con.execute(f"SELECT * FROM {t}"):
                for v in row:
                    if v is None:
                        continue
                    s = str(v)
                    库里.add(s)
                    #  ★ 表里是 889332 这种裸数,而期望里可能写成 889,332
                    if s.replace(".", "").isdigit():
                        库里.add(f"{int(float(s)):,}" if "." not in s else s)
        except Exception:
            continue
    报 = []
    for c in cases:
        for i, e in enumerate(c["期望"], 1):
            for x in e.get("必须含", []):
                if not 数字形.match(str(x)):
                    continue
                #  ★ 去掉千分位再找一遍 —— 两种写法都算
                变体 = {str(x), str(x).replace(",", "")}
                if not (变体 & 库里):
                    报.append((c["编号"], i, x))
    return 报


def 判一条(期望, 实际文本):
    """一条期望,过不过?返回 (过没过, 为什么)。

    ★ 两把尺子,分工不同:
        字面的 —— 必须含 / 必须不含。数字和名字用这个,因为那些是硬事实。
        语义的 —— 语义要点。★ 由大模型判"它有没有说出那个意思"。

    ═══ ★★★ 为什么必须有那把语义的 ═══
        张君杰一句话点破的:「只要是相同的意思就可以啊」
        ★ "说不成立"这一类,系统可以有很多种说法:
            两期一模一样 / 持平 / 没有变化 / 没降 / 走着平 / …
        ★★ 枚举说法是【枚举不完的】—— 和"补语言现象"是同一个病。
        ★★★ 而这一路我早该想到:那 60 题就是用大模型判分来补字面尺子的短板。
           我自己重新踩了一遍。
    """
    缺 = [x for x in 期望.get("必须含", []) if x not in 实际文本]
    禁 = [x for x in 期望.get("必须不含", []) if x in 实际文本]
    if 缺:
        return False, f"缺了 {缺}"
    if 禁:
        return False, f"出现了不该有的 {禁}"
    要点 = 期望.get("语义要点")
    if 要点:
        过, 为什么 = 语义判(要点, 实际文本)
        if not 过:
            return False, f"语义上不满足「{要点}」—— {为什么}"
    return True, ""


def 语义判(要点, 实际文本):
    """问大模型:这段回答有没有表达出「要点」这个意思?

    ★ 判据是【意思】,不是【说法】—— 所以只能交给大模型。
    ⚠ 而它可能判错,所以措辞要【严】:
      宁可说"没说出来",也不要说"差不多"。
      ★ 因为它在这种地方判松了,就等于【尺子放过了错的】——
        而那正是这一课开头 G02 那道题的老毛病。
    """
    from llm import chat
    prompt = f"""判断下面这段回答,有没有表达出这个意思:

要表达的意思:{要点}

回答的内容:
{实际文本[:1500]}

★ 只回答一个字:有 / 没有
  · 「有」= 它【明确说出了】那个意思
  · 「没有」= 它没说,或者说的是别的意思(包括【意思相反】)
⚠ 不要说"差不多"、"部分表达"—— 那些都算【没有】。"""
    try:
        答 = chat(prompt, max_tokens=5).strip()
    except Exception as e:
        return False, f"语义判据没跑成({type(e).__name__})"
    return ("有" in 答), f"大模型判「{答}」"


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
