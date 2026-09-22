# -*- coding: utf-8 -*-
r"""
第 8 课 · 报告的第一半:**把每一节要的数据查出来,而且把三种比法都算好。**

═══ 为什么先做这一半 ═══
    张君杰问:「这是硬编码吗?就不能像人一样理解文本然后回答吗?」

    答案是【分工】,不是二选一:
        代码管  「说什么数」  ← 硬,可核
        大模型管「怎么把数说成话」← 软,但它只能用手里的数

    所以先把「硬」的那半做出来、跑通 —— 因为它决定了大模型能拿到什么。
    **大模型的上限,是这一步给它什么。**

═══ 三种比法(张君杰选的「丁」:三个都要)═══
    ① 同档    这个机场 vs 它那一档(B3000万级以上 之类)
              ★ 2025Q4 才有分档数据 —— 别的期次没有这个版式,如实标"缺"
    ② 上期    这个机场 vs 它的上一期
    ③ 全体    这个机场 vs 全部 42 家

    **比错了组,结论会反。** 浦东 4.23 在【全体】排第 5,看着很好;
    但在【同档 11 家】里只排第 4 —— 因为它那个档位本来就是强档。

═══ ★ 每一条数据都带两样东西 ═══
    value   数值
    src     这个数从哪来(能回 PDF 页码)
    → 后面"大模型不许造数"的那道硬检查,靠的就是 src。

═══ ⚠ 一个必须说清的限制 ═══
    「同档平均」是【综合得分】的档位平均(报告里印着的)。
    **各指标的档位平均,报告里没印** —— 那是我用【同档其他机场的指标】自己算的。
    两者口径可能不同。**凡是我自己算的,src 里写清"自算",别冒充报告里的。**
"""
import sys, io, sqlite3
from pathlib import Path

DB = Path(r"D:\capse-kb\data\processed\capse.db")
PERIOD = "2025Q4"
AIRPORT = "上海浦东国际机场"


def _prev_period(con, p):
    """上一期。期次格式 2025Q4 —— 按 年*10+季 排序取前一个。"""
    key = lambda x: int(x[:4]) * 10 + int(x[5])
    ps = sorted((r[0] for r in con.execute("SELECT DISTINCT 期次 FROM 综合得分")), key=key)
    i = ps.index(p) if p in ps else -1
    return ps[i - 1] if i > 0 else None


def _overall(con, p, airport):
    r = con.execute("SELECT 得分, 来源 FROM 综合得分 WHERE 期次=? AND 机场=?",
                    (p, airport)).fetchone()
    return {"value": r[0], "src": r[1]} if r else None


def _rank_all(con, p, airport):
    rows = con.execute("SELECT 机场, 得分 FROM 综合得分 WHERE 期次=? ORDER BY 得分 DESC",
                       (p,)).fetchall()
    for i, (a, s) in enumerate(rows, 1):
        if a == airport:
            return {"value": i, "total": len(rows), "src": None,
                    "how": f"{p} 全部 {len(rows)} 家按得分降序,自算"}
    return None


def _tier(con, p, airport):
    t = con.execute("SELECT 档位, 行业平均, 来源 FROM 机场分档 WHERE 期次=? AND 机场=?",
                    (p, airport)).fetchone()
    if not t:
        return None                      # ★ 别的期次没有分档数据 —— 如实返回 None
    tier, avg, src = t
    rows = con.execute("""SELECT s.机场, s.得分 FROM 综合得分 s
                          JOIN 机场分档 t ON t.期次=s.期次 AND t.机场=s.机场
                          WHERE s.期次=? AND t.档位=? ORDER BY s.得分 DESC""",
                       (p, tier)).fetchall()
    rank = next((i for i, (a, _) in enumerate(rows, 1) if a == airport), None)
    return {"档位": tier, "行业平均": {"value": avg, "src": src},
            "同档排名": {"value": rank, "total": len(rows), "src": None, "how": "自算"},
            "同档各家": [(a, s) for a, s in rows]}


def _indicators(con, p, airport):
    mine = con.execute("""SELECT 指标, 得分, 来源 FROM 指标得分
                          WHERE 期次=? AND 机场=? ORDER BY 得分 DESC""",
                       (p, airport)).fetchall()
    if not mine:
        return None
    out = []
    for ind, sc, src in mine:
        avg_all = con.execute("SELECT AVG(得分) FROM 指标得分 WHERE 期次=? AND 指标=?",
                              (p, ind)).fetchone()[0]
        # 同档平均:自算(报告里没印各指标的档位平均)
        avg_tier = con.execute("""SELECT AVG(i.得分) FROM 指标得分 i
                                  JOIN 机场分档 t ON t.期次=i.期次 AND t.机场=i.机场
                                  WHERE i.期次=? AND i.指标=? AND t.档位=?""",
                               (p, ind, _tier(con, p, airport)["档位"])).fetchone()[0] \
            if _tier(con, p, airport) else None
        out.append({"指标": ind, "得分": {"value": sc, "src": src},
                    "比全体均值": {"value": round(sc - avg_all, 2), "src": None,
                                   "how": f"自算:该指标全体均值 {round(avg_all, 2)}"},
                    "比同档均值": ({"value": round(sc - avg_tier, 2), "src": None,
                                    "how": f"自算:该指标同档均值 {round(avg_tier, 2)}"}
                                   if avg_tier is not None else None)})
    return out


def _meta_counts(con, p):
    """本期有一级/二级指标各几项。**由库给,不由模型数。**"""
    #  ⚠ meta 表【没有来源列】—— 第 8 课的回填只做了 综合得分 / 指标得分 两张表。
    #    所以这几个数【追不回原文】。**如实标出来,不装作有出处。**
    #    (补它要动 build_meta_table.py,是另一件事 —— 记在待办里。)
    r = con.execute("SELECT 一级指标数, 二级指标数 FROM meta WHERE 期次=?", (p,)).fetchone()
    if not r:
        return None
    return {"一级指标数": {"value": r[0], "src": None, "how": "⚠ meta 表没回填页码,核不了"},
            "二级指标数": {"value": r[1], "src": None, "how": "⚠ meta 表没回填页码,核不了"}}


def build(con, period=PERIOD, airport=AIRPORT):
    prev = _prev_period(con, period)
    d = {
        "机场": airport, "期次": period, "上期": prev,
        "总体表现": {
            "综合得分": _overall(con, period, airport),
            "全体排名": _rank_all(con, period, airport),
            "同档": _tier(con, period, airport),
        },
        "核心指标": _indicators(con, period, airport),
        # ★ 「本期有几项指标」也要【由代码给】,不能让大模型自己数。
        #   实测:它写了「全部 7 项核心指标中的最低分」—— 那个 7 是它【数列表长度】数出来的。
        #   **它数对了,但"对"不代表"该由它算"** —— 该算的地方算,它只负责说。
        #   而 meta 表里本来就有这两个数,只是我没放进来。
        "本期指标数": _meta_counts(con, period),
        "变化与对比": {
            "上期得分": _overall(con, prev, airport) if prev else None,
            "差值": None,
        },
    }
    cur, old = d["总体表现"]["综合得分"], d["变化与对比"]["上期得分"]
    if cur and old:
        d["变化与对比"]["差值"] = {"value": round(cur["value"] - old["value"], 2),
                                   "src": None, "how": f"自算:{cur['value']} − {old['value']}"}
    return d


def render(d):
    """★ 纯代码渲染的一版 —— 先看【硬的部分】够不够撑起五节,再决定要不要接大模型。"""
    print("=" * 78)
    print(f"  {d['机场']}  {d['期次']}  —— 数据(还没有组织成话)")
    print("=" * 78)

    t = d["总体表现"]
    print("\n【1 总体表现】")
    g = t["综合得分"]
    print(f"   综合得分 {g['value']}      ← 原文 {g['src']}")
    r = t["全体排名"]
    print(f"   全体排名 {r['value']}/{r['total']}  ({r['how']})")
    ti = t["同档"]
    if ti:
        print(f"   所属档位 {ti['档位']}(行业平均 {ti['行业平均']['value']},"
              f"← 原文 {ti['行业平均']['src']})")
        print(f"   同档排名 {ti['同档排名']['value']}/{ti['同档排名']['total']}  "
              f"({ti['同档排名']['how']})")
    else:
        print(f"   ⚠ 同档对比:这一期没有分档数据(报告里没印)—— 缺")

    print("\n【2 核心指标】(按得分降序)")
    for x in d["核心指标"] or []:
        line = f"   {x['指标']:<12} {x['得分']['value']}   ← 原文 {x['得分']['src']}"
        line += f"\n        比全体均值 {x['比全体均值']['value']:+.2f}({x['比全体均值']['how']})"
        if x["比同档均值"]:
            line += f"\n        比同档均值 {x['比同档均值']['value']:+.2f}({x['比同档均值']['how']})"
        print(line)

    print("\n【3 变化与对比】")
    c = d["变化与对比"]
    if c["上期得分"]:
        print(f"   上期({d['上期']}) {c['上期得分']['value']}  ← 原文 {c['上期得分']['src']}")
        print(f"   差值 {c['差值']['value']:+.2f}  ({c['差值']['how']})")
    print(f"   全体 {d['总体表现']['全体排名']['total']} 家;"
          f"同档 {ti['同档排名']['total'] if ti else '?'} 家")

    print("\n【4 问题与亮点】")
    inds = d["核心指标"] or []
    if inds:
        weak = min(inds, key=lambda x: x["比同档均值"]["value"] if x["比同档均值"] else 0)
        strong = max(inds, key=lambda x: x["比同档均值"]["value"] if x["比同档均值"] else 0)
        print(f"   最弱:{weak['指标']} {weak['得分']['value']} "
              f"(比同档 {weak['比同档均值']['value']:+.2f})")
        print(f"   最强:{strong['指标']} {strong['得分']['value']} "
              f"(比同档 {strong['比同档均值']['value']:+.2f})")

    print("\n【5 结论与建议】")
    print("   (这一节系统给不了 —— 它只会【查】和【算】,不会【下结论】)")


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    con = sqlite3.connect(DB)
    render(build(con))
