# -*- coding: utf-8 -*-
r"""
你的任务:写一组【非法数据】,试着插进 capse.db,让库拒绝它们。

═══ 为什么要做这件事 ═══
    约束没生效 = 白写。而"约束生效了没有"不能靠读代码确认 ——
    必须拿真实的非法数据去撞一次。这就是这个文件存在的全部理由。

    写代码是【语法】,写"什么算非法"是【判断】。
    所以这一块由你来写,我负责验收和补洞。

═══ 库长什么样(你要攻击的对象) ═══

    meta (期次 是主键)
        期次  样本量  机场数  一级指标数  二级指标数  口径版本
        ※ 约束: 每个数是正整数
        ※ 约束: 口径版本只能是 6+30 / 6+31 / 7+28
        ※ 约束: 口径版本 必须 == 一级指标数 || '+' || 二级指标数
                 (比如一级=7、二级=28 时,口径版本必须是 "7+28")

    综合得分 (期次 + 机场 是联合主键)
        期次  机场  得分
        ※ 约束: 期次必须在 meta 里存在
        ※ 约束: 得分 > 0
        ※ 约束: 同一个(期次,机场)不能出现两次

    指标得分 (期次 + 指标 + 机场 是联合主键)
        期次  指标  机场  得分
        ※ 同上,另外还多了"指标"这一维

    综合得分排名  ← 这是【视图】,不存数据,插不进去也不用管它

═══ 真正的问题(想这个,不是想 SQL 语法) ═══
    "什么样的数据是【绝对】不该进这个库的?"

    提示:每一【列】都可以攻击 —— 数值、文本、空值
          每一【张表】都可以攻击
          每一【条关系】都可以攻击 —— 表与表之间、列与列之间
          每一个【数量】都可以攻击 —— 行数、个数、总数

═══ 怎么用 ═══
    在下面的 CASES 里,照着示例的格式往下写。然后跑:
        python tools/test_constraints.py

    看到 ✅  = 库拒绝了,约束生效
    看到 ★   = 库居然收了 —— 这是【有效发现】,我们要补约束
"""
import sqlite3
import sys, io
from pathlib import Path

DB = Path(r"D:\capse-kb\data\processed\capse.db")

# ══════════════════════════════════════════════════════════════
#  在这里写你的用例。格式:(名字, 一条 SQL)
#  ══════════════════════════════════════════════════════════════
CASES = [
    # ── 示例(我写的):口径版本不在允许清单里 ──────────────────
    ("口径版本不在允许清单里", "INSERT INTO meta VALUES ('2099Q1',1,1,6,30,'9+99')"),

    # ── 往下写你的 ───────────────────────────────────────────
    # 提示:先从"数值"下手试试 —— 有没有哪个数不可能是负的?
    #      (可以复制上面那行改;改完把名字也改掉)

    # ("给它起个名字", "INSERT INTO 表名 VALUES (...)"),

    # 提示:再从"关系"下手 —— 一张表里的数字,和另一张表里的行数,
    #      有没有"必须对得上"的地方?

    # ("给它起个名字", "INSERT INTO 表名 VALUES (...)"),
]


def run():
    if not DB.exists():
        raise SystemExit(f"找不到 {DB} —— 先跑 python tools/build_db.py")

    con = sqlite3.connect(DB)
    # ⚠ 坑:SQLite 的外键检查【默认是关的】,必须每个连接手动打开。
    #    不写这一行,"期次不存在"那条约束在本脚本里会假装通过。
    con.execute("PRAGMA foreign_keys = ON")

    n_ok, gaps, broken = 0, [], []
    for label, sql in CASES:
        if label.startswith("给它起个名字"):
            continue                                   # 还没填的模板行,跳过
        try:
            con.execute(sql)
            con.rollback()
            gaps.append((label, sql))
            print(f"  ★ 库收了它   {label}")
        except sqlite3.IntegrityError as e:
            n_ok += 1
            print(f"  ✅ 拦住了     {label}")
            print(f"                └ {e}")
        except sqlite3.OperationalError as e:
            broken.append((label, sql, str(e)))
            print(f"  ⚠ SQL 写错了  {label}")
            print(f"                └ {e}")

    print()
    print("─" * 60)
    print(f"  拦住 {n_ok} 条    漏掉 {len(gaps)} 条    写错 {len(broken)} 条")

    if gaps:
        print("\n★ 这几条库没挡住 —— 它们是【有效发现】,要么补约束,要么换个方式兜:")
        for label, sql in gaps:
            print(f"\n    {label}\n        {sql}")
        print("\n  ※ 有些东西 SQLite 的声明式约束【本来就挡不住】")
        print("    (比如\"一张表里的数字,必须等于另一张表里的行数\")——")
        print("     那种要用触发器,或者放在校验脚本里。找到了是好事。")

    if broken:
        print("\n⚠ 这几条 SQL 没写对(不是发现,是笔误):")
        for label, sql, err in broken:
            print(f"    {label}: {err}")


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    run()
