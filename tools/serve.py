# -*- coding: utf-8 -*-
r"""
能点开看的那个页面 —— 把【它怎么走到那个答案的】摊出来。

═══ 为什么是这个形态,而不是"聊天界面" ═══
    ★ 一个普通聊天界面只显示【答案】—— 而那恰好是这个项目一路在防的东西:
      用户看不到系统怎么想的。
    ★★ 所以这个页面显示的是中间那几栏:
         〔它选了〕   模型挑了哪些工具
         〔实际用的〕  记忆补过之后的参数
         〔补了什么〕  「借了上一轮的机场」「沿用了上一轮的动作」
         〔工具结果〕  每个工具交出什么、把握是什么
         〔判据〕     前提对不上、歧义、工具答不了 …
    ★★★ 那些【命令行里本来就打出来了】(chat.py),只是没人看得见。

═══ ⚠ 为什么不用 Streamlit / Gradio ═══
    这个项目一路的取舍是「少一个依赖,别人就少一步装包」(见 requirements.txt 的注释)。
    ★ 一个页面【不值得】把那个优势抹掉。
    ★★ 所以:标准库 http.server + 一段内嵌的 HTML,零依赖。

═══ 怎么用 ═══
    python tools/serve.py              然后打开 http://localhost:8000
    python tools/serve.py --port 8080

⚠ 没有 .env(大模型 key)时:SQL 和关键词检索那部分【照常能跑】,
  需要大模型的那几步会失败 —— ★ 而失败会【显示在页面上】,不是悄悄不出结果。
"""
import sys, io, json, sqlite3, argparse, threading, webbrowser
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).parent))
from paths import DB, PROCESSED

_锁 = threading.Lock()
_智能体 = None
_con = None
_会话模式 = ""          #  ★ 给页面看的那一句话:这次是存盘还是内存


#  ══════════════════════════════════════════════════════════════════
#  ★★★ 2026-09-23:优先用【能存盘】的那一版
#
#  【为什么优先它】
#      chat.py 上写着"问过的会话记在内存里 —— 关掉就没了"。
#      ★ 而那是个真缺口:用户问了浦东、关掉页面、明天再问「那合肥呢」—— 接不住。
#
#  【装不了 langgraph 怎么办 —— 退回内存版】
#      而那【必须报出来】(见下面那句 会话模式)。
#      ★ 因为"能跑,只是不存盘"和"能跑,而且存盘"【在页面上长得一样】——
#        不写出来,那就是一次静默降级。
#      ★★ 而这个项目一路在治的就是这个:机制可以降级,但要出声。
#  ══════════════════════════════════════════════════════════════════
会话存档 = PROCESSED / "会话存档.db"


def _建智能体(con):
    """返回 (智能体, 给页面看的一句话)。★ 那一句话是【必须】的。"""
    try:
        import sqlite3 as _s
        from langgraph.checkpoint.sqlite import SqliteSaver
        from agent_langgraph import LG智能体
        #  ⚠ check_same_thread=False —— 服务是多线程的,而 sqlite 默认不许跨线程
        saver = SqliteSaver(_s.connect(会话存档, check_same_thread=False))
        return (LG智能体(con, saver=saver, thread_id="网页"),
                "★ 会话会存盘 —— 关掉页面再打开,还能接着问上一句的话题")
    except ImportError:
        from agent import 智能体
        return (智能体(con),
                "⚠ 内存版:关掉页面,会话就没了。"
                "想让它存盘:pip install -r requirements-langgraph.txt")


# ══════════════════════════════════════════════════════════════════
#  后端:一句话进去,一个"过程"出来
# ══════════════════════════════════════════════════════════════════
def 问(q):
    """把 智能体.问() 的结果转成【页面能显示的形状】。"""
    global _智能体, _con, _会话模式
    with _锁:
        if _智能体 is None:
            _con = sqlite3.connect(DB, check_same_thread=False)
            _智能体, _会话模式 = _建智能体(_con)
        r = _智能体.问(q)

    if r["结局"] == "反问":
        return {"结局": "反问", "反问": r["反问"], "问": q,
                "会话模式": _会话模式}
    #  ★★★ 2026-09-23:以前这里没有这一支 —— 于是【Web 页面上会显示"答了"而底下是空的】。
    #    判断本来就有(在 chat.py 的展示层里),但它只覆盖终端那一条路。
    #    ★★ 现在结局由 agent.py 统一判,这里只是【读它】。
    if r["结局"] == "答不出":
        return {"结局": "答不出", "问": q, "说明": r["说明"],
                "选中": r["选中"], "会话模式": _会话模式}

    期次, 机场, 指标 = r["参数"]
    工具 = []
    for 名, v in r["结果"].items():
        if 名.startswith("★"):
            continue                     # 那是系统级的提示,下面单独放
        工具.append({
            "名字": 名,
            "把握": v.get("把握", ""),
            "怎么定的": v.get("怎么定的", ""),
            "来源": v.get("来源") or [],
            "值": _可读(v.get("值")),
        })
    #  ★ 系统级的那几条(前提对不上 等)单独列 —— 它们是【越出工具之外】的
    提示 = [v.get("值") for k, v in r["结果"].items() if k.startswith("★")]

    return {"结局": "答", "问": q,
            "选中": r["选中"], "工具": 工具, "提示": 提示,
            #  ⚠⚠ 2026-09-24 修:这里原来把【该用谁】当"实际用的"发出去 ——
            #    而它是【记忆补过之后的参数】,含【借来的】。
            #    ★ 问「2025Q4 的样本量是多少」时,它显示"机场=浦东",
            #      而查表【实际收到的】是 机场=None —— 那一栏在骗人。
            #    ★★ 所以两个都发,页面上分开显示:
            #       该用谁   = 记忆补过之后的(含借来的)
            #       实际收到 = 干活那个工具【自己报的】(唯一准的来源)
            "记忆补过后的": {"期次": 期次, "机场": 机场, "指标": 指标},
            "工具实际收到": r.get("实际用的"),
            "说明": r["说明"], "重做过": r.get("重做过", False),
            "会话模式": _会话模式}


def _可读(v):
    """值可能很长(原文),截一下 —— 页面不是给人读全文的地方。"""
    if v is None:
        return ""
    if not isinstance(v, list):
        return str(v)[:600]
    出 = []
    for x in v:
        if isinstance(x, dict):
            出.append(str(x.get("文本") or x.get("chunk_id") or x)[:600])
        else:
            出.append(str(x)[:600])
    return 出


# ══════════════════════════════════════════════════════════════════
#  页面 —— 内嵌,不额外文件
#  ★ 为什么内嵌:一个 clone 下来就能跑的东西,不该依赖静态文件路径。
# ══════════════════════════════════════════════════════════════════
页面 = r"""<!doctype html><html lang="zh"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>CAPSE 问答 —— 以及它怎么走到那个答案</title>
<style>
 :root{--fg:#1a1a1a;--dim:#6b6b6b;--line:#e3e3e3;--bg:#fafafa;--hi:#0b6b3a;--warn:#8a4b00}
 *{box-sizing:border-box}
 body{margin:0;background:var(--bg);color:var(--fg);
      font:15px/1.7 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif}
 .wrap{max-width:860px;margin:0 auto;padding:28px 20px 80px}
 h1{font-size:19px;margin:0 0 4px}
 .sub{color:var(--dim);font-size:13px;margin-bottom:22px}
 .row{display:flex;gap:8px;margin-bottom:20px}
 input{flex:1;padding:11px 13px;border:1px solid var(--line);border-radius:8px;font:inherit}
 button{padding:11px 18px;border:0;border-radius:8px;background:var(--fg);color:#fff;
        font:inherit;cursor:pointer}
 button:disabled{opacity:.4;cursor:default}
 .card{background:#fff;border:1px solid var(--line);border-radius:10px;
       padding:16px 18px;margin-bottom:14px}
 .ans{font-size:16px;white-space:pre-wrap}
 .k{color:var(--dim);font-size:12px;letter-spacing:.04em;margin-bottom:6px}
 .sel{display:flex;gap:6px;flex-wrap:wrap}
 .tag{background:#eef4f0;color:var(--hi);padding:2px 9px;border-radius:20px;font-size:13px}
 .tag.warn{background:#fdf3e6;color:var(--warn)}
 ul{margin:6px 0 0;padding-left:18px}
 li{margin:3px 0}
 .tool{border-top:1px dashed var(--line);padding-top:12px;margin-top:12px}
 .val{background:#f6f6f6;border-radius:6px;padding:9px 11px;margin-top:7px;
      font-size:13px;white-space:pre-wrap;max-height:200px;overflow:auto}
 .hint{background:#fdf3e6;color:var(--warn);border-radius:8px;padding:11px 13px;
       white-space:pre-wrap;font-size:14px}
 .err{color:#a11}
 small{color:var(--dim)}
</style>
<div class="wrap">
 <h1>CAPSE 问答</h1>
 <div class="sub">★ 这个页面不只显示答案 —— 它显示【它怎么走到那个答案的】。
  中间那几栏才是重点:它选了哪些工具、参数从哪来、补了什么、判据报了什么。</div>
 <div id="mode" class="sub" style="margin:-14px 0 16px"></div>
 <div class="row">
  <input id="q" placeholder="比如:2025Q4 上海浦东国际机场综合得分是多少" autofocus>
  <button id="go">问</button>
 </div>
 <div id="out"></div>
</div>
<script>
const $=(s)=>document.querySelector(s);
let 历史=[];
async function 问(){
  const q=$('#q').value.trim(); if(!q) return;
  $('#go').disabled=true; $('#go').textContent='…';
  try{
    const r=await fetch('/api/ask',{method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({q})});
    const d=await r.json();
    if(d.会话模式 && !$('#mode').textContent){
      $('#mode').textContent = d.会话模式;
      $('#mode').style.color = d.会话模式.startsWith('⚠') ? '#8a4b00' : '#0b6b3a';
    }
    历史.push(d); 渲染();
  }catch(e){ $('#out').insertAdjacentHTML('afterbegin',
      '<div class="card err">出错了:'+e+'</div>'); }
  $('#go').disabled=false; $('#go').textContent='问';
  $('#q').value='';
}
function 渲染(){
  const d=历史[历史.length-1];
  let h='<div class="card"><div class="k">你问</div><div class="ans">'
        +esc(d.问)+'</div></div>';
  if(d.结局==='反问'){
    h+='<div class="card"><div class="k">★ 它反问,而不是猜</div>'
      +'<div class="hint">'+esc(d.反问)+'</div></div>';
  }else if(d.结局==='答不出'){
    //  ★★★ 2026-09-23:以前没有这一支 —— 页面上会显示"答了"而底下是空的。
    //    ★ 那正是这个项目一路在防的【静默】:用户看不出来系统没答上。
    h+='<div class="card"><div class="k">⚠ 这一轮没答上来</div>'
      +'<div class="hint">它选了干活那一步,而那一步没拿到东西。'
      +'下面是它的原话 ——</div>'
      +'<div class="sel">'+(d.选中||[]).map(x=>'<span class="tag">'+esc(x)+'</span>').join('')+'</div>'
      +'<div class="hint" style="margin-top:10px">'
      +(d.说明||[]).map(x=>'· '+esc(x)).join('<br>')+'</div></div>';
  }else{
    h+='<div class="card">';
    h+='<div class="k">它选了</div><div class="sel">'
      +(d.选中.length?d.选中.map(x=>'<span class="tag">'+esc(x)+'</span>').join('')
        :'<small>（一个都没选）</small>')+'</div>';
    const p=d.记忆补过后的||{};
    h+='<div class="k" style="margin-top:14px">★ 记忆补过之后的（该用谁）'+(d.重做过?'　★ 重做过':'')+'</div>';
    h+='<div class="sel">'
      + (p.期次&&p.期次.length?'<span class="tag">期次 '+esc(p.期次.join(','))+'</span>':'')
      + (p.机场?'<span class="tag">机场 '+esc(p.机场)+'</span>':'')
      + (p.指标?'<span class="tag">指标 '+esc(p.指标)+'</span>':'')
      + '</div>';
    //  ★★★ 2026-09-24 加:【工具真的收到了什么】单独一栏。
    //    为什么:上面那一栏是"该用谁"(记忆补过之后的,含借来的),
    //    ★ 而"工具真的收到了什么"可能不一样 —— 比如问"样本量"那种不分机场的量,
    //      上面显示"机场=浦东",而下面才是"机场=None"。
    //    ★★ 两栏分开之后,【用户能看出"这一轮其实没用那个机场"】——
    //       而那正是这个页面存在的意义:把过程摊开。
    if(d.工具实际收到){
      const a=d.工具实际收到;
      h+='<div class="k" style="margin-top:14px">★ 干活那个工具【真的收到】什么（工具自己报的）</div>';
      h+='<div class="sel">'
        + '<span class="tag warn">'+esc(a.哪个工具||'')+'</span>'
        + (a.期次&&a.期次.length?'<span class="tag">期次 '+esc(a.期次.join(','))+'</span>':'')
        + '<span class="tag">机场 '+esc(a.机场===null||a.机场===undefined?'（没用它）':a.机场)+'</span>'
        + '<span class="tag">指标 '+esc(a.指标===null||a.指标===undefined?'（没用它）':a.指标)+'</span>'
        + '</div>';
    }
    if(d.说明&&d.说明.length){
      h+='<div class="k" style="margin-top:14px">★ 记忆补了什么</div><ul>';
      d.说明.forEach(x=>h+='<li>'+esc(x)+'</li>'); h+='</ul>';
    }
    d.工具.forEach(t=>{
      h+='<div class="tool"><div class="k">〔'+esc(t.名字)+'〕把握='
        +esc(t.把握)+'</div><small>'+esc(t.怎么定的)+'</small>';
      if(t.来源&&t.来源.length)
        h+='<div class="val">来源:'+esc(t.来源.join(' / '))+'</div>';
      const v=Array.isArray(t.值)?t.值.join('\n\n'):t.值;
      if(v) h+='<div class="val">'+esc(v)+'</div>';
      h+='</div>';
    });
    h+='</div>';
    if(d.提示&&d.提示.length)
      d.提示.forEach(x=>h+='<div class="card"><div class="k">★ 判据报的</div>'
        +'<div class="hint">'+esc(x)+'</div></div>');
  }
  $('#out').innerHTML=h+$('#out').innerHTML;
}
function esc(s){return String(s).replace(/[&<>"]/g,
    c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));}
$('#go').onclick=问;
$('#q').onkeydown=e=>{if(e.key==='Enter')问();};
</script></html>"""


class 处理(BaseHTTPRequestHandler):
    def _发(self, code, body, ctype="text/html; charset=utf-8"):
        b = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if urlparse(self.path).path in ("/", "/index.html"):
            self._发(200, 页面)
        else:
            self._发(404, "没有这个页面")

    def do_POST(self):
        if urlparse(self.path).path != "/api/ask":
            self._发(404, "没有这个接口")
            return
        #  ⚠⚠ 2026-09-23 实测踩到:`q` 必须先在这里初始化。
        #     第一版把 `q = ...` 写在 try 里,而 except 里【用了 q】——
        #     于是解析失败时,except 自己又抛 UnboundLocalError,
        #     ★ 把【原来那个错给盖住了】。终端上只看到一个莫名其妙的
        #       "cannot access local variable 'q'",而真正的原因没人知道。
        #     ★★ 又是这个项目一路在打的:**一个错误把另一个错误遮住**。
        q = ""
        try:
            n = int(self.headers.get("Content-Length") or 0)
            q = json.loads(self.rfile.read(n) or b"{}").get("q", "")
            结果 = 问(q)
        except Exception as e:
            #  ★ 出错【要显示在页面上】,不是悄悄不出结果 ——
            #    那正是这个项目一路在防的"静默"
            结果 = {"结局": "反问", "问": q,
                    "反问": f"⚠ 这一步没跑成:{type(e).__name__}: {e}"}
        self._发(200, json.dumps(结果, ensure_ascii=False),
                 "application/json; charset=utf-8")

    def log_message(self, *a):
        pass                              # 别把终端刷满


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--no-open", action="store_true", help="不自动开浏览器")
    a = ap.parse_args()
    print(f"★ 打开 http://localhost:{a.port}")
    print("  (Ctrl+C 结束。★ 问过的会话记在内存里 —— 关掉就没了。)")
    if not a.no_open:
        threading.Timer(0.6, lambda: webbrowser.open(f"http://localhost:{a.port}")).start()
    HTTPServer(("127.0.0.1", a.port), 处理).serve_forever()


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    main()
