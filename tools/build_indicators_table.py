# -*- coding: utf-8 -*-
r"""
把 2025Q4 的 7 个一级指标 × 42 家机场,汇总成长表:
    期次 / 指标 / 机场 / 得分

═══ 为什么只有这一期 ═══
    9 份季度报告里,只有 2025Q4 公布了指标级(而不是综合)的机场排名。
    其余 8 期只有"综合得分"。
    所以这张表天然只有 2025Q4 一个期次 —— 这不是偷懒,是语料的真实形状。
    【这个稀疏性本身就是拒答机制的来源】:
        "2025Q4 深圳宝安的机场商贸得分?"  → 有     → 第一档:直接答
        "2024Q3 深圳宝安的机场商贸得分?"  → 没有   → 第三档:拒答
        "2025Q4 深圳宝安在哪些指标上进了前十?" → 有 → 多跳查询
    没有这张表,上面三个问题里有两个是"答不出来但看起来能答"。

═══ 三道自检 ═══
    ① 总行数 == 7 × 42 == 294
    ② 每个指标的机场数 == 42,且指标名集合 == 报告自己列的那 7 个
    ③ 【跨表结构校验】同一家机场的 7 个一级指标分数,其【综合得分】必须落在
       这 7 个数的 [最小值, 最大值] 之间。
       依据:综合得分若由一级指标加权而来,加权平均必然落在极值之间 ——
             这是不等式保证的,与权重具体是多少无关。
       这一道跨了【两张表、两条独立的提取路径】,比表内自检又强一层。
       ※ 若不成立,说明"综合得分"不是从这 7 个指标算出来的,而是另一套口径 ——
         那本身就是一个必须写进文档的发现,不能当成 bug 修掉。
"""
import sys, io, csv
from pathlib import Path
from collections import Counter, defaultdict

sys.path.insert(0, str(Path(__file__).parent))
from extract_indicators import extract
from build_scores_table import get_pdf_files, get_period

PROCESSED   = Path(r"D:\capse-kb\data\processed")
SCORES_CSV  = PROCESSED / "capse_scores.csv"
OUT         = PROCESSED / "capse_indicators.csv"

PERIOD = "2025Q4"
AIRPORTS_PER_INDICATOR = 42
EXPECTED_ROWS = 7 * AIRPORTS_PER_INDICATOR      # 294


def source_pdf():
    for f in get_pdf_files():
        if get_period(f.name) == PERIOD:
            return f
    raise FileNotFoundError(f"没找到 {PERIOD} 的报告")


def build_table(pdf_path):
    rows = []
    for indicator, pairs, _page_i in extract(pdf_path):
        rows.extend((PERIOD, indicator, airport, score) for airport, score in pairs)
    return rows


def load_overall_scores():
    """读综合得分表,只要 2025Q4 那张 —— 独立信源,供跨表校验用。"""
    out = {}
    with open(SCORES_CSV, encoding='utf-8-sig', newline='') as f:
        for r in csv.DictReader(f):
            if r['期次'] == PERIOD:
                out[r['机场']] = float(r['得分'])
    return out


def check(rows, overall):
    if len(rows) != EXPECTED_ROWS:
        raise ValueError(f"总行数 {len(rows)} ≠ 期望 {EXPECTED_ROWS} —— 去找原因,别改数字")

    per_indicator = Counter(r[1] for r in rows)
    bad = {k: v for k, v in per_indicator.items() if v != AIRPORTS_PER_INDICATOR}
    if bad:
        raise ValueError(f"这些指标的机场数不是 {AIRPORTS_PER_INDICATOR}: {bad}")
    if len(per_indicator) != 7:
        raise ValueError(f"指标数 {len(per_indicator)} ≠ 7: {sorted(per_indicator)}")

    # 机场名单必须跟综合得分表里 2025Q4 的那 42 家完全一致 —— 否则两张表没法在机场维度上对起来
    names = {r[2] for r in rows}
    if names != set(overall):
        only_ind = names - set(overall)
        only_ovr = set(overall) - names
        raise ValueError(f"机场名单对不上\n    只在指标表: {sorted(only_ind)}\n    只在综合表: {sorted(only_ovr)}")


def cross_check_bounds(rows, overall):
    """③ 综合得分是否落在该机场 7 个一级指标的极值之间。返回违规清单(不抛异常)。

    不抛异常的原因:这一道的意义是【发现"综合得分另有一套口径"这件事】,
    而不是"改到它通过"。发现本身就是结果,要原样报出来。
    """
    by_airport = defaultdict(dict)
    for _, indicator, airport, score in rows:
        by_airport[airport][indicator] = float(score)

    bad = []
    for airport, inds in sorted(by_airport.items()):
        ov = overall[airport]
        lo, hi = min(inds.values()), max(inds.values())
        if not (lo - 1e-9 <= ov <= hi + 1e-9):
            bad.append((airport, ov, lo, hi, dict(inds)))
    return bad


def write_csv(rows, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow(['期次', '指标', '机场', '得分'])
        w.writerows(rows)


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    pdf = source_pdf()
    overall = load_overall_scores()
    rows = build_table(pdf)
    check(rows, overall)                     # ← ① ② 先自检

    write_csv(rows, OUT)

    print(f"写出 {OUT}  ({len(rows)} 行)\n")
    for ind, n in Counter(r[1] for r in rows).items():
        print(f"    {ind:<12}{n:>3} 家")

    # ③ 跨表结构校验
    bad = cross_check_bounds(rows, overall)
    print(f"\n③ 跨表校验:综合得分是否落在 7 个一级指标的极值之间")
    if not bad:
        print(f"    全部 {len(overall)} 家通过 —— 综合得分确实是这 7 个指标的加权结果")
    else:
        print(f"    {len(bad)} 家不满足(这本身是发现,不是要修的 bug):")
        for airport, ov, lo, hi, inds in bad[:8]:
            print(f"      {airport}: 综合 {ov}  指标区间 [{lo}, {hi}]")
            print(f"          {inds}")
