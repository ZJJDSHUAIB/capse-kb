# -*- coding: utf-8 -*-
r"""
同一个图,换 LangGraph 当执行器 —— 节点函数【一个都不改】。

═══ 这一步要证明什么 ═══
    ★ 上一步把流程抽成了【节点 + 边】,而那是【框架无关的】。
    ★★ 所以换执行器,应该【只改"怎么跑",不改"做什么"】。
        这个文件【继承 图智能体】,只覆盖 _建图() 一个方法 ——
        七个节点函数一行没动。
    ★★★ 而那正是选型的自由:要零依赖用我写的,要持久化/并行/中断换 LangGraph。

═══ 对照:三个版本跑同一段对话 ═══
        智能体          手写 if（原始那版）
        图智能体        我写的 40 行执行器
        LG智能体        LangGraph（这个文件）
    ★ 三个该跑出【一样的结构】。不一样就是搬错了。

═══ ⚠ 而它同时让我们看见【LangGraph 多给了什么】═══
    那三样,我们那个 40 行执行器【做不到】:
      ① Checkpointer —— 每步存一份状态快照,能恢复、能时间旅行
      ② 并行 —— 多个分支同时跑
      ③ 中断 —— 跑到一半停下等人(比如"要不要批准这一步")
    ★ 而它们【都是执行器的事】—— 加它们不用动那七个节点。
"""
import sys, io
from pathlib import Path
from typing import TypedDict, Any

sys.path.insert(0, str(Path(__file__).parent))

from langgraph.graph import StateGraph, START, END
from agent_graph import 图智能体


#  ══════════════════════════════════════════════════════════════════
#  State:一个 TypedDict
#  ★ 而这份清单本身有价值 —— 它逼你说清【这个流程到底用了哪些东西】。
#    在 agent.py 里那些是【散落的局部变量】,没人列过。
#  ⚠ total=False:不是每一步都会填满所有字段 —— 比如"反问"那条路没有"重做过"。
# ══════════════════════════════════════════════════════════════════
class 状态(TypedDict, total=False):
    问: str                    #  用户这一句
    参照: Any                  #  ★ 这一轮开始时的参照期次(全程用它,不让它被中途改)
    结果: dict                 #  每个工具交出了什么
    选中: list                 #  模型选了哪些工具
    期次: Any                  #  ★ 记忆补完之后的参数
    机场: Any
    指标: Any
    说明: list                 #  ★ 补了什么、为什么 —— 给人看的
    反问: Any                  #  非空 = 要反问
    补过: bool                 #  记忆补过参数
    补做过: bool               #  ④ 那一步做过
    继承的动作: list            #  上一轮的动作
    大模型补的: Any             #  指代解析给的东西(过了校验才留)
    重做过: bool
    结局: str                  #  "答" / "反问"


class LG智能体(图智能体):
    """★ 只覆盖 _建图 —— 节点函数【全部继承】。那正是"换执行器"的意思。"""

    def _建图(self):
        g = StateGraph(状态)
        #  ★ 节点:和 graph.py 那版【一模一样的那七个函数】
        g.add_node("起", self._起)
        g.add_node("记忆", self._记忆)
        g.add_node("大模型", self._大模型)
        g.add_node("补做", self._补做)
        g.add_node("重做", self._重做)
        g.add_node("筛", self._筛)
        g.add_node("完", self._完)

        g.add_edge(START, "起")
        g.add_edge("起", "记忆")
        #  ★ 条件边一:规则判不出(要反问)→ 去问大模型;否则直接走补做
        g.add_conditional_edges(
            "记忆",
            lambda s: "去大模型" if s["反问"] else "去补做",
            {"去大模型": "大模型", "去补做": "补做"})
        #  ★ 条件边二:大模型也没补出来(或它说 clarify)→ 直接收尾(那是反问)
        g.add_conditional_edges(
            "大模型",
            lambda s: "补出来了我" if s["补过"] else "它也不好",
            {"补出来了我": "补做", "它也不好": "完"})
        g.add_edge("补做", "重做")
        g.add_edge("重做", "筛")
        g.add_edge("筛", "完")
        g.add_edge("完", END)
        return g.compile()

    def 问(self, q):
        """跑一遍 LangGraph 的图 —— 收尾和 图智能体 一样。"""
        s = self.图.invoke({"问": q})
        if s["结局"] == "反问":
            记录 = {"问": q, "结局": "反问", "反问": s["反问"]}
        else:
            记录 = {"问": q, "结局": "答", "选中": s["选中"], "结果": s["结果"],
                    "参数": (s["期次"], s["机场"], s["指标"]),
                    "说明": s["说明"], "重做过": s.get("重做过", False)}
        self._内.历史.append(记录)
        return 记录


# ══════════════════════════════════════════════════════════════════
#  三版对照
#  ★ 比【结构】,不比生成的文本 —— 后者每次都不同
# ══════════════════════════════════════════════════════════════════
对话 = [
    "2025Q3 上海浦东国际机场综合得分是多少",
    "那合肥新桥呢",
    "那 2024Q2 的得分呢",
    "2025Q4 的样本量是多少",
    "那上海呢",
    "2025Q4 报告里,测评指标为什么调整过",
]

键 = ("结局", "反问", "参数", "选中", "说明", "重做过")


def _剁(a):
    """★ 反问只比【第一行】—— 括号里那句是大模型写的,措辞每次都不同。"""
    return None if a is None else str(a).split("\n")[0]


def _取快照(r):
    return {"结局": r["结局"], "反问": _剁(r.get("反问")), "参数": r.get("参数"),
            "选中": r.get("选中"), "说明": r.get("说明"),
            "重做过": r.get("重做过")}


def main():
    import sqlite3
    from paths import DB
    from agent import 智能体
    from agent_graph import 图智能体
    from agent_langgraph import LG智能体

    con = sqlite3.connect(DB)
    甲 = 智能体(con)
    乙 = 图智能体(con)
    丙 = LG智能体(con)

    print("=" * 78)
    print("  三版对照:手写 if ／ 我写的执行器 ／ LangGraph")
    print("=" * 78)

    同 = [0, 0]
    for i, q in enumerate(对话, 1):
        a = _取快照(甲.问(q))
        b = _取快照(乙.问(q))
        c = _取快照(丙.问(q))
        b同 = (a == b)
        c同 = (a == c)
        同[0] += b同
        同[1] += c同
        print(f"\n  [{i}] {q}")
        print(f"       手写    :{a['结局']:<4} 参数={a['参数']}")
        print(f"       我的图  :{b['结局']:<4} 参数={b['参数']}   {'✅ 一样' if b同 else '❌ 不一样'}")
        print(f"       LangGraph:{c['结局']:<3} 参数={c['参数']}   {'✅ 一样' if c同 else '❌ 不一样'}")
        if not b同:
            print(f"       ⚠ 我的图 和手写版差在:{ {k:(a[k],b[k]) for k in a if a[k]!=b[k]} }")
        if not c同:
            print(f"       ⚠ LangGraph 和手写版差在:{ {k:(a[k],c[k]) for k in a if a[k]!=c[k]} }")

    n = len(对话)
    print("\n" + "=" * 78)
    print(f"  我写的执行器  {同[0]}/{n} 一样")
    print(f"  LangGraph     {同[1]}/{n} 一样")
    print("=" * 78)
    print("""
  ★ 三个版本【同一批节点函数】,换的只是执行器 ——
    而我写的那个只有 40 行,它跑的 LangGraph 拉了 18 个包。
  ★★ 那 18 个包买到的是什么?—— 我写的那个【做不到】的三样:
       Checkpointer   每步存一份快照,能恢复、能时间旅行
       并行           多个分支同时跑
       中断           跑到一半停下等人
     ★★★ 而它们【都是执行器的事】—— 加它们【不用动那七个节点】。
          那正是"抽出来"这件事的意义。
""")


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    main()
