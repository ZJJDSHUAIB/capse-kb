# -*- coding: utf-8 -*-
r"""
同一个问答服务,换 FastAPI —— 和 serve.py 并存,当【对照】。

═══ ★★★ 为什么并存,不是替换 ═══
    这个项目一路的规矩:「换一个做法,就【留一个旧的当对照】」。
    ★ serve.py 那个版本有自己的价值 —— 它零依赖,clone 下来直接能跑。
      那个取舍写在 requirements.txt 开头,不该被一个框架抹掉。
    → 所以两个都留:
         serve.py      标准库 http.server   零依赖
         serve_api.py  FastAPI              换来四样东西(见下)

═══ ★★★ 换来的到底是什么(不是"更时髦的写法") ═══
    ① 请求校验
       serve.py  : json.loads(self.rfile.read(n) or b"{}").get("q", "")
                   ★ 前端要是传了 {"question": "..."} —— 你拿到【空字符串】,
                     然后系统去查一个空问题,【不报错】。
       serve_api: 写一行 `q: str` —— 传错直接 422,并告诉你错在哪。
    ② 异步
       serve.py  : 调 DeepSeek 是同步的,发出去就干等 1.6 秒,这个线程什么都干不了。
       serve_api: 用 asyncio.to_thread 把那段同步代码挪到线程池 ——
                  等的时候事件循环能去接别的请求。
       ⚠⚠ 而这里有个【陷阱】,见下面 _问一句() 那段注释:
          async def 里【直接】放同步阻塞代码,比不加 async 还坏。
    ③ 自动 API 文档
       serve.py  : 没有。想看接口长什么样,得读代码。
       serve_api: 起服务后访问 /docs,一张【能点着试】的接口文档,白送。
    ④ 每会话独立
       serve.py  : 全服务器【一个】智能体 —— 两个用户的对话会串在同一条记忆里。
                   ★ 而那个全局锁【把这个毛病盖住了】:它让请求排队,
                     于是没人发现"大家共用一段记忆"。
       serve_api: 每个 会话id 一套智能体 + 一个 sqlite 连接。
       ★★★ 这就是那道"锁要不要拆"的答案:
             【拆锁的正确方式不是"不要锁",是"把共享的东西变成不共享的"。】

═══ ⚠ 为什么这一版【不做流式输出】 ═══
    流式输出要成立,前提是【有一条正在生成的文本流】。
    ★ 而这个项目的答案【主要不是模型一个字一个字生成的】——
      它是代码从库里查出来拼好的(见 ask.py)。没有那条流,就没有东西可流。
    ⚠ 硬做一个"假装在流式"的接口,正是这个项目一路在防的东西。
    ★★ 哪里才该做:报告生成那两节(report_gen.py / report_conclude.py)——
       那里的正文是模型现场写的,那才有一条真的流。
    → 所以:如实说"这里不做,因为不适合",而不是做一个假的。

═══ 怎么用 ═══
    pip install -r requirements-api.txt
    python tools/serve_api.py                → http://127.0.0.1:8000/docs
    python tools/serve_api.py --串行          → ★ 对照:退回"一个智能体 + 一把锁"
    python tools/serve_api.py --port 8080
"""
import sys, io, sqlite3, argparse, asyncio, threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from paths import DB

from fastapi import FastAPI
from pydantic import BaseModel, Field


#  ══════════════════════════════════════════════════════════════════
#  ① 请求的形状 —— 这一块是 serve.py 里【手写】的那一段
#
#  【对比一下就知道差在哪】
#      serve.py  : q = json.loads(...).get("q", "")
#                  ★ 传错了不报错,拿到空串往下走
#      这里      : 传错了 FastAPI 直接 422,并指出哪个字段错
#
#  ★ 而 Field(...) 里的 description 不是装饰 —— 它会出现在 /docs 那张文档上。
#    也就是说:【校验规则和接口文档是同一份东西】,不会各写一遍然后对不上。
# ══════════════════════════════════════════════════════════════════
class 提问(BaseModel):
    q: str = Field(..., min_length=1, max_length=500,
                   description="用户问的那句话。比如:2025Q4 上海浦东国际机场综合得分是多少")
    会话id: str = Field("默认", max_length=64,
                        description="哪一段会话。★ 同一个 id 的多次提问会共用上下文")


class 答复(BaseModel):
    """★ 返回的形状。

    ═══ ⚠⚠⚠ 2026-09-26 实测踩到的坑:response_model 会【悄悄丢掉】没列的字段 ═══
        【怎么发现的】
            接口返回 结局=答、格式正常 —— ★ 而【记忆补过后的】和【工具实际收到】
            两栏【不见了】,没有任何提示。
        【根因】
            这是我的 bug:上面写了 response_model=答复,而 答复 里【没列那两个字段】——
            ★★ FastAPI 按模型过滤返回值,没列的字段【直接扔掉】。
        【★★★ 而这正是这个项目一路在打的:静默失败】
            接口 200 · 格式正常 · 数据也对 —— 只是少了两栏,而没人看得出来。
            (我在这个文件里警告了两种静默,然后自己造了第三种。)
        【怎么办 —— 两条路,选一条】
            甲 把字段列全(现在这样):★ 换来的是【接口文档上有类型】,值得
            乙 去掉 response_model   :★ 换来的是"不会漏",但文档就只剩一张空壳
        【★ 所以规矩是:用 response_model 就必须维护它 ——
          它是【声明】,而声明和实现对不上时,它不会报错,它会沉默地裁掉。】
    """
    结局: str = Field(..., description="答 / 反问 / 答不出")
    问: str
    会话id: str
    反问: str | None = Field(None, description="结局=反问时,它要问你的那句话")
    说明: list = Field([], description="记忆补了什么、判据报了什么 —— ★ 给人看的")
    选中: list = Field([], description="模型挑了哪些工具")
    工具: list = Field([], description="每个工具交出了什么、把握是什么")
    提示: list = Field([], description="系统级提示(前提对不上 等)")
    记忆补过后的: dict | None = Field(
        None, description="★ 记忆补完之后的参数(含【借来的】)—— 也就是「该用谁」")
    工具实际收到: dict | None = Field(
        None, description="★★ 干活那个工具【真的收到】什么(工具自己报的)—— "
                          "它可能和上面那栏不一样（比如问「样本量」那种不分机场的量）")
    重做过: bool = Field(False, description="记忆补了参数,所以干活那一步重跑过")
    会话模式: str = Field("", description="★ 存盘版还是内存版 —— 降级了要说出来")


#  ══════════════════════════════════════════════════════════════════
#  ② 会话表 —— 每个 会话id 一套(智能体 + 连接)
#
#  【为什么不是全局一个】
#      serve.py 里 _智能体 是全局的 —— ★ 于是两个用户的对话会串在一条记忆里。
#      而那个 _锁 让请求排队,【把这个毛病盖住了】:
#      一次只有一个人在问,所以"共用一段记忆"从来没暴露出来。
#      ★★ 这就是"锁"最坏的地方:它不只是慢,它还【让一个设计错误看不见】。
#
#  【为什么连接也要一会话一个】
#      asyncio.to_thread 把活派给【线程池】—— 不同会话可能落在不同线程上。
#      而 sqlite 的连接【不能跨线程并发用】(除非串行,而那正是我们要去掉的)。
#      ★ 所以:每个会话一个连接,各自只在自己那条线上跑。
#        不是"加锁让它安全",是"让它根本不需要锁"。
# ══════════════════════════════════════════════════════════════════
class 会话表:
    def __init__(self, 串行=False):
        self._表 = {}
        self._表锁 = threading.Lock()
        self._串行 = 串行
        self._全局锁 = threading.Lock()      # ★ 只在 --串行 时用(做对照)
        self._全局智能体 = None

    def _造一个(self, con):
        """优先用【能存盘】的那版(和 serve.py 同一个取舍,见那边的注释)。"""
        try:
            import sqlite3 as _s
            from langgraph.checkpoint.sqlite import SqliteSaver
            from agent_langgraph import LG智能体
            #  ⚠ check_same_thread=False —— 这个连接会被线程池里的线程用
            saver = SqliteSaver(_s.connect(
                Path(DB).parent / "会话存档_api.db", check_same_thread=False))
            return LG智能体(con, saver=saver, thread_id="api")
        except ImportError:
            from agent import 智能体
            return 智能体(con)

    def 拿(self, 会话id):
        """取这一段会话的智能体。★ 没有就造一个 —— 顺带给它一条自己的连接。"""
        if self._串行:
            #  ★ 对照版:全局一个智能体 + 一把锁 —— 和 serve.py 的行为对齐
            with self._表锁:
                if self._全局智能体 is None:
                    con = sqlite3.connect(DB, check_same_thread=False)
                    self._全局智能体 = self._造一个(con)
            return self._全局智能体, self._全局锁

        with self._表锁:
            if 会话id not in self._表:
                con = sqlite3.connect(DB, check_same_thread=False)
                #  ★ 这一段会话自己的锁 —— 同一段会话里仍要串行(记忆是有状态的),
                #    但【不同会话之间不再互相等】。
                智能体 = self._造一个(con)
                #  ⚠ thread_id 要分开,否则 langgraph 的存档会串
                if hasattr(智能体, "thread_id"):
                    智能体.thread_id = 会话id
                #  ⚠⚠ 2026-09-26 实测踩到的坑:这里【必须】是 threading.Lock,
                #    不是 asyncio.Lock。
                #    【为什么 —— 我第一版写的就是 asyncio.Lock,当场报错】
                #        TypeError: 'Lock' object does not support the context manager protocol
                #    ★ 根因:活是 asyncio.to_thread 派到【线程池】里干的,
                #      锁由那个【工作线程】持有 —— 而 asyncio 的原语
                #      【只能在事件循环那个线程里用】,还得配 async with。
                #    ★★ 所以:哪一层在干活,就用哪一层的锁。
                #       这里是线程在干活 → threading.Lock。
                #    ★★★ 而这个错【没有静默】:它被接口那层接住,
                #        原样显示成「反问 —— ⚠ 这一步没跑成:TypeError…」。
                #        那正是这个项目一路在要的:出了错要说出来。
                self._表[会话id] = (智能体, threading.Lock())
            return self._表[会话id]


_会话 = None
_会话模式 = ""
_不挪线程池 = False      # ★ 只给 --不挪线程池 用,平时 False


#  ══════════════════════════════════════════════════════════════════
#  ③ 干活 —— 按 serve.py 的形状把结果翻成页面/前端能读的
# ══════════════════════════════════════════════════════════════════
def _可读(v):
    if v is None:
        return ""
    if not isinstance(v, list):
        return str(v)[:600]
    return [str(x.get("文本") or x.get("chunk_id") or x)[:600]
            if isinstance(x, dict) else str(x)[:600] for x in v]


def _翻(r, q, 会话id):
    """把 智能体.问() 的结果翻成接口的形状。★ 和 serve.py 里那份【同一套规矩】。"""
    if r["结局"] == "反问":
        return {"结局": "反问", "问": q, "会话id": 会话id, "反问": r["反问"],
                "会话模式": _会话模式}
    if r["结局"] == "答不出":
        return {"结局": "答不出", "问": q, "会话id": 会话id,
                "说明": r["说明"], "选中": r["选中"], "会话模式": _会话模式}

    期次, 机场, 指标 = r["参数"]
    工具 = [{"名字": 名, "把握": v.get("把握", ""), "怎么定的": v.get("怎么定的", ""),
             "来源": v.get("来源") or [], "值": _可读(v.get("值"))}
            for 名, v in r["结果"].items() if not 名.startswith("★")]
    提示 = [v.get("值") for k, v in r["结果"].items() if k.startswith("★")]
    return {"结局": "答", "问": q, "会话id": 会话id,
            "选中": r["选中"], "工具": 工具, "提示": 提示,
            "记忆补过后的": {"期次": 期次, "机场": 机场, "指标": 指标},
            "工具实际收到": r.get("实际用的"),
            "说明": r["说明"], "重做过": r.get("重做过", False),
            "会话模式": _会话模式}


def _问一句(q, 会话id):
    """★ 同步的干活函数 —— 它【故意是同步的】。理由见下面接口那段。"""
    智能体, 锁 = _会话.拿(会话id)
    with 锁:
        return _翻(智能体.问(q), q, 会话id)


#  ══════════════════════════════════════════════════════════════════
#  ④ 接口
# ══════════════════════════════════════════════════════════════════
app = FastAPI(
    title="CAPSE 问答 Agent",
    description=("把 9 份民航满意度报告做成一问就答的 Agent。\n\n"
                 "★ 而它不只给答案 —— 它把【怎么走到那个答案的】一起给你:\n"
                 "选了哪些工具、参数从哪来、补了什么、判据报了什么。"),
    version="1.0",
)


@app.get("/", include_in_schema=False)
def 首页():
    return {"去": "/docs", "说明": "★ 接口文档在那儿,能直接点着试"}


@app.post("/api/ask", response_model=答复, summary="问一句")
async def ask(请求: 提问):
    """问一句,拿到答案【以及它怎么走到那个答案的】。

    ═══ ★★★ 为什么这里是 async,而干活那个函数是同步的 ═══
        【⚠⚠ 一个很容易踩的坑】
            async def 里【直接】调同步的阻塞代码 —— 事件循环会被卡住,
            结果比"不加 async"还坏:加了 async 却还是一次只能服务一个请求,
            而且【看起来像是做了异步】。
        【★ 正确做法】
            asyncio.to_thread(...) —— 把那一段同步代码挪到线程池去跑,
            事件循环在它等 DeepSeek 的那 1.6 秒里,可以去接别的请求。
        【为什么不用 httpx.AsyncClient 真异步】
            那要把 llm.py 整条链改成 async —— 而它被另外十几个文件共用。
            ★ 改一处的成本,和"把整个项目变成异步"的成本,不是一回事。
            to_thread 是【一行换到收益】;真异步是【重构换到收益】。
            ⚠ 如实说:这一版是后者没做。
    """
    try:
        #  ═══ ★★★ 就是这一个词,而它是这一版全部的秘密 ═══
        #      有 to_thread → 那段阻塞的活儿被挪到【线程池】,事件循环空出来接下一个
        #      没 to_thread → 事件循环被【卡住】,下一个请求只能等
        #  【★ 加了个开关,专门用来【改坏对照】】
        #      --不挪线程池  → 退回"直接在事件循环里跑那段同步代码"
        #      ★ 而这个项目一路最狠的一招就是「故意改坏,看掉多少」——
        #        掉不动 = 那个机制是死的;掉得动 = 它真的在起作用。
        #      ⚠ 而这一个开关的价值【不在"证明它有用"】——
        #        那太显然了。★ 它的价值在【量出幅度】:4 个并发差多少秒。
        #        幅度才是信息,"有用"不是。
        if _不挪线程池:
            return _问一句(请求.q, 请求.会话id)
        return await asyncio.to_thread(_问一句, 请求.q, 请求.会话id)
    except Exception as e:
        #  ★ 出错要说出来,不是悄悄不出结果 —— 见 serve.py 那段注释
        return {"结局": "反问", "问": 请求.q, "会话id": 请求.会话id,
                "反问": f"⚠ 这一步没跑成:{type(e).__name__}: {e}"}


@app.get("/api/health", summary="它还活着吗")
def health():
    return {"活着": True, "会话模式": _会话模式,
            "串行": _会话._串行 if _会话 else None}


def main():
    global _会话, _会话模式
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--串行", action="store_true",
                    help="★ 对照:退回全局一个智能体 + 一把锁(和 serve.py 行为对齐)")
    ap.add_argument("--不挪线程池", action="store_true",
                    help="★★ 改坏对照:把 asyncio.to_thread 去掉 —— 让阻塞的活儿【卡住事件循环】")
    a = ap.parse_args()

    global _不挪线程池
    _不挪线程池 = a.不挪线程池
    _会话 = 会话表(串行=a.串行)
    con = sqlite3.connect(DB, check_same_thread=False)
    _会话模式 = ("★ 会话会存盘" if _有langgraph() else
                 "⚠ 内存版:关掉就没了。想存盘:pip install -r requirements-langgraph.txt")

    print(f"★ 接口文档  http://127.0.0.1:{a.port}/docs")
    print(f"★ 模式      {'串行(对照)' if a.串行 else '每会话独立'}"
          f"{'  ★★ 不挪线程池(改坏对照)' if a.不挪线程池 else ''}")
    print(f"★ {_会话模式}")

    import uvicorn
    #  ⚠ 不用 reload=True —— Windows 上它会开子进程,而我们的会话表在内存里,
    #    子进程一重载就没了。
    uvicorn.run(app, host="127.0.0.1", port=a.port, log_level="warning")


def _有langgraph():
    try:
        import langgraph  # noqa: F401
        return True
    except ImportError:
        return False


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    main()
