# -*- coding: utf-8 -*-
r"""
第 8 课 · 抽「机场分档」—— 报告能不能"推"的关键原料。

═══ 为什么需要它 ═══
    张君杰问:「为什么浦东 2025Q4 的表现是这样?」系统答不出来。

    查下去发现,"推"需要的对比基准【只印在 PDF 的文本里,从来没进过库】:

        2025Q4-P18  「…4.13 平均, 4.15北京大兴国际机场…」   ← 4000万级以上,平均 4.13
        2025Q4-P19  「…4.11 平均, 4.15厦门高崎国际机场…」   ← 2500万-4000万级,平均 4.11
        2025Q4-P20  「…4.09 平均, …」                        ← 1500万-2500万级,平均 4.09
        2025Q4-P21  「…4.05平均, …」                         ← 1000万-1500万级,平均 4.05

    **而"浦东属哪一档",连字段都没有。**

    → 拿【全部机场的平均】去比会得出错的结论:浦东是 4000万级以上的大机场,
      该跟同一个档位比。**比错了组,"哪项弱"的结论会反。**

═══ 三样都从这四页抽 ═══
    ① 档位名     「2025Q4—(4000万级以上)机场综合得分」
    ② 行业平均   「(4.13) 平均」
    ③ 哪些机场属这一档  —— 平均分后面那一串机场名

    ★ ③ 是最要紧的:它把"这个机场该跟谁比"这件事,从【没定义】变成【有据可查】。

═══ ⚠ 局限(必须写清)═══
    分档数据【只有 2025Q4 一期】有。别的期次没有这个版式。
    → 所以"同档对比"只能在 2025Q4 上做。
    → 别的期的报告只能用【上期对比】和【全体对比】。
    **这不是脚本的毛病,是报告本身没有印。**
"""
import sys, io, re, csv, sqlite3
from pathlib import Path
from paths import ROOT, DATA, PROCESSED, DOCS, DB, OUTPUT

OUT = PROCESSED / "capse_tiers.csv"
PERIOD = "2025Q4"
TIER_PAGES = ["2025Q4-P18", "2025Q4-P19", "2025Q4-P20", "2025Q4-P21"]

TIER_NAME = re.compile(r'—\s*([^机]+?)\s*机场综合得分')
AVG = re.compile(r'(\d+\.\d+)\s*平均')


def extract_tiers(con):
    """返回 [(期次, 机场, 档位, 行业平均, 来源chunk), ...]"""
    # 库里所有机场名 —— 用来从那一串文本里认出机场
    names = sorted((r[0] for r in con.execute(
        "SELECT 机场 FROM 综合得分 WHERE 期次=?", (PERIOD,))), key=len, reverse=True)
    rows, seen = [], set()
    for cid in TIER_PAGES:
        t = con.execute("SELECT 文本 FROM chunk WHERE chunk_id=?", (cid,)).fetchone()
        if not t:
            raise FileNotFoundError(f"库里没有 {cid} —— 分档页不在,先查切片")
        text = t[0]
        mname, mavg = TIER_NAME.search(text), AVG.search(text)
        if not (mname and mavg):
            raise ValueError(f"{cid} 里抽不出档位名或平均分 —— 版式变了,别硬猜")
        tier, avg = mname.group(1).strip(), float(mavg.group(1))
        # 从这一页里认机场:长的优先,认到就划掉,避免"上海浦东"被"上海"抢走
        rest, hit = text, []
        for n in names:
            if n in rest:
                hit.append(n)
                rest = rest.replace(n, " ")
        if not hit:
            raise ValueError(f"{cid}({tier}) 里一个机场名都没认出来 —— 版式变了")
        print(f"  {cid}  档位「{tier}」  行业平均 {avg}   {len(hit)} 家机场")
        for n in hit:
            if (PERIOD, n) in seen:
                continue
            seen.add((PERIOD, n))
            rows.append((PERIOD, n, tier, avg, cid))
    return rows


def check(rows, con):
    """自检:每家在库里都有综合得分;每家只属一档;档位家数加起来 == 全部家数。"""
    have = {r[0] for r in con.execute("SELECT 机场 FROM 综合得分 WHERE 期次=?", (PERIOD,))}
    got = [r[1] for r in rows]
    if len(got) != len(set(got)):
        dup = [n for n in set(got) if got.count(n) > 1]
        raise ValueError(f"这些机场被分进了多个档:{dup}")
    missing = have - set(got)
    if missing:
        raise ValueError(f"这些机场【没被分到任何档】:{sorted(missing)} —— 别猜,去查那一页")
    extra = set(got) - have
    if extra:
        raise ValueError(f"这些名字不在综合得分表里:{sorted(extra)}")
    return len(rows)


def main():
    con = sqlite3.connect(DB)
    print(f"从 {PERIOD} 的四张分档页里抽:")
    rows = extract_tiers(con)
    n = check(rows, con)
    print(f"\n✅ 自检通过:{n} 家,每家恰好一个档,一个不漏")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["期次", "机场", "档位", "行业平均", "来源chunk"])
        w.writerows(rows)
    print(f"✅ 已写入 {OUT}")
    print("\n各档:")
    for t in dict.fromkeys(r[2] for r in rows):
        sub = [r for r in rows if r[2] == t]
        print(f"  {t:<16} {len(sub):>2} 家   平均 {sub[0][3]}")


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    main()
