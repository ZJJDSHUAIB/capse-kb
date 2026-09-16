# -*- coding: utf-8 -*-
"""
把 9 份 CAPSE 季度报告,汇总成一张长表:期次 / 机场 / 综合得分。

长表(每个数字一行),不是宽表(每期一列)。原因:
    宽表把"跨期对比"变成默认状态 —— 并排放着就会有人去减。
    长表让"对比"必须显式执行,而那次执行就是你插口径检查的地方。
    而且期次之间口径不同(6+31 → 7+28),宽表的列名装不下这件事。

用法:  python D:/capse-kb/tools/build_scores_table.py
"""
import sys
import io
import re
import csv
from pathlib import Path
from collections import Counter

# 复用已经写好并验过的提取器
sys.path.insert(0, str(Path(__file__).parent))
from extract_scores import extract
# 注意:这里【不能】在模块级 sys.stdout = TextIOWrapper(...)。
# 一旦有人 import 本模块,那层 wrapper 会在被替换后被垃圾回收,
# 回收时会顺手关掉底层 buffer —— 调用方的 print 就 "I/O operation on closed file"。
# 编码设置只属于"我自己当脚本跑"这一种情况,放进 __main__。

DATA = Path(r"D:\capse-kb\data")
OUT  = Path(r"D:\capse-kb\data\processed\capse_scores.csv")

PERIOD = re.compile(r'CAPSE_(\d{4}Q\d)')   # 只认"季度报告"这个命名
EXPECTED_ROWS = 373                         # 5期×41 + 4期×42


def get_pdf_files():
    """只收季度报告。

    判据是【文件名里有 CAPSE_YYYYQn】,而不是"排除某个长文件名" ——
    2024年度报告没有机场级得分,自然匹配不上,不用特意排除。
    """
    return sorted(f for f in DATA.glob("*.pdf") if PERIOD.search(f.name))


def get_period(file_name):
    """'CAPSE_2025Q1_机场服务测评报告.pdf.pdf' → '2025Q1'"""
    m = PERIOD.search(file_name)
    return m.group(1) if m else None


def build_table():
    """返回 [(期次, 机场, 得分), ...]"""
    rows = []
    for f in get_pdf_files():
        period = get_period(f.name)
        _, pairs, _ = extract(f)          # extract 内部已跑过三道自检
        rows.extend((period, airport, score) for airport, score in pairs)
    return rows


def sort_table(rows):
    """期次升序;同一期内按得分降序。"""
    return sorted(rows, key=lambda r: (r[0], -float(r[2])))


def check(rows):
    """自检。不过就报错 —— 不写出可疑的表。"""
    if len(rows) != EXPECTED_ROWS:
        raise ValueError(f"总行数 {len(rows)} ≠ 期望 {EXPECTED_ROWS} —— 去找原因,别改数字")

    counts = Counter(r[0] for r in rows)
    bad = {p: c for p, c in counts.items() if c not in (41, 42)}
    if bad:
        raise ValueError(f"这些期的家数不对(应为41或42): {bad}")
    return counts


def write_csv(rows, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', newline='', encoding='utf-8-sig') as f:   # utf-8-sig:Excel 打开不乱码
        w = csv.writer(f)
        w.writerow(['期次', '机场', '得分'])
        w.writerows(rows)


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')   # 只在这里改 stdout
    rows = build_table()
    counts = check(rows)          # ← 先自检
    rows = sort_table(rows)       # ← 再排序(上次就是漏了这一步)

    write_csv(rows, OUT)

    print(f"{'期次':<8}{'家数':>5}")
    print("-" * 15)
    for p, c in sorted(counts.items()):
        print(f"{p:<8}{c:>5}")
    print("-" * 15)
    print(f"{'合计':<8}{len(rows):>5}\n")

    print("前 3 行:")
    for r in rows[:3]:
        print(f"   {r}")
    print("后 3 行:")
    for r in rows[-3:]:
        print(f"   {r}")

    print(f"\n✅ 已写入 {OUT}")
