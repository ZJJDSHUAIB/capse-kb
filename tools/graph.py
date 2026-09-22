# -*- coding: utf-8 -*-
r"""
最小的状态图 —— 把 agent.py 里那串手写的 if,换成【节点 + 边】。

═══ 为什么自己写,不用 LangGraph ═══
    ★ 量过代价:LangGraph 会拉 18 个包,其中 langchain-core 是个新的大框架,
      langsmith 还会【把运行数据上报到云端】。
      ★★ 而这个项目一路的取舍是「少一个依赖,别人就少一步装包」——
         requirements.txt 里那句注释写了;而这里处理的是【报告原文】,
         "数据出不出本机"不是小事。
    ★★★ 所以我们先自己写一遍最小的 —— 那样才知道框架到底替我们做了什么。
         **不知道那个,用框架就只是照文档抄一遍。**

═══ 它是什么(三个概念,定义先说清)═══
    **State(状态)**  一个字典,在节点之间传。
                     谁要用的东西,谁从这个字典里拿。
    **Node(节点)**   一个函数:`state -> 要更新的那部分`。
                     它【不修改】传进来的 state,只返回自己改动的部分。
    **Edge(边)**     一个函数:`state -> 下一个节点的名字`(None = 结束)。
                     ★ 它可以是【条件边】—— 按 state 里的东西走不同分支。

    ★ 就这三样。不多。
    ★★ 而这个实现只有下面那个 `图` 类那么长 —— 因为【核心就是这些】。

═══ ⚠ 它【不】做什么(和 LangGraph 的差距,要写清)═══
    · 它不持久化 —— 状态只在内存里跑一遍,跑完就没了。
      ★ LangGraph 的 Checkpointer 干的是这个。我们【还没做】。
    · 它不并行 —— 节点一个一个跑。LangGraph 支持并行分支。
    · 它不许中途暂停 —— 不能"跑到一半等人审批"。
      ★ 而那三样,恰恰是"用框架"能拿到的东西 —— **知道差在哪,才叫选型。**
"""
import sys, io
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


class 图:
    """最小的状态图执行器。

    ★ 用它的方式:
        图 = 图("起点")
        图.加节点("起点", 函数)          #  函数: state -> dict(要更新的部分)
        图.加边("起点", lambda s: "下一个")   #  返回 None 表示结束
        结果 = 图.跑({"问": "..."})
    """

    def __init__(self, 起点):
        self.起点 = 起点
        self.节点 = {}
        self.边 = {}
        self.轨迹 = []          #  ★ 走了哪些节点 —— 留给人看

    def 加节点(self, 名字, 函数):
        self.节点[名字] = 函数
        return self

    def 加边(self, 名字, 函数):
        """函数: state -> 下一个节点的名字,或 None。"""
        self.边[名字] = 函数
        return self

    def 跑(self, state):
        """从起点开始,一直走到没有下一个为止。返回最终 state。"""
        cur = self.起点
        self.轨迹 = []
        #  ⚠ 上限保护:边写错了会死循环 —— 而那正是"没有上限的循环"那个老教训。
        for _ in range(50):
            if cur is None:
                break
            self.轨迹.append(cur)
            state = {**state, **self.节点[cur](state)}
            cur = self.边.get(cur, lambda s: None)(state)
        else:
            raise RuntimeError(f"图跑了 50 步还没停 —— 边多半写错了。轨迹:{self.轨迹}")
        return state


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    print("=" * 78)
    print("  最小状态图 自检 —— 三个概念各跑一遍")
    print("=" * 78)

    #  ★ 用例一:直线。三个节点一条边到底。
    图1 = 图("加")
    图1.加节点("加", lambda s: {"数": s["数"] + 1})
    图1.加节点("乘", lambda s: {"数": s["数"] * 10})
    图1.加边("加", lambda s: "乘")
    图1.加边("乘", lambda s: None)
    出 = 图1.跑({"数": 1})
    print(f"\n  ① 直线:1 → 加 → 乘 → {出['数']}   轨迹={图1.轨迹}")
    print("     ★ 状态在节点之间传下来了(加完是 2,乘完是 20)")

    #  ★ 用例二:条件边。同一个图,按 state 走不同分支。
    图2 = 图("判")
    图2.加节点("判", lambda s: {})
    图2.加节点("走甲", lambda s: {"结果": "走了甲"})
    图2.加节点("走乙", lambda s: {"结果": "走了乙"})
    图2.加边("判", lambda s: "走甲" if s["数"] > 0 else "走乙")
    图2.加边("走甲", lambda s: None)
    图2.加边("走乙", lambda s: None)
    for n in (5, -5):
        出 = 图2.跑({"数": n})
        print(f"\n  ② 条件边:数={n:>3} → {出['结果']}   轨迹={图2.轨迹}")
    print("     ★ 边是个函数 —— 按 state 里的东西决定去哪。那就是「条件边」。")

    #  ★ 用例三:【边写错了会怎样】—— 上限保护真的会响
    图3 = 图("转")
    图3.加节点("转", lambda s: {"数": s["数"] + 1})
    图3.加边("转", lambda s: "转")        #  ★ 自己指自己 = 死循环
    try:
        图3.跑({"数": 0})
        print("\n  ③ 死循环:❌ 居然没拦住")
    except RuntimeError as e:
        print(f"\n  ③ 死循环:✅ 被拦住了 —— {e}")

    print("""
  ★ 三个概念就这些:State(字典)/ Node(函数)/ Edge(条件路由)。
  ⚠ 而这个实现【不持久化、不并行、不能中途暂停】——
    那三样是框架能给的,也正是我们【知道自己没要什么】的地方。""")
