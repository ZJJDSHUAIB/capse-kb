# -*- coding: utf-8 -*-
r"""
第 10 课 · 给几页材料,大模型才答得对?

═══ 为什么做这个 ═══
    第 10 课发现:给 5 页材料,大模型有时会漏(题 45 说"材料里没有")。
    → 那少给几页,会不会更好?

    ★ 这就是那份外部建议里【Context Builder】那一格要做的事。
      但它没写怎么做。这里先试最简单的一刀:少给几页。

═══ ★★★ 三条规矩(全是第 10 课学的,不守这三条,结果不能看) ═══

    ① 【跑多次,不看单次】
       大模型的输出是概率。跑一次得的分数不作数。

    ② 【比的是概率,而且要看区间】
       10 次里对 8 次 ≠ "80%"。它的误差很宽。
       → 所以下面直接算区间,并标注【两档的区间有没有重叠】。
       ★ 重叠 = 没量出差别 = 结论是"分不清",那也是一个结论。

    ③ 【写清条件】
       任何结论只能这么说:
           "在【这 5 道题 + 这 54 页报告 + 当前提示词 + 当前模型】上,……"
       ★ 换一批题可能不成立 —— 它是量出来的一个数,不是一条规律。

═══ ⚠ 判对错用的是【代码】,不是大模型 ═══
    "对" = 期望答案里的关键内容出现在回答里(关键词见 KEYS)。
    ★ 好处:硬、可复现、不花钱。
    ★★ 代价:它只判"答没答到点上",判不了"说得对不对"。
      所以下面这个"答对率"是个【粗判】,不是判分口径。
"""
import sys, io, re, time, sqlite3
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

ROOT = Path(r"D:\capse-kb")
DB = ROOT / "data" / "processed" / "capse.db"
OUT = ROOT / "docs" / "第10课_给几页测试.txt"

N_REP = 8                            # 每档跑几次
COUNTS = [1, 2, 3, 5]                # 给几页

#  题号 → (问题, 判对错用的关键词 —— 全部出现才算对)
CASES = {
    45: ("2025Q3的CAPSE简介里，CAPSE创立了哪些指标或系统",
         ["净推荐值", "出行意愿"]),
    46: ("2025Q4分吞吐量级服务测评里，4000万级以上机场综合得分前两名是谁",
         ["北京大兴", "深圳宝安", "4.28", "4.27"]),
    47: ("2025Q4分吞吐量级服务测评里，2500万-4000万级机场综合得分第一是谁",
         ["厦门", "4.25"]),
    50: ("2024Q3报告里“旅客最佳”的定义是什么",
         ["物有所值"]),
    51: ("2024Q2的著作权声明说了什么",
         ["著作权", "航联传播"]),
}


def wilson(k, n):
    """k/n 的 95% 区间(Wilson)。★ 小样本时比 k/n 那个点靠得住得多。

    为什么要它:5 次里对 3 次,不代表"60%" —— 真实值可能在 20%~90% 之间。
    ★★ 不报区间就报点,那是假精确 —— 项目里已经栽过一次(K 曲线那次)。
    """
    if n == 0:
        return 0.0, 0.0
    p = k / n
    z = 1.96
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    m = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5)
    return max(0.0, (c - m) / d), min(1.0, (c + m) / d)


def main():
    from ask import gen_answer
    from build_search import search_merged, search_multi
    import ask as askmod

    con = sqlite3.connect(DB)
    askmod.USE_MERGE = True          # 和正式跑一致

    L = []
    L.append("=" * 92)
    L.append("  第 10 课 · 给几页材料,大模型才答得对?")
    L.append("=" * 92)
    L.append(f"  每档跑 {N_REP} 次;判对错用【代码】核关键词,不调大模型")
    L.append(f"  条件:这 {len(CASES)} 道题 + 当前 54 页库 + 当前提示词 + 当前模型")
    L.append("")

    rows = []
    for no, (q, keys) in CASES.items():
        per = sorted(set(re.findall(r"\d{4}Q\d", q))) or None
        hits = search_merged(con, q, k=5, periods=per)
        ids = [str(h["chunk_id"]) for h in hits]
        L.append(f"  题 {no}  {q[:46]}")
        L.append(f"        检索给的顺序:{ids}")
        line = []
        for n in COUNTS:
            sub = hits[:n]
            if not sub:
                line.append(f"给{n}页: —")
                continue
            ok = 0
            for _ in range(N_REP):
                try:
                    a = gen_answer(q, sub)
                except Exception as e:
                    a = f"(出错 {e})"
                if all(k in a for k in keys):
                    ok += 1
            lo, hi = wilson(ok, N_REP)
            line.append(f"给{n}页 {ok}/{N_REP}")
            rows.append((no, n, ok, N_REP, lo, hi, ids[:n]))
            time.sleep(0.2)
        L.append("        " + "   ".join(line))
        L.append("")

    L.append("=" * 92)
    L.append("  汇总(★ 看【区间】,不是看那个分数)")
    L.append("=" * 92)
    L.append(f"  {'题':>4} {'给几页':>6} {'答对':>7} {'区间(95%)':>18}   给了哪几页")
    for no, n, ok, N, lo, hi, got in rows:
        star = "★" if hi - lo > 0.35 else " "      # 区间太宽 = 这个数不能信
        L.append(f"  {no:>4} {n:>6} {ok:>4}/{N} {f'{lo:.0%} ~ {hi:.0%}':>18}{star}   {got}")

    L.append("")
    L.append("  ★★ 怎么读:")
    L.append("       ① 区间【宽】(带 ★ 的那些)= 这个数不能信,得跑更多次")
    L.append("       ② 两档的区间【重叠】= 没量出差别 = 结论是「分不清」")
    L.append("       ③ 区间不重叠 = 才有资格说「哪个更好」")
    L.append("")
    L.append("  ★★★ 而无论结论是什么,它只能这么说:")
    L.append(f"       「在【这 {len(CASES)} 道题 + 当前库 + 当前提示词 + 当前模型】上,……」")
    L.append("        换一批题可能不成立 —— 这是量出来的一个数,不是一条规律。")

    text = "\n".join(L)
    print(text)
    OUT.write_text(text, encoding="utf-8")
    print(f"\n  ✅ 存到 {OUT}")


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    main()
