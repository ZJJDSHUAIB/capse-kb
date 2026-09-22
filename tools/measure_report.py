# -*- coding: utf-8 -*-
r"""
第 8 课 · 量「报告每一节,系统能负责到什么程度」。

═══ 为什么先量这个,而不是先写报告生成器 ═══
    一份报告会放大两件事,方向不同:
        放大【错误的绝对数量】  30 个数字 × 8% 错 → 大概 2~3 个错
        放大【错误的影响力】    问答里用户会追问;报告里数字直接变成结论

    所以"能不能做报告"的门槛不是 91.7%,是:
        **一份报告里,有多少数字是【错的、而且没标出来的】。**

    要回答它,先得量:报告每一节的数据,系统【能不能保证】。

═══ 量什么 ═══
    每道题记四样:
        去向              系统知不知道该去哪查
        拿到没有          答案是不是空的
        来源到哪          能回 PDF 页码 / 只到表名
        报警没有          out["警告"] 非空

    ★ 「来源到哪」这一栏是新的 —— 第 5 课就发现 SQL 那条路回不到页码,
      但它一直没被当成指标。**报告里用户要核数字,这一栏就是能不能核。**
"""
import sys, io, re, json, sqlite3
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

DB = Path(r"D:\capse-kb\data\processed\capse.db")

# 用户给的 5 节 → 拆成系统能回答的问题
SECTIONS = [
    ("1 总体表现", [
        "2025Q4上海浦东国际机场综合得分是多少",
        "2025Q4上海浦东国际机场综合得分排名第几",
    ]),
    ("2 核心指标", [
        "2025Q4上海浦东国际机场在7个一级指标里,哪项最高",
    ]),
    ("3 变化与对比", [
        "2025Q4和2025Q3的上海浦东国际机场哪个综合得分高",
        "2025Q4上海浦东国际机场的机场安检得分是多少",
    ]),
    ("4 问题与亮点", [
        "哪个机场2025Q4航班不正常保障最差",
    ]),
    ("5 结论与建议", [
        "为什么上海浦东国际机场2025Q4的表现是这样",
    ]),
]


def main():
    from ask import ask
    from route import load_airports, load_indicators
    con = sqlite3.connect(DB)
    ap, ind = load_airports(con), load_indicators(con)

    rows = []
    for sec, qs in SECTIONS:
        print("=" * 80)
        print(f"  {sec}")
        print("=" * 80)
        for q in qs:
            a = ask(con, q, ap, ind)
            ans = a.get("答案") or []
            src = a.get("来源") or []
            has = bool(ans)
            # 来源落到哪一层
            #  ★ 判据改过一次:原来用「来源里有没有 capse.db」判"只到表名" ——
            #    但回填之后,来源【两样都有】(表名 + → 原文 2025Q4-P09),
            #    那个判据就永远判成"核不了"。**判据过时了。**
            #    现在改成看:有没有 chunk_id 格式的原文引用。
            if not src:
                lvl = "无来源"
            elif any(re.search(r'\d{4}Q\d-P\d+', x) for x in src):
                lvl = "到 PDF 页码(能核)"
            else:
                lvl = "只到表名(核不了原文)"
            w = a.get("警告") or []
            rows.append({"节": sec, "问": q, "去向": a["去向"],
                         "拿到": has, "来源层级": lvl, "报警": bool(w)})
            print(f"\n  问:{q}")
            print(f"     去向={a['去向']}  来源={lvl}  报警={'★有' if w else '无'}")
            for l in ans[:2]:
                print(f"     {l[:74]}")
            if w:
                print(f"     ★ {w[0][:66]}")

    print("\n" + "=" * 80)
    print("  逐节汇总 —— **这一节的数据,系统能不能负责?**")
    print("=" * 80)
    print(f"  {'节':<12} {'题数':>4} {'拿到':>5} {'能核原文':>9} {'报警':>5}   判断")
    print("  " + "-" * 66)
    for sec, _ in SECTIONS:
        rs = [r for r in rows if r["节"] == sec]
        n = len(rs)
        got = sum(r["拿到"] for r in rs)
        page = sum("PDF" in r["来源层级"] for r in rs)
        warn = sum(r["报警"] for r in rs)
        if got == 0:
            verdict = "★ 系统答不了"
        elif page == 0 and got:
            verdict = "⚠ 答得出,但【核不了原文】"
        elif warn:
            verdict = "⚠ 答得出,但有报警"
        else:
            verdict = "✅ 能负责"
        print(f"  {sec:<12} {n:>4} {got:>5} {page:>9} {warn:>5}   {verdict}")

    print("""
  ★ 判断标准(我定的,你可以改):
       ✅ 能负责      拿到了、来源能回原文、没报警
       ⚠ 答得出但要标  拿到了,但【核不了原文】或者系统自己报警了
       ★ 答不了        系统给不出

  ⚠ 注意第三栏【能核原文】:SQL 那条路的来源只到表名。
     报告里的数字如果核不了原文,用户凭什么信?  —— 这一栏比"答对没答对"更要紧。
""")


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    main()
