# -*- coding: utf-8 -*-
r"""
报告链的尺子 —— 第 22 课。

═══ 为什么需要它（实测：报告链【完全在尺子外面】）═══
    ★ 项目里有 8 套自检(score_eval / agent_eval / check_loop / …),
      而它们量的全是【问答那条链】。
    ★★ 而报告链(make_report → report_data → report_gen → report_conclude)
      —— 【一次都没被测过】。今天所有改动,它一次都没跑到。
    ★★★ 那正是这一路反复出现的:「量具只覆盖它覆盖的地方」。

═══ 报告链【自己】有一道把关,而它只有一个方向 ═══
    report_gen.audit:  "报告里的数,data 里有吗"
    ★★ 缺的是另一个方向:
       · data 里的数,报告里用上了吗
       · ★ 用【对】了吗 —— 那是这一把尺子管的
    ★★★ 而"用对了没有"里,最贵的是【方向】:
       report_data 的注释自己写着:
         「比错了组，结论会反。浦东 4.23 在【全体】排第 5,看着很好;
           但在【同档 11 家】里只排第 4 —— 因为它那个档位本来就是强档。」
       ★ 所以一句"高于全体均值 0.09"如果写成"低于" ——
         报告读起来一样顺,而结论【反了】。

═══ 判据是【能算的】—— 不靠理解 ═══
    data 里每一个"比 X 均值"都带 value,而【正负就是方向】。
    ★ 所以:报告说"高" → 那个数该是正的;说"低" → 该是负的。
    ★★ 而它【不用大模型判】—— 那是 hard check。

=== 怎么用 ===
    python tools/报告测试.py              # 拿现成的那份报告核
    python tools/报告测试.py --重生成       # 先重新生成,再核
"""
import sys, io, re, sqlite3, argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from paths import DOCS, DB

报告目录 = DOCS / "报告"
机场, 期次 = "上海浦东国际机场", "2025Q4"
报告文件 = 报告目录 / f"{机场}_{期次}.md"

#  ★ 说"高"的词 / 说"低"的词 —— 分开列,别用"含高"这种松判据
说高 = ("高于", "高出", "领先", "超过")
说低 = ("低于", "低出", "落后", "不如")


def 取带符号的数(d):
    """★ 报告数据里所有"比 X 均值"的 value —— 正负就是方向。"""
    出 = {}
    for it in (d.get("核心指标") or []):
        for 比 in ("比全体均值", "比同档均值"):
            v = (it.get(比) or {}).get("value")
            if isinstance(v, (int, float)):
                出[round(abs(v), 2)] = 出.get(round(abs(v), 2), []) + [
                    (it.get("指标"), 比, v)]
    return 出


def 核(文, d):
    """返回 (核了几处, 分不清几处, [方向错的…])。"""
    表 = 取带符号的数(d)
    核过 = 歧 = 0
    错 = []
    for 句 in re.split(r'(?<=[。；])|\n', 文):
        for m in re.finditer(r'(' + "|".join(说高 + 说低) + r')([^0-9]{0,8})(\d+\.\d+)',
                            句):
            方, 数 = m.group(1), round(float(m.group(3)), 2)
            候 = 表.get(数)
            if not 候:
                continue
            if len(候) > 1:
                #  ★ 同一个 |值| 出现在两处(比如 +0.07 和 −0.07)——
                #    这时要看【这一句里提了哪个指标】,不能随便挑一个。
                #    ⚠ 第一版就是随便挑第一个,于是报了 5 个假错。
                命中 = [c for c in 候 if c[0] and c[0] in 句]
                if len(命中) != 1:
                    歧 += 1
                    continue
                候 = 命中
            指, 比, 真 = 候[0]
            核过 += 1
            #  ★ 差为 0 时方向无意义 —— 不算错
            if abs(真) <= 0.005:
                continue
            该高 = 真 > 0
            if (方 in 说高) != 该高:
                错.append((指, 比, 方 + str(数), 真))
    return 核过, 歧, 错


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--重生成", action="store_true", help="先重新生成报告再核")
    a = ap.parse_args()
    con = sqlite3.connect(DB)

    if a.重生成:
        import make_report
        make_report.main()
    if not 报告文件.exists():
        print(f"⚠ 报告不在:{报告文件}\n  ★ 先跑 python tools/make_report.py")
        return

    文 = 报告文件.read_text(encoding="utf-8")
    import report_data
    d = report_data.build(con, 期次, 机场)

    print("=" * 76)
    print("  报告链的尺子:【每一句「比 X 高/低」,方向对不对】")
    print("=" * 76)
    print(f"  报告:{报告文件.name}（{len(文)} 字）")
    print(f"  数据:（指标 × 比法）"
          f"{sum(len(v) for v in 取带符号的数(d).values())} 个")

    核过, 歧, 错 = 核(文, d)
    print(f"\n  ★ 逐处核了 {核过} 处")
    print(f"  ★ 分不清的 {歧} 处（同一个数在两处出现,而这句没点名指标）")
    if 错:
        print(f"\n  ★★ 方向错的 {len(错)} 处:")
        for 指, 比, 说, 真 in 错:
            print(f"      ✗ {指} · {比} —— 报告说「{说}」,而数据是 {真}")
    else:
        print("\n  ★★ 方向错的:0 处 ✅")
    print("\n" + "=" * 76)
    print("""
  ★ 这一把量的是【方向上有没有说反】—— 那是最贵的一类错:
     报告读起来一样顺,而【结论反了】。
  ⚠ 而它【量不到】的,也要说清:
     · 报告里【没提】哪些数（那是"漏",不是"反"）
     · 一句话里的因果关系对不对（那要理解,不是算）
  ★★ 而这两样要量,得另想办法 —— 别把它当成"报告全对了"。""")


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    main()
