# -*- coding: utf-8 -*-
r"""
验收:【关掉再打开】还能接住上文吗?—— 而这件事【只有跨进程才算数】。

═══ 为什么必须跨进程 ═══
    ★ "会话记在内存里,关掉就没了" —— 那句里的"关掉"指的是【进程结束】。
    ★★ 所以在同一个进程里跑两次 invoke,【证明不了】任何事 ——
       那是 InMemorySaver 都能做到的。
    ★★★ 要验的是:进程 A 存下来 → 进程 B 读得到。
        那才是 serve.py 重启、或者用户关了页面明天再来 —— 那件事。

═══ 怎么跑 ═══
    python tools/agent_persist_test.py
    它自己起两个子进程,一个存、一个读。
"""
import sys, io, os, json, sqlite3, subprocess, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from paths import DB, PROCESSED

#  ★ 存的库放在 processed 下 —— 和别的派生物一起,而且 .gitignore 已经挡了 *.db
存档 = PROCESSED / "会话存档.db"


def _跑(阶段, 问句):
    """在【一个子进程】里跑一句。★ 每个阶段一个进程 —— 那才是"关掉再打开"。"""
    脚本 = r'''
import sys, sqlite3
sys.path.insert(0, r"{tools}")
from paths import DB
from langgraph.checkpoint.sqlite import SqliteSaver
from agent_langgraph import LG智能体

con = sqlite3.connect(DB)
with SqliteSaver.from_conn_string(r"{存档}") as saver:
    a = LG智能体(con, saver=saver, thread_id="张三")
    r = a.问(r"{问句}")
    print("__结果__" + repr({{
        "结局": r["结局"],
        "参数": list(r["参数"]),
        "说明": r.get("说明") or [],
        "反问": (r.get("反问") or "")[:80],
    }}))
'''.format(tools=str(Path(__file__).parent), 存档=str(存档), 问句=问句)
    r = subprocess.run([sys.executable, "-c", 脚本],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace",
                       env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    for 行 in (r.stdout or "").split("\n"):
        if 行.startswith("__结果__"):
            return eval(行[len("__结果__"):])
    return {"崩了": (r.stderr or "")[-400:]}


def main():
    if 存档.exists():
        存档.unlink()          #  ★ 从零开始 —— 不然读到的是上次的
    print("=" * 78)
    print("  跨进程验收:进程 A 存 → 进程 B 读")
    print("=" * 78)

    甲 = _跑("存", "2025Q3 上海浦东国际机场综合得分是多少")
    print(f"\n  进程 A(第一次打开)问「2025Q3 上海浦东…综合得分」")
    print(f"      → {甲.get('结局')}  参数={甲.get('参数')}")

    乙 = _跑("读", "那合肥新桥呢")
    print(f"\n  ── 进程 A 结束。进程 B(关掉再打开)──")
    print(f"  进程 B 问「那合肥新桥呢」—— ★ 它没点名期次")
    print(f"      → {乙.get('结局')}  参数={乙.get('参数')}")
    print(f"      说明:{乙.get('说明')}")

    print("\n" + "=" * 78)
    接住了 = bool(乙.get("参数") and 乙["参数"][0])
    if 接住了:
        print(f"  ★ 接住了 —— 进程 B 拿到了进程 A 留下的期次 {乙['参数'][0]}")
        print("  ★★ 而那是【跨进程】的:两个子进程,各跑各的,中间没有共享内存。")
    else:
        print("  ❌ 没接住 —— 进程 B 拿不到进程 A 的记忆")
    print("=" * 78)
    print(f"""
  ⚠ 而它存的地方:{存档.name}(在 data/processed/ 下,是派生物)
     ★ 想清掉:"删掉那个文件" —— 会话就没了。而那正是"存档"该有的样子。

  ★★ 对照:另外两个执行器(手写 / 我写的图)【做不到这件事】——
     它们的记忆活在进程里。★ 而那正是那 18 个包买到的东西之一。""")


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    main()
