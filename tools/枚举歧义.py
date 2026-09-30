# -*- coding: utf-8 -*-
r"""
枚举歧义 —— 从库里【扫出】"该反问"和"不该反问"两类题,而不是我编。

═══ 它解决什么 ═══
    「问的不清楚的一律反问」—— 用户定的通则。
    ★ 而它一直立不起来,因为评估集里【"反问"是 0 道】。
    ★★ 而那个 0 不是"没想到",是【结构性的】:
       route() 的去向里压根没有"反问"(现在补上了)。

    补上出口之后,要【有题】才能验。
    而题从哪来?

═══ ★★★★★ 关键:不要我编题,要【从库里枚举】 ═══
    "该不该反问"这件事,判据是【能算的】:
        极值词的两种读法 → 算出来是同一个指标吗?
            一样  → ★ 乙类:不该反问(怎么理解都对)
            不同  → ★ 甲类:该反问

    ★ 所以可以【扫遍库里所有(期次, 机场)】,把两类都列出来。
    ★★ 而那样出来的题是【客观的】—— 不是我挑的,是从数据里长出来的。

═══ ⚠⚠ 为什么必须【两类都要】 ═══
    只出甲类(该反问)的题 → 一个【见谁问谁】的系统把全部题都反问,能拿满分。
    ★ 那和告警率那个"每题都报警"是【同一个坑】。
    ★★ 而你项目早就定过这条:误报率要和告警率【一起卡】。
    → 所以甲类和乙类要成对出现。

═══ ⚠ 枚举范围 ═══
    只有【有分档数据】的期次才能算第二种读法。
    实测:分档数据只有 2025Q4 一期。
    ★ 别的期次算不了 —— 那是【没有这条路】,不是"算出来一样"。

═══ 怎么用 ═══
    python tools/枚举歧义.py              # 扫一遍,打印两类各多少 + 示例
    python tools/枚举歧义.py --抽样 8      # 每类抽 8 条,写成 JSON 供加题
"""
import sys
import io
import json
import argparse
import sqlite3
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from paths import DB, DOCS


def 扫一类(con, 期次, 机场, 弱向=True):
    """这个(期次,机场)上,极值词的两种读法是同一个指标吗?

    ★ 返回 None = 算不了(没有分档数据 / 指标少于两项)
    ★ 返回 True  = 甲类【该反问】(两种读法不同)
    ★ 返回 False = 乙类【不该反问】(两种读法相同)
    """
    from ask import 逐项同档数据
    各 = 逐项同档数据(con, 期次, 机场)
    if not 各 or len(各) < 2:
        return None
    挑 = min if 弱向 else max
    按分 = 挑(各, key=lambda x: x[1])[0]      # 按分数
    按差 = 挑(各, key=lambda x: x[3])[0]      # 按和同档的差
    return 按分 != 按差


def 扫全部(con):
    """扫遍所有(有分档数据的期次 × 机场)。"""
    对 = con.execute("SELECT DISTINCT 期次, 机场 FROM 机场分档 ORDER BY 期次, 机场").fetchall()
    甲, 乙, 算不了 = [], [], []
    for 期, 机 in 对:
        r = 扫一类(con, 期, 机, 弱向=True)      # 只做"最弱"这一侧
        if r is None:
            算不了.append((期, 机))
        elif r:
            甲.append((期, 机))
        else:
            乙.append((期, 机))
    return 甲, 乙, 算不了


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--抽样", type=int, default=0,
                    help="每类抽 N 条,写成 JSON(0 = 只看统计)")
    ap.add_argument("--期次", default="2025Q4")
    a = ap.parse_args()

    con = sqlite3.connect(DB)
    print("=" * 74)
    print("  枚举歧义 —— 从库里扫出两类题")
    print("=" * 74)

    甲, 乙, 算不了 = 扫全部(con)
    总 = len(甲) + len(乙) + len(算不了)
    print(f"\n  扫了 {总} 个 (期次, 机场) 组合")
    print(f"    ★ 甲类【该反问】(两种读法不同): {len(甲)}")
    print(f"      乙类【不该反问】(两种读法相同): {len(乙)}")
    print(f"      ⚠ 算不了(没有分档数据/指标太少): {len(算不了)}")

    if 甲:
        print(f"\n  ── 甲类示例(该反问)──")
        for 期, 机 in 甲[:5]:
            from ask import 逐项同档数据
            各 = 逐项同档数据(con, 期, 机)
            按分 = min(各, key=lambda x: x[1])
            按差 = min(各, key=lambda x: x[3])
            print(f"     {期} {机}")
            print(f"        分数最低 = {按分[0]} ({按分[1]})")
            print(f"        比同档最差 = {按差[0]} (差 {按差[3]:+})")

    if 乙:
        print(f"\n  ── 乙类示例(不该反问)──")
        for 期, 机 in 乙[:5]:
            from ask import 逐项同档数据
            各 = 逐项同档数据(con, 期, 机)
            按分 = min(各, key=lambda x: x[1])
            print(f"     {期} {机} —— 两种读法都指向「{按分[0]}」")

    if a.抽样:
        #  ★ 两类【成对抽】—— 理由见文件开头那段:只抽甲类会让"全部反问"拿满分
        n = a.抽样
        批 = {
            "甲_该反问": [{"期次": p, "机场": k,
                          "问句": f"{k}{p}哪一项指标最弱",
                          "期望去向": "反问"} for p, k in 甲[:n]],
            "乙_不该反问": [{"期次": p, "机场": k,
                            "问句": f"{k}{p}哪一项指标最弱",
                            "期望去向": "SQL"} for p, k in 乙[:n]],
        }
        出 = DOCS / "内部" / "歧义枚举.json"
        出.parent.mkdir(exist_ok=True)
        出.write_text(json.dumps(批, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n  ✅ 每类抽 {n} 条,写到 {出}")
        print("       ★ 两类【成对】—— 只抽甲类的话,一个「见谁问谁」的系统能拿满分")

    print("\n" + "=" * 74)
    return 0


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.exit(main())
