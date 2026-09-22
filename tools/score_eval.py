# -*- coding: utf-8 -*-
r"""
第 6 课 · 跑分。

═══ 它和 check_eval.py 的分工 ═══
    check_eval.py  核【评估集自己】—— 你写的标准答案对不对(拿你的出处去库里比)
    score_eval.py  核【系统】—— 拿评估集去问系统,系统答得对不对
    这是两件事。第一件不做,第二件的数字没有意义。

═══ 口径(什么算对)—— 三档分开记 ═══
      去向对   —— 系统知不知道该去哪查(SQL / 检索 / 拒答)
      答案对   —— 查到了正确的东西
      来源齐   —— 答案带出处

    ※ 为什么"拒答"要两个方向分开看:
      第 4 课定过 —— 拒答是最贵的选项,不是最安全的。
      答错用户能核对;拒错用户拿不到数据,而且不会知道。
      "该拒的拒了"和"该答的答了"是两个指标,合并成一个数就把方向盖掉了。

═══ ★ 判"答案对不对"必须分三种结果,不能只有对/错 ═══
      对 / 错 / 【机器判不了】

    ※ 这是第一版最严重的错(实测踩了三次):
      ① 系统答"样本量 205,164 份",我的抽数把千分位逗号切开,抽出 205 和 164
         → 判成"错"。**假的。**
      ② 他问"相差多少",系统答了两个值,差 0.05 不在库里 —— 我没替它算
         → 判成"错"。**假的。** check_eval 里修过,这里忘了同步。
      ③ 叙述题的期望答案是纯文字("机场交通、机场服务与设施…"),没有数字
         → 我判"答案对 = False"。**假的。** 系统其实答对了。

    → 把"我没替它算"和"我算不了"说成"它错了",等于**把我的局限算成系统的错**。
      这和第 3 课的"查不了 ≠ 查了没有"是同一个病。评估脚本自己犯这个病,
      跑出来的分数就没有意义了。
"""
import sys, io, re, sqlite3, json, argparse, hashlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from route import load_airports, load_indicators              # noqa: E402
from ask import ask                                           # noqa: E402
import ask as _ask_mod                                        # noqa: E402  ← 第9课:要改它的 USE_MERGE 开关
from check_eval import (read_rows, answer_numbers, numbers_in,  # noqa: E402
                        explain_missing, EVAL_IN)

DB  = Path(r"D:\capse-kb\data\processed\capse.db")
_CON = None   # 惰性打开的连接,给证据核对用
OUT = Path(r"D:\capse-kb\docs\评估集_跑分.json")


def _chunk_ids(text):
    """从"出处"或"来源"里抓出所有 chunk 编号(2024Q2-P07 这种)。"""
    return set(re.findall(r'\d{4}Q\d-P\d+', str(text or '')))


def _sub_items(ans):
    """把期望答案切成子项 —— 口径②要的就是"能按项算分"。

    ※ 切法是从他【已经写好的数据】里读出来的,不是我另定的规矩:
      ① 他用了 ; 或 ； 的,那就是显式的子项边界(60 道里已有 18 道这么写)。
      ② 没用分号、但逗号分开的段【每段都带数字】的,也当子项。
         (#2「样本量：205164，机场数：41，一级指标数：6，二级指标数：31」就是这种)
      ③ 其余整段算一个子项 —— 【不乱切】。宁可少切,不可切错:
         切错了会产生"部分得分"的假象,比不切更糟。
    """
    a = str(ans or "").strip()
    parts = [p.strip() for p in re.split(r'[;；]', a) if p.strip()]
    if len(parts) <= 1:
        cand = [p.strip() for p in re.split(r'[，,]', a) if p.strip() and re.search(r'\d', p)]
        if len(cand) >= 2:
            parts = cand
    return parts or [a]


# ── 大模型判分(口径①的"基本意思对即可")────────────────────
#
# ※ 它的定位要说清:大模型只判【意思】,不判【证据】。
#   证据有没有命中是硬判的(上面 _chunk_ids 那段),那是这套评估里
#   唯一不依赖第二个模型的地方。全交给大模型 = 让另一个 LLM 决定
#   另一个 LLM 对不对 —— 它判松了,分数就虚高,而且【看不出来】。
_JUDGE_CACHE = Path(r"D:\capse-kb\docs\评估集_判分缓存.json")
_cache = json.loads(_JUDGE_CACHE.read_text(encoding="utf-8")) if _JUDGE_CACHE.exists() else {}

# ── ★ 让缓存自己报数 ──────────────────────
#   为什么非要报这个数(实测踩过):
#   `hash()` 那个 bug 所以能活下去,是因为缓存不出声。
#   文件在、在被写、长度在长 —— 看起来完全正常。
#   如果它一开始就报「命中 0/35」,第一眼就能看出来。
#   → **静默的机制要让它报数。**
_HIT = {"hit": 0, "miss": 0}

# ── ★★ 第 11 课:--no-cache,用来量【判分自己稳不稳】 ──────────
#   为什么不加这个开关就量不出来:
#       缓存键 = (题号, 期望答案, 系统答)。
#       ★ 而"量判分稳不稳"要拿【同一份答案】反复判 —— 键完全一样 →
#         100% 命中缓存 → 读到的"稳定"是【缓存命中】,不是判分给的。
#   ★★ 而且开这个开关时【也不许写缓存】:不然会把随机结果污染进缓存,
#      以后别的实验就会拿这些结果当"判过的"。
_NO_CACHE = False


def llm_judge(row, got_a):
    """返回 {"对":bool,"理由":str},或 None(判分没跑成)。"""
    # ── ★ 缓存键必须用 hashlib,不能用内置 hash() ──────
    #   Python 的 hash() 对字符串每个进程都挂一个随机盐,
    #   所以同一段文本每次跑算出的键都不同 → 缓存永远命中不了。
    #   实测:#46 的系统答案三次逐字相同(md5 f6a21b13),却被判出两种结果。
    #   同一道题在缓存文件里堆了 7 条一模一样的记录。
    #   → 缓存存在、在被写、看起来在工作,但一次都没生效。

    _k = lambda s: hashlib.md5(str(s).encode('utf-8')).hexdigest()[:12]
    key = f"{row['题号']}|{_k(row['期望答案'])}|{_k(got_a)}"
    if not _NO_CACHE and key in _cache:
        _HIT["hit"] += 1
        return _cache[key]
    _HIT["miss"] += 1
    # ══ ★★ 第 11 课:把判据的洞补上 ═══════════════════════════
    #  老提示词有三处没写清,实测会晃(题47 同一个答案判对 4/10 和 6/10):
    #     · "关键事实一致就算一致"  —— 名字对、数字没给,算一致吗?没写
    #     · "数字"两字明明在          —— 那少了数字算不算?没写
    #     · "多说了别的,不算错"      —— ★ 那【少说了】呢?没写
    #  ★ 实测(46/47/48 各判 10 次):
    #      旧:0/10  6/10  0/10     ← 题47 在晃
    #      新:0/10  0/10  0/10     ← 稳定,而且判对了(答案确实漏了 4.25)
    #    ★★ 所以晃的主因是【规则没写清】,不是大模型天生不可靠。
    #
    #  ⚠ 第一版新规则我写的是"标准答案里【每一个】都必须有" —— 补过头了,实测误伤:
    #      题52 标准答案"CASE于2012年正式成立,经过13年发展",
    #      系统答"CASE于2012年正式成立" —— 答全了问题,却因为少一句背景被判错。
    #    ★★ 所以改成【乙】:只把【数字】和【专有名字】当必答项,其余算加分。
    #       理由:"数字和专名"是【客观可核的】,不靠谁去判断"关键不关键"。
    #       而这正是这个项目一路的方向:能核的用能核的,别靠理解。
    prompt = (
        "你在给一个问答系统的答案打分。只判【意思对不对】,不管文采、不管长短。\n\n"
        f"【标准答案】\n{row['期望答案']}\n\n"
        f"【系统回答】\n{got_a[:1500]}\n\n"
        "系统回答的意思和标准答案一致吗?\n"
        "★ 判据(按顺序核对):\n"
        "  1. 标准答案里的【每一个数字】,系统回答里都必须有 —— 少一个就算错。\n"
        "     (只数【数字】。像「经过13年发展」这种带数字的句子,\n"
        "      数字 13 必须有;那句话本身有没有,不算判据。)\n"
        "  2. 标准答案里点名的【每一个专有名字】(机场名 / 指标名 / 机构名),\n"
        "     系统回答里都必须有 —— 少一个就算错。\n"
        "  3. 上面两条【少一点都算错】,那不是「换种说法」,是【漏】。\n"
        "  4. ★ 除了数字和专名,标准答案里【别的话】—— 比如背景说明、\n"
        "     补充形容、结论的展开 —— 系统回答里【没有也不算错】。\n"
        "     只要数字齐、专名齐、意思不反,就算对。\n"
        "只输出一行,格式:对|理由  或  错|理由(理由不超过30字)"
    )
    try:
        from llm import chat
        r = chat(prompt, max_tokens=80).strip()
    except Exception as e:
        print(f"    (大模型判分没跑成: {type(e).__name__}: {e})")
        return None
    ok = r.startswith("对")
    why = r.split("|", 1)[1].strip() if "|" in r else r
    out = {"对": ok, "理由": why}
    if not _NO_CACHE:                       # ★ 见 _NO_CACHE 的注释:不许污染
        _cache[key] = out
    return out


def _con():
    global _CON
    if _CON is None:
        _CON = sqlite3.connect(DB)
    return _CON


def _chunk_text(cid):
    r = _con().execute("SELECT 文本 FROM chunk WHERE chunk_id=?", (cid,)).fetchone()
    return r[0] if r else ""


def evidence_hit(want_c, src_c):
    """期望的那一页,系统命中了吗?返回 (直接命中, 放宽命中对)。

    ★ 为什么要有"放宽"这一档(张君杰质疑题 39 逼出来的):
      他问:"这道题在所有的 pdf 文件里都能查到他就不会了吗?非要指出具体时间?
             这也太不智能了"

      他说的对,而且不止对一道题 —— 我量了 15 道叙述题,其中 9 道
      期望出处那一页【跨期是同一页】(相似度 0.978~1.000)。
      例:#49 期望 2024Q4-P12,而 2023Q3-P12 和它【一字不差】。

      对这些页来说,【期次根本不是区分特征】—— 它是同一段文字。
      要求系统报出准确期次,是我在评估集里过度指定,不是系统答错了。
      这和"机器核不了 ≠ 答案错"是同一类错:把【我的口径太窄】记成【系统的错】。

    ※ 但放宽必须有底线,而且是【量出来的】,不是我拍脑袋:
      同页码、跨期、文本相似度 ≥ 0.95 才算同一页。
      - #40 的 2023Q3-P05 vs 2024Q1-P05 相似度只有 0.309 → 【不放宽】,期次有意义
      - #52 的 2025Q4-P23 别的期根本没有这一页 → 天然严格
      所以评估集里【仍然有真正考期次的题】,放宽没有把这类题一起放过。
    """
    src_c = _chunk_ids(src_c) if isinstance(src_c, str) else src_c
    direct = want_c & src_c
    relaxed = []
    for w in sorted(want_c - direct):
        m = re.match(r'\d{4}Q\d-P(\d+)', w)
        if not m:
            continue
        base = _chunk_text(w)
        if not base:
            continue
        for s in sorted(src_c - direct):
            n = re.match(r'\d{4}Q\d-P(\d+)', s)
            if not n or n.group(1) != m.group(1):
                continue
            import difflib
            if difflib.SequenceMatcher(None, base, _chunk_text(s)).ratio() >= 0.95:
                relaxed.append((w, s))
                break
    return direct, relaxed


def _pkey(p):
    """'2024Q1' → 20241,用来按期次排序比大小。"""
    m = re.match(r'(\d{4})Q(\d)', str(p or ""))
    return int(m.group(1)) * 10 + int(m.group(2)) if m else 0


def multi_version_hit(cite, src_c):
    """出处写成 `chunk=多版本;页码=NN;分界=YYYYQN` 时,系统两边都命中了没?

    ★ 为什么用【显式分界期】,不再用文本相似度自动分组(我踩了两轮才走到这):

      第一轮:答案键钉死 `chunk=2024Q4-P07` → 要求系统猜出出题人心里想的是哪一期。
              张君杰否决:"非要指出具体时间?这也太不智能了" —— 他是对的,那是过度指定。
      第二轮:改成按"文本相似度 ≥0.95 同一版"自动分组 → 第 7 页算出"2 个版本"。
              **这也是假的。** 2023Q3 写二级 30 项、2024Q1~Q4 写 31 项,
              30→31 只差一个字符,被并进了同一组。真实是【三档】。
              → 阈值是我拍的,拍出来的结果把一个真差异吃掉了。
                而且脚本反过来报"你写的 31 在原文里找不到" —— 把我的阈值错记成数据错。
      第三轮(现在):分界期【由出题人写在出处里】,脚本只负责数。
              `chunk=多版本;页码=07;分界=2025Q1` 意思很直白:
              这一页有一道分界,系统必须【两边都命中】,只命中一边 = 不知道存在另一版。

    ★ 为什么这一档必须是【硬判】,不能交给大模型:
      "知不知道存在第二个版本"这件事,要能被打分脚本【直接数出来】。
      让大模型判"它说全了没有",判不准,而且判松了分数虚高、看不出来 ——
      那等于让另一个模型决定这个模型对不对,而项目里唯一不依赖第二个模型的硬判据
      就是证据命中。丢掉它,分数就没有不依赖模型的那一半了。

    ★ 为什么 #39 的分界只判 2025Q1,不判 2024Q1(张君杰定的):
      2024Q1 那次二级指标 30→31,一级指标的名字一个没变 —— 数值微调。
      2025Q1 那次【一级指标的名字换了】(去「行李服务」,加「出港服务」「进港服务」)
      —— 语义变化。**只有语义变化才会让报告生成器把跨年数据比错**,数值微调不会。
      要求系统报出 30→31 是苛求;要求它报出"定义换过"是应该的。

    返回 (命中的边数, 总边数, {"旧": [...期次], "新": [...期次]})。
    """
    s = str(cite or "")
    if "多版本" not in s:
        return None
    pg = re.search(r'页码\s*[=:：]\s*(\d+)', s)
    bd = re.search(r'分界\s*[=:：]\s*(\d{4}Q\d)', s)
    if not pg or not bd:
        # 缺分界期就判不了 —— 【报错,不猜】。猜一个分界,等于替出题人做判断。
        return "缺分界期"
    cut = _pkey(bd.group(1))
    rows = _con().execute("SELECT chunk_id, 期次 FROM chunk WHERE 页码=?",
                          (int(pg.group(1)),)).fetchall()
    if not rows:
        return 0, 2, {"旧": [], "新": []}
    old = sorted({p for _, p in rows if _pkey(p) < cut})
    new = sorted({p for _, p in rows if _pkey(p) >= cut})
    src_c = _chunk_ids(src_c) if isinstance(src_c, str) else src_c
    ids = {c: p for c, p in rows}
    hit_old = any(ids[c] in old for c in src_c if c in ids)
    hit_new = any(ids[c] in new for c in src_c if c in ids)
    return int(hit_old) + int(hit_new), 2, {"旧": old, "新": new}


def cross_period_conflict(want_c, src_c):
    """用户点名了期次,系统却把【说法不一样】的别期内容一起塞进答案 —— 错。

    ★ 这条是张君杰定的,原话:
        "这肯定错啊 剩下的两个回答都不符合日期"
      他一句话把 #42 的病根说准了 —— 比我原来写的准。我原来写的是
      "系统不知道这一页有多个版本",那说的是【机制】;他说的"不符合日期"
      说的是【用户的损失】:我问的是 2024Q2,你给我三段,两段是别的日期的。

    ★ 为什么必须卡一个例外,不能见"别期"就判错:
      第 49/50 题系统也返回了别期(2023Q3-P12 而不是 2024Q4-P12),
      但那两页【一字不差】(相似度 1.000)—— 内容不矛盾,用户没被误导,不算错。
      第 42 题不一样:2025Q2-P07 说 7 项,2024Q2-P07 说 6 项,【互相排斥】。
      → 所以规则精确版是:命中了别的期,【而且那一期跟所问期次说法不一样】才算错。
        分界就是 evidence_hit 用的同一个 0.95 —— 两条规则共用一把尺子。

    ★ 它真正指向的错,是这个:
      系统列了三条来源,格式上像是"我找到三处,都这么说"—— 三重印证。
      实际是【同一页、不同年份、说法互相排斥】。
      **它把"矛盾"包装成了"印证"。** 这比单纯答错更难被发现。

    量过:#42 之前 7 道题有"多捞别期",其中 5 道内容一致(不算错),2 道说法不同
    (题 40、题 42)—— 这条规则没有误伤。

    返回 [(所问的, 多捞的), ...]。
    """
    src_c = _chunk_ids(src_c) if isinstance(src_c, str) else src_c
    out = []
    for w in sorted(want_c):
        m = re.match(r'\d{4}Q\d-P(\d+)', w)
        if not m:
            continue
        base = _chunk_text(w)
        if not base:
            continue
        for s in sorted(src_c - want_c):
            n = re.match(r'\d{4}Q\d-P(\d+)', s)
            if not n or n.group(1) != m.group(1):
                continue
            import difflib
            if difflib.SequenceMatcher(None, base, _chunk_text(s)).ratio() < 0.95:
                out.append((w, s))
    return out


_CON = None


def _con():
    global _CON
    if _CON is None:
        _CON = sqlite3.connect(DB)
    return _CON


def code_judge(row, got_a, src):
    """★★ 第 11 课:能算的题,别问大模型。返回 True(对)/False(错)/None(算不了)。

    ═══ 为什么要有它 ═══
        第 11 课实测:判分在【分档排名】那类题上会晃 ——
           题47 同一个答案,判对 4/10,换一次实验又是 6/10。
        ★ 原因是那类题的答案【有结构】(分数 ↔ 机场的配对),
          而大模型判"说全了没有"时,每次掂量的尺度不一样。

    ═══ 而结构能算 ═══
        parse_table 能把那张表解析出来,于是"第一名有几个"是算得出来的。
        ★★ 而算出来的东西【不抽样】—— 同一份材料,每次给同一个答案。

    ═══ ⚠ 它只覆盖"分档排名"这一类题 ═══
        库里现在 3 道(#46 #47 #48)。其余 57 道没有可解析的结构,还得叫大模型。
        ★ 所以它只能【缩小】判分的噪声,消不掉。
    """
    from ask import check_ranked_answer

    ids = re.findall(r"\d{4}Q\d-P\d+", src or "")
    if not ids:
        return None
    con = _con()
    hits = []
    for c in ids:
        t = con.execute("SELECT 文本 FROM chunk WHERE chunk_id=?", (c,)).fetchone()
        if t:
            hits.append({"chunk_id": c, "文本": t[0]})
    if not hits:
        return None
    res = check_ranked_answer(got_a, str(row.get("问题") or ""), hits)
    if res is None:
        return None                 # 不适用 —— 交给大模型
    return not res                  # [] → True(答全了);[缺的] → False


def judge_one(row, got_a, src):
    """先试代码判;判不了才叫大模型。★ 两条路都返回同一个格式。"""
    c = code_judge(row, got_a, src)
    if c is not None:
        return {"对": c, "理由": "代码判的 —— 从材料里的得分表算出来的,不抽样"}
    return llm_judge(row, got_a)


def judge(row, got):
    """判一道题。got = 系统实际返回的那个 dict(或 from-json 里存下来的)。

    ═══ 张君杰定的评估口径(2026-09-16),三条,逐条落在这里 ═══

    ① 叙述题:"只有数字正确不算完全正确,必须能从检索结果中找到对应证据
               并正确支持答案。" + "基本意思对即可(交给大模型)"
       → 【两个条件都要满足】:证据命中(硬判) 且 意思对(大模型判)。
         只做到一个,不算对。这比"数字对上就行"严 —— 但严得对:
         检索题真正该测的是【有没有找到那段原文】,不是数字。

    ② 复合题:"拆成若干子项,只答对一部分按部分得分,不直接算整题正确。"
       → 分数是 [0,1] 的连续值,不是 0/1。
         #2 答了 4 项里的 2 项 = 0.5,不是 0,也不是 1。

    ③ "0 条检索属于检索失败;主动拒答属于模型在有/无证据条件下选择不回答。"
       → 【三者互不相等】:检索 / 检索·0条 / 拒答。
         期望"拒答"而系统给"检索·0条" = 错 —— 它不是在拒绝回答,
         它是在说"我找了,没有"。那是两回事,用户看到的也是两种东西。
    """
    want_w = (row["期望去向"] or "").strip()
    got_w  = got.get("去向", "?")
    got_a  = got.get("系统答", "") if "系统答" in got else "\n".join(got.get("答案") or [])
    # ※ 两个键名都要认:"系统来源"是旧 JSON 的写法,"来源"是 query_all 存进去的。
    #   第一版只读前者 → 所有叙述题的证据命中都查了个空,15 道全判 0 分。
    #   又是一次"我的脚本错、记在系统账上"。别名读法比"记住用哪个"可靠。
    src    = str(got.get("系统来源") or got.get("来源") or "")
    ok_w   = (got_w == want_w)

    # ── 拒答(口径③:和"检索·0条"不是一回事)────────────────
    if want_w == "拒答":
        if ok_w:
            return {"去向对": True, "得分": 1.0, "说明": ""}
        extra = ""
        if got_w == "检索·0条":
            extra = "(注意:它是【检索 0 条】,不是拒答 —— 它没意识到自己缺这块数据)"
        return {"去向对": False, "得分": 0.0,
                "说明": f"应该拒答,系统却答了({got_w}){extra}"}

    # ── 叙述题(口径①)─────────────────────────────────
    if want_w == "检索":
        if not ok_w:
            return {"去向对": False, "得分": 0.0,
                    "说明": f"应该走检索,系统走了{got_w}"}
        # ①a 证据命中:期望出处那一页必须在系统命中的来源里(硬判,不问大模型)
        mv = multi_version_hit(row["出处"], _chunk_ids(src))
        if mv == "缺分界期":
            return {"去向对": True, "得分": 0.0, "机器判不了": True,
                    "说明": "出处写了『chunk=多版本』但没写『分界=YYYYQN』—— 分界是出题人的判断,脚本不猜"}
        if mv is not None:
            n_hit, n_all, sides = mv
            detail = (f"分界前({'/'.join(sides['旧'])}) | 分界后({'/'.join(sides['新'])})")
            if n_hit < 2:
                return {"去向对": True, "得分": 0.0, "证据": False,
                        "说明": f"★ 系统只命中了分界的一边({n_hit}/2)—— "
                                f"它不知道这一页的定义换过({detail})"}
            why = judge_one(row, got_a, src)
            if why is None:
                return {"去向对": True, "得分": 0.0, "证据": True, "机器判不了": True,
                        "说明": f"分界两边都命中了,但大模型判分没跑成 —— 要人眼看"}
            return {"去向对": True, "得分": 1.0 if why["对"] else 0.0, "证据": True,
                    "说明": ("分界两边都命中。 " if why["对"] else "")
                            + ("" if why["对"] else f"两边都命中,但意思不对:{why['理由']}")}
        want_c = _chunk_ids(row["出处"])
        hit_c, relaxed = evidence_hit(want_c, _chunk_ids(src))
        if want_c and not hit_c and not relaxed:
            return {"去向对": True, "得分": 0.0, "证据": False,
                    "说明": f"★ 检索结果里没有含答案的那一页 {sorted(want_c)}"
                            f"(系统命中:{sorted(_chunk_ids(src))})"}
        note = ""
        if relaxed and not hit_c:
            w, s = relaxed[0]
            note = f"[放宽:{w} 那一页跨期是同一页,系统给的 {s} 内容一致] "
        # ①a′ 张君杰的规则:点名了期次,就不许把【说法不同】的别期内容混进答案。
        #     这是【硬判】,不等大模型 —— 大模型给 #42 的理由是"含7项指标,与标准答案
        #     不一致",那说的是症状;这条说的是病根:不符合用户所问的日期,
        #     而且三段平铺、不标注,把"矛盾"伪装成了"三重印证"。
        conf = cross_period_conflict(want_c, _chunk_ids(src))
        if conf:
            pairs = ";".join(f"你问 {w},它多给了 {s}" for w, s in conf)
            return {"去向对": True, "得分": 0.0, "证据": True, "跨期矛盾": True,
                    "说明": f"★ 答案里混进了不符合所问日期的内容({pairs})—— "
                            f"同一页不同期说法不同,它却三段平铺、不标注,"
                            f"把矛盾当成了印证"}
        # ①b 意思对(大模型判)
        why = judge_one(row, got_a, src)
        if why is None:
            return {"去向对": True, "得分": 0.0, "证据": True, "机器判不了": True,
                    "说明": note + "证据命中了,但大模型判分没跑成 —— 要人眼看"}
        return {"去向对": True, "得分": 1.0 if why["对"] else 0.0, "证据": True,
                "放宽": bool(relaxed),
                "说明": note + ("" if why["对"] else f"证据命中,但意思不对:{why['理由']}")}

    # ── 数值题(口径②:分子项,部分得分)──────────────────
    if got_w != "SQL":
        return {"去向对": False, "得分": 0.0, "说明": f"应该查表,系统走了{got_w}"}
    subs = _sub_items(row["期望答案"])
    have_n = numbers_in(got_a)
    # ※ 用 answer_numbers 而不是 numbers_in:"排名第一"里没有阿拉伯数字,
    #   但它是【一个确定的值 = 1】。用 numbers_in 判"有没有数字"会把 #17 误判成
    #   "机器判不了" —— 又是把我的局限算成系统的账。
    if not any(answer_numbers(s) for s in subs):
        return {"去向对": True, "得分": 0.0, "机器判不了": True,
                "说明": "期望答案里没有可比的数字"}
    # ★ 分母只算【可比的子项】(2026-09-18 修,我自己的 bug)
    #
    #   改之前:分母是 len(subs),但循环里 `if not want_n: continue` 会跳掉
    #   【没有数字的子项】—— 那些项永远拿不到分,却永远占着分母。
    #
    #   后果(实测):#11 的期望答案是
    #       「深圳宝安：4.26；上海浦东：4.22；深圳宝安高」
    #     第三项「深圳宝安高」里没有数字 → 被判分跳过 →
    #     **这道题的满分被压成 2/3 = 0.67,任何系统都到不了 1.0。**
    #
    #   这等于给一批题【装了个够不到的天花板】,而分数看上去完全正常。
    #   和这个项目一路在打的是同一个东西:一个静默的尺子错误。
    subs_ok = [s for s in subs if answer_numbers(s)]
    got_subs, miss_txt = 0, []
    for s in subs_ok:
        want_n = answer_numbers(s)
        miss = want_n - have_n
        if miss:
            still, derived = explain_missing(miss, have_n)
            if still:
                miss_txt.append(f"{s.strip()[:24]} → 缺 {sorted(still)}")
                continue
        got_subs += 1
    score = got_subs / len(subs_ok) if subs_ok else 0.0
    if score == 1.0:
        return {"去向对": True, "得分": 1.0, "说明": ""}
    return {"去向对": True, "得分": score,
            "说明": f"子项答对 {got_subs}/{len(subs)}" + ("; " + "; ".join(miss_txt) if miss_txt else "")}


def query_all(rows):
    con = sqlite3.connect(DB)
    ap, ind = load_airports(con), load_indicators(con)
    out = []
    for r in rows:
        print(f"  问 {r['题号']:>2}: {str(r['问题'])[:50]}")
        try:
            o = ask(con, r["问题"], ap, ind)
            rec = {"去向": o.get("去向", "?"), "系统答": "\n".join(o.get("答案") or []),
                   "来源": o.get("来源") or [], "警告": o.get("警告") or [],
                   "过程": o.get("备注") or []}
        except Exception as e:
            rec = {"去向": "★崩了", "系统答": f"{type(e).__name__}: {e}", "来源": [], "警告": [], "过程": []}
        out.append(rec)
    return out


def report(rows, gots):
    res = [{**r, **g, **judge(r, g)} for r, g in zip(rows, gots)]
    n = len(res)
    w_ok   = sum(r["去向对"] for r in res)
    full   = sum(r["得分"] == 1.0 for r in res)
    unk    = sum(bool(r.get("机器判不了")) for r in res)
    perfect= sum(r["去向对"] and r["得分"] == 1.0 for r in res)
    total  = sum(r["得分"] for r in res)
    # 机器判不了的题不算进平均分的分母 —— 那会把"没判"当成"答错"。
    # 但也【不能】算成满分,那会虚高。两边都不算,单独报。
    scored = [r for r in res if not r.get("机器判不了")]

    print("\n" + "=" * 72)
    print(f"  去向对 {w_ok}/{n}     全对 {full}/{n}     "
          f"机器判不了 {unk}/{n}     两项全对 {perfect}/{n}")
    print(f"  ★ 平均得分(口径②:复合题按子项给分) "
          f"{sum(r['得分'] for r in scored):.3f} / {len(scored)} 道 = "
          f"{sum(r['得分'] for r in scored) / max(1, len(scored)):.1%}")
    print(f"    (分式:把 60 道压成一个数会盖住方向 —— '答了一半'和'全错'不该同分)")

    print("\n  按类别(两项全对 / 总数,及该类平均得分):")
    cat = {}
    for r in res:
        c = cat.setdefault(r["类别"], [0, 0, 0.0, 0])
        c[0] += 1
        c[1] += bool(r["去向对"] and r["得分"] == 1.0)
        c[2] += r["得分"]
        c[3] += bool(r.get("机器判不了"))
    for c, (t, ok, s, u) in cat.items():
        print(f"    {c:<12} 全对 {ok}/{t}   平均 {s / t:.2f}"
              + (f"   (含 {u} 道机器判不了)" if u else ""))

    ref = [r for r in res if r["期望去向"] == "拒答"]
    ans = [r for r in res if r["期望去向"] != "拒答"]
    print(f"\n  ★ 拒答两个方向分开看:")
    print(f"      该拒的 {sum(r['去向对'] for r in ref)}/{len(ref)} 拒对了"
          f"   —— 拒错了比答错更贵:用户拿不到数据,而且不会知道")
    print(f"      该答的 {sum(r['去向对'] for r in ans)}/{len(ans)} 没被误拒"
          f"   —— 拒多了同样是错,拒答不是最安全的选项")
    zero_hit = [r for r in res if r["去向"] == "检索·0条"]
    if zero_hit:
        print(f"      另有 {len(zero_hit)} 道走成了【检索 0 条】(口径③:这不是拒答,是检索失败)"
              f": {[r['题号'] for r in zero_hit]}")

    # ── ★ 指标 8/9:告警率(按路径分层)──────────────────────
    #
    #  口径(张君杰定的):
    #    错误告警率 = 实际答错/答不全的题里,系统发了【警告】的 ÷ 同类题总数
    #    误报率     = 实际答对的题里,系统发了【警告】的 ÷ 同类题总数
    #
    #  ※ 分母不用 60 —— 这个指标测的是「系统犯错后意识到自己错了的概率」,
    #    不是「60 道里有多少道出现警告」。
    #    该拒答的题留在上面『拒答两个方向』里,不混进来。
    #
    #  ※ ★ 为什么必须【按路径分层报】:
    #    整个 ask.py 里只有两处会写警告(判不出 / 检索的 verify),
    #    **SQL 和 拒答两条路【还没有任何检查】** ——
    #    那不是「结构上不可能」,是「那条路上一个检查都没写」。
    #    不分层的话,这两个数会被『SQL 占多少比例』埋掉,改了系统也看不出来:
    #        错误告警率上限只有 5/16 = 31%(11 道 SQL 永远不可能报警)
    #        误报率上限只有 11/44 = 25%
    #    分层之后『检索路径 0/5』一眼可见 —— 那才是『有机制却不用』的证据。
    #
    #  ⚠ 分母的线:<1.0(不满分即计入)。这是【口径】,不是随手取的 ——
    #    换成 <0.5,分母就从 16 掉到 10。线要人定,不能默认。
    def _cnt(rs):
        tot = len(rs)
        got = sum(1 for r in rs if r.get('警告'))
        return got, tot, (got / tot if tot else 0)

    print('\n  ★ 指标 8/9:告警率(按路径分层)—— 系统犯错时,知不知道自己错了')
    # ── ★ 附:仍然静默的清单(张君杰定的)──────────────────────
    #   为什么主指标不够:「错的都该报警」会让【容易报的错】先涨上去,
    #   从而掩盖「最难报的那些还没报」。
    #   例:7 道错题里 5 道容易报 → 5/7 = 71% 看起来很好,
    #      而那 2 道【最贵的】还是静默。
    #   → 主指标说「进步了多少」,这张清单说「还没做到什么」。两个都看。
    for _lab, _grp in (('答错/不全(错误告警率)', [r for r in scored if r['得分'] < 1.0]),
                       ('答对  (误报率)     ', [r for r in scored if r['得分'] == 1.0])):
        _g, _t, _r = _cnt(_grp)
        print(f'      {_lab}  {_g}/{_t} = {_r:.0%}')
        for _p in ('SQL', '检索', '拒答'):
            _sub = [r for r in _grp if str(r['去向']).startswith(_p)]
            if not _sub:
                continue
            _g2, _t2, _r2 = _cnt(_sub)
            print(f'          {_p:<4} {_g2}/{_t2}')
    _silent = [r for r in scored if r['得分'] < 1.0 and not r.get('警告')]
    if _silent:
        print(f'      ★ 仍然静默(答错了、但系统一声不吭):{len(_silent)} 道 '
              f'{[r["题号"] for r in _silent]}')
    print("\n  ★ 没拿满分(去向对,但答案不全):")
    for r in res:
        if r["去向对"] and r["得分"] < 1.0:
            tag = "机器判不了" if r.get("机器判不了") else f"{r['得分']:.2f}"
            print(f"    {r['题号']:>2} [{r['类别']}] 得分 {tag}  {str(r['问题'])[:42]}")
            if r.get("说明"):
                print(f"        {r['说明'][:130]}")
            if r.get("警告"):
                print(f"        警告 {r['警告']}")

    print("\n  ★ 去向判错(不知道该去哪查,或把 0 条检索当成了拒答):")
    for r in res:
        if not r["去向对"]:
            print(f"    {r['题号']:>2} [{r['类别']}] {str(r['问题'])[:42]}")
            print(f"        期望 {r['期望去向']:<4} 实际 {r['去向']:<6} | {r['系统答'][:80]}")
            if r.get("说明"):
                print(f"        {r['说明'][:130]}")

    return res


def main():
    global OUT, _NO_CACHE
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-json", action="store_true",
                    help="不重新问系统,直接拿上次存下来的答案重新判分")
    ap.add_argument("--merge", action="store_true",
                    help="★ 第9课:打开【关键词+向量合并】再跑(规则在 my_merge.py)")
    ap.add_argument("--gen", action="store_true",
                    help="★ 第10课:打开【生成层】再跑 —— 让大模型作答,而不是把材料拼起来")
    ap.add_argument("--retry", action="store_true",
                    help="★ 第12课:打开【重试循环】—— 生成→诊断→做对应的动作(见 ask.gen_with_retry)")
    ap.add_argument("--no-cache", action="store_true",
                    help="★ 第11课:不用判分缓存 —— 量【判分自己稳不稳】时必须加,"
                         "否则同一份答案全命中缓存,读到的稳定是假的")
    ap.add_argument("--tag", default="",
                    help="★ 第9课:给这一轮起个名,结果另存成 评估集_跑分_<tag>.json")
    args = ap.parse_args()

    # ★ 规矩第 ⑧ 条:每轮结果另存带轮次名,不共用固定文件名。
    #   共用会把「这是哪一次跑的」这件事抹掉 —— 而这个项目已经栽过一次。
    if args.tag:
        OUT = OUT.with_name(f"评估集_跑分_{args.tag}.json")

    # ★★ 静默失败守卫:--from-json 是【不重跑】的,它读的是别人已经跑好的答案。
    #   这时候 --merge 开关【碰不到任何东西】—— 它会静静地什么都不做,
    #   而你会在报告里看到一个"用了合并"的分数,其实那是旧的。
    #   项目一路的规矩:沉默的机制要让它出声。
    if args.merge and args.from_json:
        raise SystemExit("  ✗ --merge 和 --from-json 一起用没有意义:\n"
                         "      --from-json 不重跑系统,所以合并开关根本没机会生效,\n"
                         "      你拿到的会是【旧答案 + 新标签】。要么去掉 --from-json。")
    #  ★ 同一个守卫要盖到 --gen —— 理由一模一样。少盖一个,下一次就栽在这。
    if args.gen and args.from_json:
        raise SystemExit("  ✗ --gen 和 --from-json 一起用没有意义:\n"
                         "      --from-json 不重跑系统,生成层根本没机会跑,\n"
                         "      你拿到的会是【旧答案(材料拼接) + 『用了生成层』的标签】。")

    if args.merge:
        _ask_mod.USE_MERGE = True
        print("  ★ 合并检索:开(my_merge.merge_rank 参与排序)")
    else:
        print("  ★ 合并检索:关(只用关键词 —— 第 5 课以来的行为,基准就在这一档)")
    if args.gen:
        _ask_mod.USE_GEN = True
        print("  ★ 生成层:开(大模型作答 + audit 核数字,见 ask.gen_answer)")
    else:
        print("  ★ 生成层:关(答案 = 把取回的原文拼起来 —— 第 5 课以来的行为)")
    if args.retry:
        _ask_mod.USE_RETRY = True
        print("  ★ 重试循环:开(诊断→动作;规则在 ask.RETRY_PLAN)")
    else:
        print("  ★ 重试循环:关(生成一次就完事)")
    if args.no_cache:
        _NO_CACHE = True
        print("  ★ 判分缓存:【关】—— 每次都真判,量判分稳定性时必须这样")
    else:
        print("  ★ 判分缓存:开(命中率会报在末尾)")
    if args.tag:
        print(f"  ★ 轮次标签:{args.tag}  →  {OUT.name}")
    print()

    rows = [r for r in read_rows(EVAL_IN) if r["问题"]]
    if args.from_json:
        gots = json.loads(OUT.read_text(encoding="utf-8"))
        print(f"从 {OUT.name} 读回 {len(gots)} 条系统答案,不重跑。\n")
    else:
        print(f"跑 {len(rows)} 道…\n")
        gots = query_all(rows)
        OUT.write_text(json.dumps(gots, ensure_ascii=False, indent=1), encoding="utf-8")

    res = report(rows, gots)
    OUT.write_text(json.dumps(gots, ensure_ascii=False, indent=1), encoding="utf-8")
    if _cache:
        _JUDGE_CACHE.write_text(json.dumps(_cache, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n  系统原始答案: {OUT}")
    print(f"  大模型判分缓存: {_JUDGE_CACHE.name}({len(_cache)} 条)")
    # ★ 报命中率 —— 让"缓存失灵"这种事自己浮出来
    _tot = _HIT["hit"] + _HIT["miss"]
    if _tot:
        _rate = _HIT["hit"] / _tot
        #  ★ --no-cache 时命中 0 是【应该的】,不是异常 ——
        #    第一版没区分,于是量判分稳定性那三次都打出一句
        #    "太低说明缓存键有问题"的误导提示。
        #    ★ 提示的口径没跟上开关的状态 —— 和那条旧告警是同一个病。
        _note = ("   (缓存是【关】的 —— 命中 0 是应该的)" if _NO_CACHE else
                 "   ← ★ 太低说明缓存键有问题,分数不可比" if _rate == 0 and _tot >= 3 else "")
        print(f"  缓存命中率: {_HIT['hit']}/{_tot} = {_rate:.0%}{_note}")
    else:
        print("  缓存命中率: 这一轮没走判分(全在缓存里,或没有走检索的题)")


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    main()
