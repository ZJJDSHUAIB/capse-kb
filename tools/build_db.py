# -*- coding: utf-8 -*-
r"""
第 2 课:把三张 CSV 装进一个能被 SQL 查的库。

═══ 为什么需要它(不做的后果) ═══
    CSV 是"躺着"的数据。每查一个问题,都要现写一段 Python:

        "2025Q4 口径是啥?"  → import csv ... 5 行 → 才拿到 7+28

    更严重的:CSV 里【没有排名】。
        排名不是数据,是【派生量】——它必须由"排序"算出来。
        在 CSV 上,每次问排名都要现写一次排序;写十次,就有十次写错的机会。

═══ 做完之后,三类问题各有一条确定的路 ═══
    查    "2025Q4 口径是啥"          → 一条 SQL,问一万次答案一样
    算    "上海浦东 2025Q4 排第几"    → SQL 排序,【代码算的,不是模型猜的】
    跨表  "口径是哪几期变的"          → 时间序列 diff,只有结构化的行做得到

    ※ 第三条是 meta 表独有的能力:它是九行【结构化的行】,能排序、能 diff。
      而 chunk 里那段话是【一段文本】,你没法 diff 两段话。
      —— "结构决定你能问什么问题",与第 0 部分"长表 vs 宽表"同一条原则。

═══ 三个 schema 决策,理由如下 ═══

    ① 【不存排名】—— 排名是派生量,用「视图」代替
      存下来就会过期:数据一更新,存的排名就是错的,而且【错得看不出来】。
      视图不存数据,只存"查询的定义",每次读时现算 —— 永远和源数据一致。
      这不是性能取舍,是【一致性】取舍。

    ② 【口径版本用 CHECK 约束】—— 把 Python 里的 VALID_VERSIONS 搬进 schema
      build_meta_table.py 里有一句 VALID_VERSIONS = {'6+30','6+31','7+28'},
      但那只是"我运行时检查一下"。数据库层的 CHECK 更强:
      就算有人【手写一条 INSERT】,非法口径也进不去。
      ※ 副作用是好的:将来加新期次,如果口径变了,你必须【显式改这一行】——
        它逼你面对"口径变了"这件事,而不是让它悄悄流进来。

    ③ 【得分只做宽松下限检查,不卡死区间】
      CHECK (得分 > 0),不写 CHECK (得分 BETWEEN 3.9 AND 4.7)。
      因为后者是把当前数据的区间【写死】了 —— 换一份报告就炸。
      宽松约束只拦"解析失败"这类事故(负数、0),不拦真实的分数变化。

═══ 自检 ═══
    ① 每张表的行数 == CSV 行数
    ② 往返一致:从库里读回来的行,和 CSV 里的一模一样
    ③ 约束真的生效:【故意插一条非法数据】,必须被拒绝
       —— 这一条是"验约束本身",不是"验数据"。约束没生效 = 白写。
"""
import sys, io, csv, sqlite3
from pathlib import Path

PROCESSED = Path(r"D:\capse-kb\data\processed")
DB        = PROCESSED / "capse.db"

# 与 build_meta_table.py 里的 VALID_VERSIONS 一致。
# 但这里它是【数据库层的守门人】,不是"运行时检查一下"。
VALID_VERSIONS = ('6+30', '6+31', '7+28')

SCHEMA = f"""
PRAGMA foreign_keys = ON;

CREATE TABLE meta (
    期次         TEXT PRIMARY KEY,
    样本量       INTEGER NOT NULL CHECK (样本量 > 0),
    机场数       INTEGER NOT NULL CHECK (机场数 > 0),
    一级指标数   INTEGER NOT NULL CHECK (一级指标数 > 0),
    二级指标数   INTEGER NOT NULL CHECK (二级指标数 > 0),
    口径版本     TEXT    NOT NULL CHECK (口径版本 IN {VALID_VERSIONS}),
    -- 口径版本必须和两个指标数【自洽】—— 不允许出现 7+28 却写着 6+30 的行
    CHECK (口径版本 = 一级指标数 || '+' || 二级指标数)
);

CREATE TABLE 综合得分 (
    期次   TEXT NOT NULL REFERENCES meta(期次),
    机场   TEXT NOT NULL,
    得分   REAL NOT NULL CHECK (得分 > 0),
    PRIMARY KEY (期次, 机场)
);

CREATE TABLE 指标得分 (
    期次   TEXT NOT NULL REFERENCES meta(期次),
    指标   TEXT NOT NULL,
    机场   TEXT NOT NULL,
    得分   REAL NOT NULL CHECK (得分 > 0),
    PRIMARY KEY (期次, 指标, 机场)
);

-- ① 排名【不存】,存"怎么算" —— 视图每次读时现算,永远和源数据一致
CREATE VIEW 综合得分排名 AS
SELECT 期次,
       机场,
       得分,
       ROW_NUMBER() OVER (PARTITION BY 期次 ORDER BY 得分 DESC) AS 排名,
       COUNT(*)     OVER (PARTITION BY 期次)                    AS 本期机场数
FROM 综合得分;
"""


def read_csv(name):
    with open(PROCESSED / name, encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def build():
    if DB.exists():
        DB.unlink()                       # 每次重建,保证可复现
    con = sqlite3.connect(DB)
    con.executescript(SCHEMA)

    meta = read_csv("capse_meta.csv")
    con.executemany(
        "INSERT INTO meta VALUES (?,?,?,?,?,?)",
        [(r['期次'], int(r['样本量']), int(r['机场数']),
          int(r['一级指标数']), int(r['二级指标数']), r['口径版本']) for r in meta])

    scores = read_csv("capse_scores.csv")
    con.executemany("INSERT INTO 综合得分 VALUES (?,?,?)",
                    [(r['期次'], r['机场'], float(r['得分'])) for r in scores])

    inds = read_csv("capse_indicators.csv")
    con.executemany("INSERT INTO 指标得分 VALUES (?,?,?,?)",
                    [(r['期次'], r['指标'], r['机场'], float(r['得分'])) for r in inds])

    con.commit()
    return con, {"meta": meta, "综合得分": scores, "指标得分": inds}


def check(con, source):
    """① 行数一致  ② 往返一致  ③ 约束真的生效"""
    # ①
    for table, rows in source.items():
        n = con.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
        if n != len(rows):
            raise ValueError(f"{table}: 库里 {n} 行,CSV {len(rows)} 行 —— 对不上")
        print(f"  {table:<10}{n:>5} 行  ✅")

    # ② 往返:库里读回来的集合,必须和 CSV 的集合完全相同
    got = {(r[0], r[1], r[2]) for r in con.execute("SELECT 期次,机场,得分 FROM 综合得分")}
    want = {(r['期次'], r['机场'], float(r['得分'])) for r in source["综合得分"]}
    if got != want:
        raise ValueError(f"综合得分往返不一致: 库多 {got - want} / 库少 {want - got}")
    print("  往返一致  ✅")

    # ③ 约束自检 —— 拿【非法数据】去撞,撞不进去才算约束生效
    bad_cases = [
        ("口径版本不在清单里", "INSERT INTO meta VALUES ('2099Q1',1,1,6,30,'9+99')"),
        ("口径版本与指标数不自洽", "INSERT INTO meta VALUES ('2099Q1',1,1,7,28,'6+30')"),
        ("期次不存在(外键)", "INSERT INTO 综合得分 VALUES ('2099Q1','某机场',4.0)"),
        ("得分是负数", "INSERT INTO 综合得分 VALUES ('2025Q4','某机场',-1)"),
        ("同一(期次,机场)重复", "INSERT INTO 综合得分 VALUES ('2025Q4','上海浦东国际机场',4.0)"),
    ]
    for label, sql in bad_cases:
        try:
            con.execute(sql)
            con.rollback()
            raise ValueError(f"★ 约束没生效: 居然插进去了 —— {label}")
        except sqlite3.IntegrityError:
            print(f"  拦住: {label:<22} ✅")
    con.rollback()


def demo(con):
    q = lambda sql: con.execute(sql).fetchall()

    print("\n【查】2025Q4 是什么口径?")
    print("   SQL:", "SELECT 口径版本 FROM meta WHERE 期次='2025Q4'")
    print("   结果:", q("SELECT 口径版本 FROM meta WHERE 期次='2025Q4'")[0][0])

    print("\n【算】2025Q4 上海浦东排第几? (排名不在数据里,是算出来的)")
    print("   SQL:", "SELECT 排名,得分 FROM 综合得分排名 WHERE 期次=? AND 机场 LIKE ?")
    print("   结果:", q("SELECT 排名,得分 FROM 综合得分排名 "
                      "WHERE 期次='2025Q4' AND 机场 LIKE '上海浦东%'"))

    print("\n【跨表】2025Q4 综合第一的机场,它 7 个指标各考了多少?")
    rows = q("""SELECT i.指标, i.得分
                FROM 指标得分 i
                JOIN (SELECT 机场 FROM 综合得分排名
                      WHERE 期次='2025Q4' AND 排名=1) t ON i.机场 = t.机场
                WHERE i.期次='2025Q4' ORDER BY i.得分 DESC""")
    for name, s in rows:
        print(f"      {name:<14}{s}")

    print("\n【时间序列】口径是在哪几期变的? (chunk 里的一段话答不了这个)")
    rows = q("""SELECT 期次, 口径版本,
                       LAG(口径版本) OVER (ORDER BY 期次) AS 上一期
                FROM meta ORDER BY 期次""")
    for p, v, prev in rows:
        mark = "  ← 变了" if prev and prev != v else ""
        print(f"      {p}   {prev or '  —  '} → {v}{mark}")


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    con, source = build()
    print(f"写出 {DB}\n")
    print("=== 自检 ===")
    check(con, source)
    demo(con)
    con.close()
