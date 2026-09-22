# -*- coding: utf-8 -*-
r"""临时探针:证明「开关关着时,合并那条路一次都不会被走到」。

★ 为什么用"让它一被调用就炸"这种土办法,而不是"我看代码知道它不会走":
   这个项目一路的规矩是**别相信推理,去量**。
   "那个分支不会被执行"是推理;把它换成一个会炸的函数,是量。
   炸不了 = 那行代码在关着的时候是死的,系统的行为【和改之前一模一样】。

★ 探针拿【系统实际用的那个调用方式】问(和 score_eval.query_all 同一套),
  不是我自己另写一句更简单的 —— 那样问出来的"没炸"不算数。
"""
import sys, io, sqlite3
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


def boom(*a, **k):
    raise AssertionError("★ 开关关着,search_merged 却被调用了 —— 改前没守住!")


import build_search
import ask
from route import load_airports, load_indicators

# 把它换成一个一调用就炸的东西。注意【两个地方都要换】:
#   build_search.search_merged  —— 万一有人从模块里现取
#   ask.search_merged           —— ask.py 写的是 `from build_search import ...`,
#                                  它手里握着的是【自己命名空间里的那个名字】。
# ★ 我只换前一个的话,后一个还是老函数 —— 探针会【假通过】。
#   同一个东西有两个身份,而没有任何地方记着它有两个身份。这在项目里是第三次。
build_search.search_merged = boom
ask.search_merged = boom
ask.USE_MERGE = False

con = sqlite3.connect(ask.DB)
ap, ind = load_airports(con), load_indicators(con)

# 故意挑【一条检索路 + 一条 SQL 路】:只测一条路的话,
# "另一条路本来就不会调它"会被误读成"开关守住了"。
QS = ("2024Q2的著作权声明说了什么",                        # 走检索
      "上海浦东国际机场2025Q4的综合得分是多少")             # 走 SQL


def run(expect_fire):
    """expect_fire: 期望【哪几道】会响(下标集合)。

    ⚠ 期望不能写成"全响"或"全不响" —— 走 SQL 的那道题【无论开关开没开】
      都不该碰检索,所以它永远不响。把它算进"期望响",会误判成探针坏了;
      算进"期望不响"又掩盖不了什么。**期望必须逐题给。**
    """
    ok = True
    for i, q in enumerate(QS):
        want = i in expect_fire
        try:
            o = ask.ask(con, q, ap, ind)
            fired, tail = False, f"去向={o.get('去向')}"
        except AssertionError:
            fired, tail = True, "★ 探针响了"
        good = fired == want
        ok &= good
        print(f"    {'✅' if good else '✗'} 问「{q[:18]}…」→ {tail:<22}"
              f" (期望{'响' if want else '不响'})")
    return ok


# ── 第一遍:开关关着 —— 应该【一次都不响】 ──
ask.USE_MERGE = False
print(f"① 开关 USE_MERGE = {ask.USE_MERGE}   ← 现在应该【全程不响】")
if not run(expect_fire=set()):
    print("  ✗ 不该响却响了"); sys.exit(1)

# ── 第二遍:开关打开 —— 走检索的那道应该【响】 ──
# ★★ 这一遍才是关键。项目规矩:「故意改坏,看掉多少」——
#    一个永远不会响的探针,和"检查根本没跑"长得一模一样,证明不了任何事。
#    步骤①说"没响",只有在步骤②证明"它响得起来"之后,才有意义。
ask.USE_MERGE = True
print(f"\n② 开关 USE_MERGE = {ask.USE_MERGE}   ← 反向验证:走检索的那道应该【响】")
if not run(expect_fire={0}):
    print("  ✗ 探针是死的(打开开关也不响)—— 步骤①的结论【作废】"); sys.exit(1)

print("\n★ 结论:探针是活的(开着会响、关着不响)→")
print("  开关关着时,合并检索【一次都没被走到】—— 改前守住了。")
