# -*- coding: utf-8 -*-
r"""
第 14 课 · 所有路径只在这一个文件里算 —— 别的地方一律引用它。

═══ 为什么需要这个文件 ═══
    原来 64 处路径写死在 47 个文件里,长这样:

        DB = Path(r"D:\capse-kb\data\processed\capse.db")

    ★ 它在【作者机器上】永远正确 —— 而这正是它从来没被发现的原因。
    ★★ 别人 clone 下来之后:
         · 路径不存在 → 有的地方直接崩
         · ★★★ 更坏的情况:它【看起来能跑】,因为它连的还是作者那份库
           (实测:在新目录跑 ask.py,它答得出来 —— 而那个库只可能在 D:\capse-kb)

═══ ★★★ 项目根怎么算,以及为什么必须这么算 ═══
    ROOT = Path(__file__).resolve().parent.parent

    ★ 拆开说:
        __file__        这个文件自己的路径(tools/paths.py)
        .resolve()      变成绝对路径(消掉 .. 和软链接)
        .parent         上一级 → tools/
        .parent         再上一级 → 项目根
    ★★ 为什么不用 os.getcwd():
        那是【你从哪个目录敲命令】决定的,不是【代码在哪】决定的。
        你在 D:\ 下敲 python D:\capse-kb\tools\ask.py,cwd 就是 D:\ ——
        路径全错。而 __file__ 永远指向文件自己。
    ★★★ 为什么不用环境变量做默认值:
        那要求每个用的人都先配一次,而"clone 下来就能跑"是这一课的目标。

═══ 一个例外:数据目录可以搬走 ═══
    CAPSE_DATA 这个环境变量能覆盖数据目录的位置。
    ★ 为什么留这个口子:数据(库 + PDF)可能比代码大得多,
      或者放在一个不进版本管理的地方。**但代码根不能用环境变量** ——
      代码在哪是可以算出来的,算得出来就别让人配。
"""
import os
from pathlib import Path

#  ★ 项目根:这个文件在 <根>/tools/paths.py,所以往上两级
ROOT = Path(__file__).resolve().parent.parent

#  数据根。默认 <根>/data,但允许用环境变量指到别处(比如磁盘大的地方)。
DATA = Path(os.environ.get("CAPSE_DATA") or (ROOT / "data")).resolve()

#  processed:从 PDF 抽出来的中间产物 + 库 + 向量文件
PROCESSED = DATA / "processed"

#  文档 / 评估集 / 跑分结果
DOCS = ROOT / "docs"

#  报告输出
OUTPUT = ROOT / "output"

#  最常用的那个:SQLite 库
DB = PROCESSED / "capse.db"


if __name__ == "__main__":
    #  ★ 自检:把这些路径打出来,并且【实测目录在不在】——
    #    "算出来了"和"那个地方真的有东西"是两件事。
    import sys, io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    print("这一份代码算出来的路径:\n")
    for name in ("ROOT", "DATA", "PROCESSED", "DOCS", "OUTPUT", "DB"):
        p = globals()[name]
        #  ★ 只报"在不在",不报大小 —— 一个目录的存在与否就够了
        mark = "✅" if p.exists() else "✗ 不存在"
        print(f"  {name:<10} {str(p):<48} {mark}")
    print(f"\n  (DATA 可以被环境变量 CAPSE_DATA 覆盖 —— 现在"
          f"{'用了' if os.environ.get('CAPSE_DATA') else '没设置'})")
    print("""
  ⚠ 上面打 ✗ 的不是错 —— 比如刚 clone 下来时 capse.db 不在,
     那是对的,它要从 CSV 重建(见 README「从头装起来」那一节)。""")
