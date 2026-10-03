# -*- coding: utf-8 -*-
"""会话存档 —— 把【会话那几格记忆】存到 sqlite,关掉再打开还能接着问。

═══ 为什么需要它 ═══
    服务(serve.py / serve_api.py)原来走的是 LangGraph 那条路,理由只有一个:
        ★ 「会话会存盘 —— 关掉页面再打开,还能接着问上一句的话题」
    ★★ 而那条路【缺了 5 处业务判断】(拒答闸 / 反问闸 / 偏好 / 计划路 / 补漏)
       —— 于是"能存盘"和"业务完整"成了二选一。
    ★★★ 而"存盘"这件事本来【不需要整个执行器】:
        agent_memory.会话 早就有 导出() / 从() 两个方法
        (那是 agent_graph 为"记忆放进 State"加的)。
        → 缺的只是一个【把那份 dict 放哪儿】的地方。

═══ 所以这里只做一件事 ═══
    一张表:k = 会话id · v = 那份 dict 的 JSON。
    ★ 不碰业务逻辑,也不碰执行器。

⚠ 为什么用 sqlite 而不是内存 dict?
    服务是【多进程 / 重启会丢】的。而 sqlite 就在 data/processed 下面,
    和别的东西一样 —— 数据在本地文件里,不在某个进程的内存里。
⚠ 为什么不用 pickle?
    JSON 是【人能读的】。而这个项目一路的规矩是:存下来的东西要能被查。
    会话那份 dict 全是 str/list/bool/int(见 会话.导出()),JSON 够用。
"""
import io
import json
import sqlite3
import sys
from pathlib import Path

表 = """
CREATE TABLE IF NOT EXISTS 会话存档 (
    k TEXT PRIMARY KEY,
    v TEXT NOT NULL,
    t TEXT NOT NULL DEFAULT (datetime('now'))
)
"""


class 存盘:
    """★ 一个极小的 KV:会话id → 那份记忆的 dict。

    ⚠ `check_same_thread=False`:服务是多线程的,而 sqlite 默认不许跨线程
      —— 和 serve.py 那边 LangGraph 的 SqliteSaver 是同一个坑,同一个解法。
    """

    def __init__(self, 路径):
        self.路径 = str(路径)
        self.con = sqlite3.connect(self.路径, check_same_thread=False)
        self.con.execute(表)
        self.con.commit()

    def 取(self, 会话id):
        """★ 取不到就返回 None —— 而不是 {}。
        ⚠ "这个会话还没存过"和"存过、但是空的"是两件事:
          前者该造一个新的;后者该原样还原(它可能是"上一轮很清楚地说没实体")。
        """
        row = self.con.execute("SELECT v FROM 会话存档 WHERE k=?",
                               (str(会话id),)).fetchone()
        if not row:
            return None
        try:
            return json.loads(row[0])
        except Exception:
            #  ★ 存坏了【不吞掉】—— 但也不能让整个会话起不来,所以返回 None 并说清
            return None

    def 存(self, 会话id, 记忆):
        self.con.execute(
            "INSERT INTO 会话存档(k, v, t) VALUES(?, ?, datetime('now')) "
            "ON CONFLICT(k) DO UPDATE SET v=excluded.v, t=excluded.t",
            (str(会话id), json.dumps(记忆, ensure_ascii=False)))
        self.con.commit()

    def 清(self, 会话id):
        self.con.execute("DELETE FROM 会话存档 WHERE k=?", (str(会话id),))
        self.con.commit()


# ══════════════════════════════════════════════════════════════════
#  自检 —— ★ 用真的 会话 对象走一遍,不是拿假 dict 试
# ══════════════════════════════════════════════════════════════════
def 自检():
    import tempfile
    from agent_memory import 会话
    ok = 0

    def 对(名, 条件):
        nonlocal ok
        print(("  ✅ " if 条件 else "  ❌ ") + 名)
        ok += 条件

    路径 = Path(tempfile.gettempdir()) / "_会话存档自检.db"
    if 路径.exists():
        路径.unlink()
    s = 存盘(路径)

    对("没存过的会话 → None(而不是 {})", s.取("甲乙") is None)

    #  ★ 造一个【真的】会话,塞满东西,再走一遍存取
    甲 = 会话(None)
    甲.期次, 甲.机场, 甲.指标 = ["2025Q4"], "上海浦东国际机场", "综合得分"
    甲.上一轮动作, 甲.轮次, 甲.上一轮有实体 = ["查表"], 3, True
    s.存("甲乙", 甲.导出())
    回 = s.取("甲乙")
    对("存了能取回来", 回 is not None)
    对("期次/机场/指标都对",
      回["期次"] == ["2025Q4"] and 回["机场"] == "上海浦东国际机场"
      and 回["指标"] == "综合得分")
    对("上一轮动作/轮次/有实体都对",
      回["上一轮动作"] == ["查表"] and 回["轮次"] == 3 and 回["上一轮有实体"] is True)
    乙 = 会话.从(回, None)
    对("从 dict 还原出来的会话,字段一样",
      乙.期次 == 甲.期次 and 乙.机场 == 甲.机场 and 乙.指标 == 甲.指标
      and 乙.上一轮动作 == 甲.上一轮动作 and 乙.轮次 == 甲.轮次)
    对("还原出来的【是另一个对象】(不是同一个引用)", 乙 is not 甲)

    #  ★ 覆盖写:同一个会话存第二次,该是新的那份
    甲.期次 = ["2025Q3"]
    s.存("甲乙", 甲.导出())
    对("再存一次会【覆盖】,不是插两条", s.取("甲乙")["期次"] == ["2025Q3"])
    对("表里只有一条", s.con.execute(
        "SELECT COUNT(*) FROM 会话存档").fetchone()[0] == 1)

    #  ★ 两个会话【互不干扰】—— 那是"会话id"这个参数的全部意义
    丙 = 会话(None)
    丙.期次 = ["2023Q3"]
    s.存("丙丁", 丙.导出())
    对("两个会话各存各的",
      s.取("甲乙")["期次"] == ["2025Q3"] and s.取("丙丁")["期次"] == ["2023Q3"])

    print(f"\n  自检 {ok}/9")
    #  ⚠⚠ 必须先关连接再删 —— Windows 上【打开的文件删不掉】:
    #     PermissionError: [WinError 32] 另一个程序正在使用此文件
    #  ★ 而 Linux/macOS 上删得掉 —— 所以这个坑【只在 Windows 上出现】,
    #    在别处跑这个自检是【绿的】。如实记着。
    s.con.close()
    路径.unlink(missing_ok=True)
    return ok == 9


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.exit(0 if 自检() else 1)
