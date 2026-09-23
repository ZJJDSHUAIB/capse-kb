# -*- coding: utf-8 -*-
r"""
第 17 课 · 能对话的入口 —— 把智能体接到命令行上。

═══ 为什么需要它 ═══
    到这之前,智能体只能【跑自检脚本】看 —— 那不是对话。
    ★ 而一个能连续问的东西,价值恰恰在【第二句起】:
        「那全年呢」「那合肥呢」「2025Q4 的样本量是多少」
      这几句【单独问都是残的】,只有接着上一句才成立。

═══ ⚠ 它不做什么 ═══
    · 不存盘 —— 退出就没了。要跨会话记东西是另一件事。
    · 不做界面 —— 就是个命令行循环。**能看见它怎么接话,比好看重要。**

═══ 怎么用 ═══
    python tools/chat.py                    # 交互
    python tools/chat.py "第一句" "第二句"   # 给几句直接跑完(方便演示)
"""
import sys, io, sqlite3
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from paths import DB


def 打印(r):
    print()
    if r["结局"] == "反问":
        print(f"  ★ {r['反问']}")
        print()
        return
    #  ★★★ 2026-09-23:「走到那一步」≠「那一步成了」。
    #    以前这里只打一句「结果没查出东西」,而 `结局` 字段还是"答" ——
    #    所以【终端看得见,Web 看不见】。现在结局由 agent.py 统一判。
    if r["结局"] == "答不出":
        print("  ⚠ 这一轮【没答上来】—— 你要的东西那一步没拿到:")
        for x in r["说明"]:
            print(f"    · {x}")
        print()
        return
    期次, 机场, 指标 = r["参数"]
    用了 = "、".join(x for x in (f"期次={期次}" if 期次 else "",
                                f"机场={机场}" if 机场 else "",
                                f"指标={指标}" if 指标 else "") if x) or "（没有参数）"
    print(f"  〔模型选了〕{'、'.join(r['选中']) if r['选中'] else '一个都没选'}")
    print(f"  〔实际用的〕{用了}" + ("      ★ 记忆补过参数,重做过" if r["重做过"] else ""))
    for x in r["说明"]:
        print(f"    · {x}")

    from agent_tools import 干活类
    有答案 = False
    for 名 in 干活类:
        if 名 not in r["结果"]:
            continue
        v = r["结果"][名]["值"]
        if not v:
            continue
        有答案 = True
        print(f"  〔{名}〕")
        for 行 in (v if isinstance(v, list) else [v]):
            print(f"      {str(行)[:200]}")
    if not 有答案:
        print("  〔结果〕没查出东西")
    print()


def main():
    con = sqlite3.connect(DB)
    from agent import 智能体
    a = 智能体(con)

    预设 = sys.argv[1:]
    if 预设:
        for q in 预设:
            print(f"\n{'─' * 74}\n  你:{q}")
            打印(a.问(q))
        return

    print("=" * 74)
    print("  问点东西。★ 试试连着问:先问一个机场,再问「那去年呢」")
    print("  (输入 退出 / q 结束)")
    print("=" * 74)
    while True:
        try:
            q = input("\n你: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not q:
            continue
        if q in ("退出", "q", "exit", "quit"):
            break
        打印(a.问(q))


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    main()
