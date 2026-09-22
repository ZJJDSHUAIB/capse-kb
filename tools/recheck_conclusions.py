# -*- coding: utf-8 -*-
r"""
第 8 课 · 结论的保质期:**把台账里那些结论,拿现在的系统重新量一遍。**

═══ 为什么需要这个 ═══
    张君杰改了一个数字(k=3 → k=5),分数从 95.0% 变成 96.7%。
    顺着查下去发现:**K 的曲线整个翻面了** ——
    旧曲线说"4 以上更差",新曲线说"5 以上更好一点"。

    而他问了一句更狠的:「既然 5 会变好,之前画曲线的时候怎么没注意到?」

    ★ 答案是:**不是没注意到,是当时它真的是差的。** 两次测量都对,变的是系统。
    ★ 而我那句话错在【没写条件】——
        「K>4 更差」听起来像 K 的性质,其实它只在【当时那个系统上】成立:
            当时没有去噪机制 → 多捞 = 多捞噪音 → 更差
            现在有了期次过滤 + 多版本意识 → 多捞 = 多一个机会
      → **准确的说法是「在【当时那个系统】上,K>4 更差」。**

    ⚠ **这个项目改了十几轮。台账里躺着一堆结论,而其中一些是在【当时的系统状态】下量的。**
      不知道哪条已经过期,比不知道分数更危险 —— **因为你会拿它去面试。**

═══ 这个脚本做什么 ═══
    把【台账里记过的那些数】和【现在量出来的数】并排摆出来。
    ★ 它不判断谁对谁错 —— 它只让你看见【哪一栏变了】。
      变了就说明:那条结论的【条件】跟现在不一样了。
"""
import sys, io, re, json, sqlite3
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

DB = Path(r"D:\capse-kb\data\processed\capse.db")
OUT = Path(r"D:\capse-kb\docs\评估集_跑分.json")

#  台账里记过的值(原样抄,不改)
RECORDED = {
    "叙述·检索 平均得分": "0.13",
    "叙述·检索 全对": "2/15",
    "期次污染率": "37%",
    "多捞别期的题数": "7 道(5 道内容一致、2 道说法不同)",
    "K=5 的全对": "32/60(旧曲线)→ 现在?",
}


def main():
    sys.path.insert(0, str(Path(__file__).parent))
    from route import load_airports, load_indicators
    from ask import ask
    from check_eval import read_rows, EVAL_IN

    rows = read_rows(EVAL_IN)
    gots = json.loads(OUT.read_text(encoding="utf-8"))
    con = sqlite3.connect(DB)
    ap, ind = load_airports(con), load_indicators(con)

    #  ── 分数从跑分 JSON 里重建(不重跑,省时间)────────────────
    #  ※ 但它只给"去向",不给"得分" —— 得分在 score_eval 的报告里。
    #    所以这里只量【不依赖判分】的那几件事。
    print("=" * 78)
    print("  台账里的结论  vs  现在量出来的")
    print("=" * 78)

    #  ① 期次污染率
    PER = re.compile(r'(\d{4})\s*[Qq]\s*([1-4])')
    tot_n = tot_pol = 0
    n_with_period = 0
    for r, g in zip(rows, gots):
        if g.get("去向") != "检索":
            continue
        want = {f"{a}Q{b}" for a, b in PER.findall(str(r.get("问题") or ""))}
        if not want:
            continue
        n_with_period += 1
        got = [s.split(" ")[0][:6] for s in (g.get("来源") or [])]
        tot_n += len(got)
        tot_pol += len([x for x in got if x not in want])
    print(f"\n① 期次污染率")
    print(f"     台账记的:  {RECORDED['期次污染率']}")
    print(f"     现在量的:  {tot_pol}/{tot_n} = {tot_pol/tot_n:.0%}"
          f"   (期次敏感题 {n_with_period} 道)")

    #  ② 多捞别期 —— 同上,换个说法看
    multi = []
    for r, g in zip(rows, gots):
        if g.get("去向") != "检索":
            continue
        want = {f"{a}Q{b}" for a, b in PER.findall(str(r.get("问题") or ""))}
        if not want:
            continue
        got = [s.split(" ")[0][:6] for s in (g.get("来源") or [])]
        if any(x not in want for x in got):
            multi.append(r["题号"])
    print(f"\n② 多捞别期的题数")
    print(f"     台账记的:  {RECORDED['多捞别期的题数']}")
    print(f"     现在量的:  {len(multi)} 道  {multi}")

    #  ③ 同一页多版本
    from page_versions import versions
    print(f"\n③ 同一页有几个版本(第 7 页)")
    vs = versions(con, 7)
    print(f"     台账记的:  3 组")
    print(f"     现在量的:  {len(vs)} 组")
    for pers, _, _ in vs:
        span = pers[0] if len(pers) == 1 else f"{pers[0]}~{pers[-1]}"
        print(f"                {span}")

    #  ④ 警告字段:还有多少道错题是【没出声】的
    #     ★ 这一条不用判分就能看:去向 + 警告
    silent = []
    for r, g in zip(rows, gots):
        if g.get("去向") in ("拒答", "检索·0条"):
            continue                      # 拒答/0条本身已经是出声
        if not g.get("警告"):
            silent.append(r["题号"])
    print(f"\n④ 一声不吭的题(不含拒答/0条 —— 那两种本身就在出声)")
    print(f"     台账记的:  24 道(第 6 课,警告字段全空)")
    print(f"     现在量的:  {len(silent)} 道  {silent[:12]}")

    print("""
  ★ 怎么读这张表:
      每一行【变了】的,都说明那条结论的【条件】跟现在不一样了。
      而条件变了,结论就得重写 —— 或者至少补上"在什么条件下成立"。

  ⚠ 这个脚本【只量不依赖判分的那几件事】——
     因为判分要用大模型,慢且要钱。得分那一栏请看 score_eval 的输出。
""")


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    main()
