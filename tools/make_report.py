# -*- coding: utf-8 -*-
r"""
第 8 课 · 出一份【完整的报告文件】。

═══ 为什么要有这一步 ═══
    前面几步都是命令行输出 —— 面试时你只能说,不能给他看。
    而报告是这个项目的【最终目的】("知识库 + 报告生成工作流")。
    所以这一步不是"再写个脚本",是【把前面所有东西拼成一件能拿出来的东西】。

═══ 它和 report_gen / report_conclude 的分工 ═══
    report_data.py      硬算:三种比法 + 出处(每条数据带 src)
    report_gen.py       软说:数据 → 前四节的话;publish 里的 audit 做硬查
    report_conclude.py  软说:数据 → 第 5 节的结论(标明是推断)
    ★ 这个文件          【组装】:调上面三个,拼成一份 markdown,再把把关结果附在末尾

    **所以它自己不产生任何判断 —— 它只负责把它们摆到一起。**

═══ ★ 报告里必须体现这一课建的东西 ═══
    ① 每个数字带出处,而且能回 PDF 页码(来源回填)
    ② 三种比法:同档 / 上期 / 全体
    ③ 事实与推断分开(前四节是事实,第 5 节标着是推断)
    ④ 硬查结果附在末尾 —— **报告里有没有一个数字是没有出处的**
    ⑤ ⚠ 报告本身也是一份数据,所以它也要能被核

    **一份"每个数都能核、错了会说出来"的报告,才叫报告。
      否则它只是"漂亮文档"。**
"""
import sys, io, json, sqlite3, datetime
from pathlib import Path
from paths import ROOT, DATA, PROCESSED, DOCS, DB, OUTPUT

sys.path.insert(0, str(Path(__file__).parent))

OUT_DIR = DOCS / "报告"
AIRPORT = "上海浦东国际机场"
PERIOD = "2025Q4"


def gen(con, airport=AIRPORT, period=PERIOD):
    from report_data import build
    from report_gen import PROMPT as P1, audit, collect_numbers
    from report_conclude import PROMPT as P2
    from llm import chat

    d = build(con, period, airport)
    brief = json.dumps(d, ensure_ascii=False, default=str)

    print("  ① 硬算 —— 三种比法 + 出处…")
    print("  ② 软说 —— 前四节…")
    body = chat(P1.format(sections="1 总体表现 / 2 核心指标 / 3 变化与对比 / 4 问题与亮点",
                          data=brief), max_tokens=1500)
    print("  ③ 软说 —— 第 5 节(结论与建议)…")
    sec5 = chat(P2.format(data=brief), max_tokens=1000)

    #  ★ 硬查:前四节和第 5 节【分开查】—— 它们的把关方式不一样
    #    前四节是"事实",每个数都要有出处;第 5 节是"推断",数也要有出处,
    #    但它多一层"整节声明"。
    bad1 = audit(body, d)
    bad5 = audit(sec5, d)
    return d, body, sec5, bad1, bad5


def render(d, body, sec5, bad1, bad5):
    L = []
    L.append(f"# {d['机场']} {d['期次']} · 机场满意度报告")
    L.append("")
    L.append(f"*生成于 {datetime.date.today()} · 数据源:CAPSE 机场服务测评报告(9 期)*")
    L.append("")
    # ── 把关结果放【最前面】──
    #   ※ 为什么在前:用户会从第一页读起。警告跟在后面等于没警告。
    L.append("## ★ 这份报告的可信程度")
    L.append("")
    if not bad1 and not bad5:
        L.append("- **前四节的每一个数字都能追到出处**(可回 PDF 页码)**—— 硬查通过。**")
    else:
        L.append(f"- ⚠ **前四节里有数字查不到出处:{sorted(bad1)} —— 这一段先别用。**")
    L.append("- **第 5 节整节是【推断】,不是数据。** 它依据的数都能核,但结论是推出来的,"
             "不是报告里印着的 —— **请按推断对待。**")
    if bad5:
        L.append(f"- ⚠ 第 5 节里有数字查不到出处:{sorted(bad5)}")
    t = d["总体表现"]["同档"]
    L.append(f"- 本期数据里,**{'同档(按吞吐量级)对比' if t else '没有分档数据,同档对比缺'}**。")
    L.append("")
    L.append("---")
    L.append("")
    L.append(body.strip())
    L.append("")
    L.append("---")
    L.append("")
    L.append("## 5 结论与建议")
    L.append("")
    L.append("*（以下整节是**推断**,不是数据 —— 依据的数都标了出处,但结论是推出来的。）*")
    L.append("")
    L.append(sec5.strip())
    L.append("")
    L.append("---")
    L.append("")
    L.append("## 附:这份报告的数据从哪来")
    L.append("")
    L.append("| 数据 | 值 | 出处 |")
    L.append("|---|---|---|")
    g = d["总体表现"]["综合得分"]
    L.append(f"| 综合得分 | {g['value']} | {g['src']} |")
    if t:
        L.append(f"| 同档行业平均 | {t['行业平均']['value']} | {t['行业平均']['src']} |")
    for x in (d["核心指标"] or []):
        L.append(f"| {x['指标']} | {x['得分']['value']} | {x['得分']['src']} |")
    L.append("")
    L.append("> **出处写成 `2025Q4-P09` 这样的形式 —— 它是 PDF 的期次和页码,能翻回去核。**")
    return "\n".join(L)


def main():
    con = sqlite3.connect(DB)
    print(f"生成报告:{AIRPORT} {PERIOD}")
    d, body, sec5, bad1, bad5 = gen(con)
    md = render(d, body, sec5, bad1, bad5)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"{AIRPORT}_{PERIOD}.md"
    out.write_text(md, encoding="utf-8")
    print(f"\n✅ 写出 {out}")
    print(f"   硬查:前四节 {'✅ 全部有据' if not bad1 else '★ 有查不到的:' + str(sorted(bad1))}")
    print(f"         第5节 {'✅ 全部有据' if not bad5 else '★ 有查不到的:' + str(sorted(bad5))}")


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    main()
