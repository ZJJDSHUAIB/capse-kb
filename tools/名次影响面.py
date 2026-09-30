# -*- coding: utf-8 -*-
"""名次影响面 —— 把「名次换成【并列同名次】(RANK)」这件事的影响面【查出来】。

═══ 为什么要有这一个 ═══
    张君杰问了一句:
      「如果我选了并列 这个问题是解决了 但是对其他的问题呢?
        会不会有影响某一类题呢?答案是肯定的吧 那该怎么办呢?」
    ★ 他说得对 —— 而【影响哪几类】这件事不该推着说,该【查出来】。
    ★★ 判据这个项目里早就有:「那个数要是查出来的,不是估的。」

═══ 它怎么查 —— ★ 一次模型调用都不花 ═══
    · 已存下来的答案里,每个「排名第 N」都是【从库里读的】
    · 而 RANK() 能在库里【当场算出来】
    → 两边一比,就知道哪几道题的答案会变、变成什么。
    ★ 这两件事都是【能算的】—— 能算的地方,别问大模型(也不用重跑评估)。

═══ 它认三种地方的名次 ═══
    ① `{期次} {机场}:综合得分 {分},排名第 {N}/{总}`   —— 单机场排名
    ② `{期次} 前 {k} 名:第1名 A 4.28;第2名 B 4.27;…`  —— 排名列表
    ③ 它自己产出的比较结论行里的「第N名」             —— (只统计,不改)
"""
import io
import json
import re
import sqlite3
import sys
from pathlib import Path

DOCS = Path(__file__).resolve().parent.parent / "docs"

单机场行 = re.compile(
    r'(\d{4}Q\d)\s+(\S+?):\s*[^\s:]+\s+(-?\d+(?:\.\d+)?)'
    r'\s*,\s*排名第\s*(\d+)\s*/\s*(\d+)')
前N名行 = re.compile(r'(\d{4}Q\d)\s+前\s*\d+\s*名:(.*)')
列表项 = re.compile(r'第\s*(\d+)\s*名\s+(\S+?)\s+(-?\d+(?:\.\d+)?)')


def 装名次表(con):
    """(期次, 机场) → (现在ROW_NUMBER的名次, 换成RANK之后的名次, 同分几家)。

    ★ 一次全算出来,不逐条查库 —— 免得"同一件事查两遍,迟早不一致"。
    ⚠⚠ "同分几家"这一栏是【补的】—— 见 查一遍() 的 docstring:
       第一版只比"打印出来的数字变不变",于是漏掉了题21 那种。
    """
    t = {}
    同分 = {(期, 得): n for 期, 得, n in con.execute(
        "SELECT 期次, 得分, COUNT(*) FROM 综合得分 GROUP BY 期次, 得分")}
    分 = {(期, 场): s for 期, 场, s in con.execute(
        "SELECT 期次, 机场, 得分 FROM 综合得分")}
    for 期, 场, w, r in con.execute("""
            SELECT 期次, 机场,
                   ROW_NUMBER() OVER (PARTITION BY 期次 ORDER BY 得分 DESC),
                   RANK()       OVER (PARTITION BY 期次 ORDER BY 得分 DESC)
            FROM 综合得分"""):
        t[(期, 场)] = (int(w), int(r), 同分.get((期, 分[(期, 场)]), 1))
    return t


def 查一遍(答案, 表):
    """这份答案里,哪些名次会变。→ (数字会变, 意思会变)

    ═══ ⚠⚠⚠ 2026-10-01:第一版【报少了】—— 它是被题21 照出来的 ═══
        【症状】题21「2025Q2无锡硕放国际机场综合得分排名第几」
               期望:并列第16/42（4.15）   而工具判它【不变】。
        ★ 查了库:2025Q2 得 4.15 的【有两家】(无锡硕放 / 福州长乐) ——
          期望是对的,两家真的并列第16。
        ★★ 而它们现在的序号【本来就是 16 和 17】:
           无锡硕放 序号=16,RANK 也=16 → **数字没变**。
        ★★★ 于是工具说"没事"—— 而它答的是「排名第 16/42」,
           既没说"并列",也没提福州长乐。**答案照样是缺的。**
        【根因】第一版只比【打印出来那个数字变不变】。
           而"这个名次处在并列里"是【另一件事】——
           并列里的第一家,数字不变而答案缺了"并列"两个字。
        【★ 修法】两个都报:
             数字会变 —— 换了 RANK 之后打印出来的数会不一样
             意思会变 —— 数字不变,但它处在并列里,而答案没提这件事
           ⚠ 第二个才是【真正的影响面】:它说的是"这道题现在答得不对"。
    """
    数字变, 意思变 = [], []
    文 = str(答案 or "")

    def 看(期, 场, 现):
        换, 家数 = None, 1
        if (期, 场) in 表:
            _, 换, 家数 = 表[(期, 场)]
        if 换 is not None and 换 != 现:
            数字变.append((期, 场, 现, 换))
        elif 家数 > 1:
            意思变.append((期, 场, 现, 家数))

    for m in 单机场行.finditer(文):
        看(m.group(1), m.group(2), int(m.group(4)))
    for m in 前N名行.finditer(文):
        期 = m.group(1)
        for 名, 场, _分 in 列表项.findall(m.group(2)):
            看(期, 场, int(名))
    return 数字变, 意思变


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--跑分", default="评估集_跑分_比结论_ask3.json",
                    help="拿哪一份已存下来的答案来量")
    args = ap.parse_args()

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from check_eval import read_rows, EVAL_IN
    from paths import DB

    con = sqlite3.connect(DB)
    表 = 装名次表(con)
    rows = [r for r in read_rows(EVAL_IN) if r["问题"]]
    得 = json.load(open(DOCS / args.跑分, encoding="utf-8"))

    print("=" * 78)
    print(f"  「名次换成【并列同名次】」的影响面 —— 拿 {args.跑分} 量")
    print("=" * 78)

    行行 = []
    for r, a in zip(rows, 得):
        数, 意 = 查一遍(a.get("系统答"), 表)
        行行.append((r, a, 数, 意))
    会变 = [x for x in 行行 if x[2] or x[3]]
    不会变 = [x for x in 行行 if not (x[2] or x[3])]
    只数变 = [x for x in 行行 if x[2]]
    只意变 = [x for x in 行行 if x[3] and not x[2]]

    print(f"\n  问 {len(rows)} 道:")
    print(f"    ★  打印出来的名次【会变】                  {len(只数变):>2} 道"
          f"  (换 RANK 之后那个数字不一样了)")
    print(f"    ★★ 数字不变,但它处在【并列】里,"
          f"而答案没提这件事  {len(只意变):>2} 道")
    print(f"    合计受影响 {len(会变)} 道,不受影响 {len(不会变)} 道")
    print(f"  (★ 这些数是【查出来的】—— 每个「排名第 N」都对着库比过一遍)")
    print( "  ⚠ 第二行才是【真正的坏消息】:它说的是'这道题现在答得不对',"
           "而分数上看不出来")

    #  ★ 按类别分 —— 他问的就是"会不会影响某一类题"
    按类 = {}
    for r, _a, _数, _意 in 会变:
        按类.setdefault(r["类别"], []).append(r)
    总数按类 = {}
    for r in rows:
        总数按类[r["类别"]] = 总数按类.get(r["类别"], 0) + 1

    print("\n  ★ 会变的题按【类别】分:")
    for 类 in sorted(总数按类, key=lambda c: -len(按类.get(c, []))):
        n = len(按类.get(类, []))
        print(f"    {类:<12} {n:>2}/{总数按类[类]:<2} "
              + ("█" * n if n else ""))

    #  ★ 期望答案里含「并列」的那几道 —— 它们该是"变对了的那一类"
    有并列期望 = {str(r["题号"]) for r in rows if "并列" in str(r.get("期望答案"))}
    print(f"\n  ★★ 期望答案里含【并列】的 {len(有并列期望)} 道,"
          f"而它们现在答的是什么:")
    for r, a, 数, 意 in 行行:
        if str(r["题号"]) in 有并列期望:
            _标 = "数字变" if 数 else ("缺'并列'" if 意 else "不受影响 ★")
            print(f"    题{r['题号']:>2} [{_标}] {str(r['问题'])[:34]}")
            print(f"           期望:{str(r.get('期望答案'))[:44]}")
            for l in str(a.get("系统答")).split("\n"):
                if "排名第" in l or "→" in l:
                    print(f"           现在:{l.strip()[:74]}")
            for 期, 场, 现, 换 in 数:
                print(f"           ★ 换后:{期} {场} 第{现} → 第{换}")
            for 期, 场, 现, n in 意:
                print(f"           ★ 它处在并列里({期} {场} 第{现},同分 {n} 家)")

    #  ★ 再按【变化的形状】分一次 —— 那才是"哪一类题"的真答案
    print(f"\n  ★★★ 变化的形状(同一个名次变化影响的问法):")
    形状 = {"问某机场排第几(单个)": 0, "问前几名(列表里)": 0}
    for r, _a, _数, _意 in 会变:
        文 = str(_a.get("系统答"))
        形状["问前几名(列表里)"] += len(前N名行.findall(文))
        形状["问某机场排第几(单个)"] += len(单机场行.findall(文))
    for k, v in 形状.items():
        print(f"    {k:<22} {v} 处")

    if 不会变:
        print(f"\n  ★ 不受影响的 {len(不会变)} 道 —— 头几道:")
        for r, _a, _n, _y in 不会变[:5]:
            print(f"    题{r['题号']:>2} {str(r['问题'])[:44]}")
    return 0


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.exit(main())
