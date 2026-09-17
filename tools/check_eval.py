# -*- coding: utf-8 -*-
r"""
第 6 课 · 评估集核对脚本。

═══ 它解决什么问题 ═══
    标准答案写错了,整把尺子就废了 —— 而且是【静默地】废。
    你以为系统答错了,跑去改代码,越改越糟。

    防御办法和第 2 课一样:两条独立的路,对得上才算数。
        人:读 PDF → 写标准答案
        脚本:拿你写的【出处】→ 去库里取值 → 得到值
    对不上 → 有一边错了。

═══ 它【不】做什么(这条比上面那条重要) ═══
    它【不判】"你是对是错"。它只是把三样东西并排放在一起:
        你写的标准答案 / 库里算出来的值 / 系统实际答的
    然后让你自己判。

    为什么不能让脚本判:
      ① 脚本错了,你不知道 —— 那就是第 3 课说的"坏了",不是"不够好"
      ② 更根本的:脚本和库是【同一条路】出来的。如果入库时就提错了,
         脚本查出来的"正确值"也是错的,两边一致,一起错。
         → 所以脚本的结论只能当【信号】,不能当【判决】。
         → 真正的独立核对只有一条:人回去翻 PDF。这一步脚本代替不了。

═══ 判据分两档(必须说清楚哪档是硬的) ═══
    数值题  → 【可核】:机器能算,能给出确定的"对得上/对不上"
    叙述题  → 【只摆】:机器把那段原文摆出来,由你眼看。
              机器唯一能硬判的,是"你写的数字在原文里有没有"
    ※ 把"只摆"说成"可核",就是造一个新的静默失败。

═══ 格式上,第一版太严了(2026-09-16 改) ═══
    张君杰填的 10 道,答案 10/10 全对,但 9 道卡在格式上 ——
    他写的是『机场：上海浦东』(全角冒号)、『CAPSE_2024Q2_..._P5』(报告文件名)。
    那不是他写错了,是【我的格式在让他迁就机器】。

    改的原则:
        只要【不产生歧义】,格式就该迁就人。
        一旦会产生歧义(『上海』对得上两个机场),就报错,不许猜。
"""
import sys, io, re, sqlite3, argparse
from pathlib import Path

DB       = Path(r"D:\capse-kb\data\processed\capse.db")
EVAL_IN  = Path(r"D:\capse-kb\docs\评估集.xlsx")
EVAL_OUT = Path(r"D:\capse-kb\docs\评估集_结果.xlsx")

NUM = re.compile(r'\d+(?:\.\d+)?')


def _pkey(p):
    """'2024Q1' → 20241,用来按期次排大小(和 score_eval.py 里那个必须一致)。"""
    m = re.match(r'(\d{4})Q(\d)', str(p or ""))
    return int(m.group(1)) * 10 + int(m.group(2)) if m else 0


def norm_num(s):
    """把数字统一成可比的字符串:'4.20' 和 '4.2' 要算同一个。"""
    return f"{round(float(s), 2):g}"


# ── 千分位逗号不是分隔符,是【数字的一部分】────────────────────
#
# ※ 实测踩过(题 2/3/4/33):系统答"样本量 205,164 份",NUM 把逗号当分隔,
#   抽出 205 和 164 两个数 —— 于是他写的 205164 被判成"系统答里没有"。
#   **假的。** 系统答对了,是我的抽数器把它读错了。
#
# ※ 为什么必须带 (?!\d) 兜底:不问缘由地把逗号全删掉,会把
#   "4.15,4.16"(答案里并排两个数)粘成 "4.154.16" —— 那又造出新的假分歧。
#   逗号后面【恰好三位且再没数字】才算千分位,这是唯一能自证的写法。
_THOUSANDS = re.compile(r'(?<=\d),(?=\d{3}(?!\d))')


def numbers_in(text):
    return {norm_num(m) for m in NUM.findall(_THOUSANDS.sub("", str(text or "")))}


# ── 答案里的数字比"值"更复杂,有两种【不是值】的东西要先剥掉 ──────
#
# ① 期次不是答案里的数,是【指路的坐标】。
#    实测踩过:他写"2023Q3南京禄口国际机场：4.14",我的脚本从中抽出 2023 和 3,
#    报"库里没有 2023" —— 假的。这一版先剥掉 YYYYQN 再抽数。
#
# ② "排名第一" 里没有阿拉伯数字,但它就是一个确定的值 = 1。
#    只在【名次语境】里翻译中文数字("第X名""排名X"),不全文乱翻 ——
#    全文乱翻会把"一共三个原因"翻成 1 和 3,那是新的假警报。
PERIOD_PAT = re.compile(r'\d{4}\s*[Qq]\s*[1-4]')
CN_DIGIT   = {"一": "1", "二": "2", "两": "2", "三": "3", "四": "4",
              "五": "5", "六": "6", "七": "7", "八": "8", "九": "9", "十": "10"}
RANK_CN    = re.compile(r'(?:第|排名)\s*([一二两三四五六七八九十]+)')


def answer_numbers(text, rank=True):
    """rank=False 用在叙述题上。

    ※ 为什么叙述题不能翻中文名次(实测踩过,题 48):
      chunk 是【逐字原文】,里面写的是"4.17 / 4.17 / 无锡硕放 / 宁波栎社",
      不会有阿拉伯数字 1。把答案里的"并列第一"翻成 1 再去原文里找 1 ——
      必然找不到,于是报一个【假的】分歧。
      中文名次只在跟【结构化数据】比的时候才翻译(那边真的会输出"第 1 名")。
    """
    t = PERIOD_PAT.sub(" ", str(text or ""))
    out = numbers_in(t)
    if rank:
        for m in RANK_CN.finditer(t):
            s = m.group(1)
            if len(s) == 1 and s in CN_DIGIT:
                out.add(CN_DIGIT[s])
    return out


def explain_missing(miss, have):
    """★ 派生量:答案里的数【库里没有,但算得出来】。

    ※ 为什么需要这个(实测踩过,题 12/14):
      他写"2024Q2：4.15;2024Q3：4.16;上升0.01"。
      4.15 和 4.16 都查得到,0.01 是【差】—— 库里不存差,存的是两个值。
      第一版报"库里没有 0.01" —— 那是把"我没替它算"说成"他写错了"。
      → 所以这里替它算一遍。算得出来 → 通过;算不出来 → 才报分歧。
    """
    hs = sorted({float(x) for x in have})
    still, derived = set(), {}
    for m in miss:
        mv, hit = float(m), None
        for i in range(len(hs)):
            for j in range(i + 1, len(hs)):
                if abs(abs(hs[j] - hs[i]) - mv) < 1e-9:
                    hit = f"{hs[j]:g} - {hs[i]:g}"
                    break
            if hit:
                break
        (derived.__setitem__(m, hit) if hit else still.add(m))
    return still, derived


# ══════════════════════════════════════════════════════════
#  词汇表:机场名 / 指标名。用来把用户写的短名对上库里的全名。
# ══════════════════════════════════════════════════════════
_AIRPORTS, _INDICATORS = [], []


def load_vocab(con):
    global _AIRPORTS, _INDICATORS
    _AIRPORTS = sorted({r[0] for r in con.execute("SELECT DISTINCT 机场 FROM 综合得分")} |
                       {r[0] for r in con.execute("SELECT DISTINCT 机场 FROM 指标得分")})
    _INDICATORS = sorted({r[0] for r in con.execute("SELECT DISTINCT 指标 FROM 指标得分")})


def resolve_name(kind, name):
    """短名 → 库里的全名。返回 (全名, 提示) 或 (None, 报错)。

    ※ 为什么不做模糊匹配:
      模糊匹配【错的时候你看不出来】—— 那是"坏了"。
      所以只在"库里恰好只有一个名字和它对得上"时才接受,
      而且要把"这里我替你猜了一下"写进结论里,让人看得见。
      『上海』对得上『上海浦东国际机场』和『上海虹桥国际机场』两个 → 报错,不猜。
    """
    pool = _AIRPORTS if kind == "机场" else _INDICATORS
    if name in pool:
        return name, None
    cands = [x for x in pool if x.startswith(name)]
    if len(cands) == 1:
        return cands[0], f"『{name}』库里没有,按唯一前缀匹配到『{cands[0]}』(以后直接写全名更稳)"
    if len(cands) > 1:
        return None, f"『{name}』对上了 {len(cands)} 个,说不准是哪个: {cands} —— 请写全名"
    return None, f"库里没有『{name}』"


# ══════════════════════════════════════════════════════════
#  出处解析 —— 这是整个脚本最脆的地方,所以它【报错】而不是【猜】
# ══════════════════════════════════════════════════════════
CITE_KEYS = {"表", "期次", "机场", "字段", "指标", "取前", "chunk", "页码", "分界"}

# 全角 → 半角。用户手打会用全角冒号,不该因为这个报错。
# 【格式该迁就人,只要不产生歧义】—— 全角冒号和半角等号在这里意思完全一样。
FULL2HALF = str.maketrans("：＝，；｜", ":=,;|")

# 报告文件名 → chunk_id。他写『CAPSE_2024Q2_机场服务测评报告P5』,
# 机器要的是『chunk=2024Q2-P05』。期次和页码都写明了,没有歧义,翻译是安全的。
REPORT_NAME = re.compile(r'(?:CAPSE[_-])?(\d{4}Q\d).*?[Pp]\.?(\d+)')


def parse_cite(s):
    """出处 → ([{...}, ...], 提示 或 报错)。

        表=综合得分;期次=2025Q4;机场=上海浦东国际机场
        表=综合得分;期次=2023Q3;机场=南京禄口国际机场 | 表=综合得分;期次=2025Q2;机场=西安咸阳国际机场
        chunk=2024Q2-P05
        CAPSE_2024Q2_机场服务测评报告P5          ← 也认,自动翻成 chunk=2024Q2-P05

    ※ 为什么解析不了要【报出来】而不是跳过:
      跳过一行 = 那一行的标准答案没人核 = 静默失效。
      宁可显式地挂在"这行我读不懂"上,也不给它一个静默的默认值。
      (和第 4 课的"判不出"是同一个道理。)
    """
    raw = (s or "").strip()
    if not raw:
        return None, None, "出处是空的"
    s = raw.translate(FULL2HALF)

    # 整条就是报告文件名 → 翻译
    if '=' not in s and ':' not in s:
        m = REPORT_NAME.search(s)
        if m:
            cid = f"{m.group(1)}-P{int(m.group(2)):02d}"
            return [{"chunk": cid}], f"『{raw}』按报告名翻成 chunk={cid}(以后直接写 chunk={cid} 更稳)", None
        return None, None, f"这一段读不懂(没有等号或冒号,也不像报告名): {raw!r}"

    clauses, notes = [], []
    for blk in re.split(r'[|\n]', s):
        blk = blk.strip().strip(';')
        if not blk:
            continue
        d = {}
        for part in re.split(r';', blk):
            part = part.strip()
            if not part:
                continue
            mm = re.match(r'^([^=:]+)[=:](.*)$', part)
            if not mm:
                return None, None, f"这一段读不懂(没有等号或冒号): {part!r}"
            k, v = mm.group(1).strip(), mm.group(2).strip()
            if k not in CITE_KEYS:
                return None, None, f"不认识这个键 {k!r}(可用: {'/'.join(sorted(CITE_KEYS))})"
            if k in d:
                # ※ 静默覆盖 = 静默失效。所以这里报错,并且把改法直接给出来。
                fixed = blk.replace(f"，表=", " | 表=").replace(",表=", " | 表=")
                return None, None, (
                    f"这一处里『{k}=』出现了两次 —— 第二次会把第一次覆盖掉。\n"
                    f"        要一次查两处,用 |（竖线）分开,把中间的『，表=』改成『 | 表=』:\n"
                    f"        {fixed}")
            d[k] = v
        if d:
            clauses.append(d)
    if not clauses:
        return None, None, "出处是空的"
    return clauses, "; ".join(notes) or None, None


def lookup_one(con, d, notes):
    """按一处出处去库里取值。返回 (值文本, 错误)。"""
    if "chunk" in d:
        # ── chunk=多版本;页码=NN ─────────────────────────────
        #    ※ 为什么需要这个写法(张君杰的题 39 逼出来的):
        #      他那句问话【没写期次】,而这一页的内容跨期有两个版本
        #      (第 7 页:2023Q3~2024Q4 是"6项/31项",2025Q1~2025Q4 是"7项/28项")。
        #      系统的错不是"挑错了期次",是【它不知道有两个版本】——
        #      它命中的三页全是同一版,所以它给出的答案看起来完全正常。
        #      这正是这个项目一直在打的东西:静默。
        #    → 出处里指名"这一页有多个版本",评估才有东西可判。
        if d["chunk"].strip() == "多版本":
            pg = d.get("页码")
            if not pg:
                return None, "『chunk=多版本』还得写『;页码=07』,不然不知道是哪一页"
            rs = con.execute("SELECT chunk_id,文本 FROM chunk WHERE 页码=? ORDER BY chunk_id",
                             (int(pg),)).fetchall()
            if not rs:
                return None, f"没有第 {pg} 页"
            groups = []                       # 按文本相似度归并成"版本"
            import difflib
            for cid, t in rs:
                for g in groups:
                    if difflib.SequenceMatcher(None, g[0][1], t).ratio() >= 0.95:
                        g.append((cid, t)); break
                else:
                    groups.append([(cid, t)])
            #    ⚠ 这里【每一期的原文都要列出来】,不能只列一个"代表"(踩过两次):
            #      ① 原来写的 [:160] 是为了显示好看,但这段文本同时是【核数字用的原文】,
            #         截掉的部分等于没核。第 7 页版本A 全长 234 字,"31项"落在 160 之后 →
            #         脚本报"你写的数在原文里找不到: ['31']"。假的。
            #         **显示用的文本和核对用的文本不能是同一个变量。**
            #      ② 取消截断之后还是错 —— 因为版本A 的"代表"是 2023Q3(写 30 项),
            #         而组里另外 4 期写的是 31 项。只看代表,31 照样核不出来。
            #         **分组是给人看的便利,核对必须回到每一期的原文。**
            bd = d.get("分界")
            if bd:
                # 出题人写了分界期 → 【按他写的分】,不用相似度猜。
                #   踩过的坑:原来按相似度 ≥0.95 分组,第 7 页 2023Q3(二级30项)
                #   和 2024Q1~Q4(31项)只差一个字符,被并成同一组,
                #   于是脚本反过来报"你写的 31 在原文里找不到" —— 假的。
                #   **分界是出题人的判断,不该由我的阈值代替他判断。**
                cut = _pkey(bd)
                if not cut:
                    return None, f"『分界』要写成 2025Q1 这样,收到的是『{bd}』"
                shards = [("分界前", [(c, t) for c, t in rs if _pkey(c.split('-')[0]) < cut]),
                          ("分界后", [(c, t) for c, t in rs if _pkey(c.split('-')[0]) >= cut])]
                out = [f"第 {pg} 页一共 {len(rs)} 期,按你写的【分界={bd}】分成两段:"]
            else:
                shards = [(f"第 {i} 组", g) for i, g in enumerate(groups, 1)]
                out = [f"第 {pg} 页一共 {len(rs)} 期,按文本相似度≥0.95 分成 {len(groups)} 组:",
                       "  ⚠ 这是脚本【自己猜的】分组,不代表答案的取值只有这么多。",
                       "    要按你定的分界判,请在出处里写『;分界=YYYYQN』。"]
            out.append("  ⚠ 分组是给人看的,核数字请对每一期的原文 —— 组内各期仍可能有小差异。")
            for name, g in shards:
                out.append(f"  · {name}({len(g)} 期):")
                for cid, t in g:
                    out.append(f"    [{cid}] {t}")
            return "\n".join(out), None

        ids = [x.strip() for x in re.split(r'[,]', d["chunk"]) if x.strip()]
        texts = []
        for cid in ids:
            row = con.execute("SELECT 期次,页码,文本 FROM chunk WHERE chunk_id=?", (cid,)).fetchone()
            if not row:
                return None, f"chunk 表里没有 {cid}"
            texts.append(f"[{cid} = {row[0]} 第 {row[1]} 页] {row[2]}")
        return "\n".join(texts), None

    表 = d.get("表")
    if not 表:
        return None, "少了『表=』"

    # ── meta:样本量 / 机场数 / 一级指标数 / 二级指标数 / 口径版本 ──
    if 表 == "meta":
        期次 = d.get("期次")
        ALL = ["样本量", "机场数", "一级指标数", "二级指标数", "口径版本"]
        fields = [f.strip() for f in re.split(r'[,]', d.get("字段", "")) if f.strip()] or ALL
        bad = [f for f in fields if f not in ALL]
        if bad:
            return None, f"meta 表里没有字段 {bad}(可用: {'/'.join(ALL)})"
        row = con.execute(f"SELECT {','.join(fields)} FROM meta WHERE 期次=?", (期次,)).fetchone()
        if not row:
            return None, f"meta 表里没有期次 {期次}"
        return "; ".join(f"{k} {v}" for k, v in zip(fields, row)), None

    # ── 综合得分 / 排名 / 前 N 名 ─────────────────────────
    if 表 == "综合得分":
        期次 = d.get("期次")
        if "取前" in d:
            n = int(d["取前"])
            rows = con.execute("SELECT 机场,得分 FROM 综合得分 WHERE 期次=?"
                               " ORDER BY 得分 DESC LIMIT ?", (期次, n)).fetchall()
            if not rows:
                return None, f"综合得分表里没有期次 {期次}"
            total = con.execute("SELECT COUNT(*) FROM 综合得分 WHERE 期次=?", (期次,)).fetchone()[0]
            return (f"共 {total} 家,前 {n} 名:" +
                    "、".join(f"{i} {a} {b}" for i, (a, b) in enumerate(rows, 1))), None

        机场 = d.get("机场")
        if not 机场:
            return None, ("少了『机场=』。若要问『谁最高』这类不给机场的问题,"
                          "改用『取前=N』,或把『机场=』删掉换一个问法")
        full, note = resolve_name("机场", 机场)
        if note and full:
            notes.append(note)
        if not full:
            return None, note
        if d.get("字段") == "排名":
            row = con.execute("SELECT 排名,本期机场数,得分 FROM 综合得分排名"
                              " WHERE 期次=? AND 机场=?", (期次, full)).fetchone()
            if not row:
                return None, f"查不到 {期次} / {full}"
            return f"第 {row[0]} 名 / 共 {row[1]} 家,得分 {row[2]}", None
        row = con.execute("SELECT 得分 FROM 综合得分 WHERE 期次=? AND 机场=?",
                          (期次, full)).fetchone()
        if not row:
            return None, f"查不到 {期次} / {full}"
        return f"{row[0]}", None

    # ── 指标得分 ─────────────────────────────────────────
    if 表 == "指标得分":
        期次, 机场, 指标 = d.get("期次"), d.get("机场"), d.get("指标")
        if not 指标:
            return None, "少了『指标=』"
        指标, note = resolve_name("指标", 指标)
        if note and 指标:
            notes.append(note)
        if not 指标:
            return None, note
        if 机场:
            机场, note = resolve_name("机场", 机场)
            if note and 机场:
                notes.append(note)
            if not 机场:
                return None, note
            row = con.execute("SELECT 得分 FROM 指标得分 WHERE 期次=? AND 机场=? AND 指标=?",
                              (期次, 机场, 指标)).fetchone()
        else:   # 只给指标不给机场 = 问这期这个指标谁最高
            row = con.execute("SELECT 机场,得分 FROM 指标得分 WHERE 期次=? AND 指标=?"
                              " ORDER BY 得分 DESC LIMIT 1", (期次, 指标)).fetchone()
            if row:
                return f"{row[0]} {row[1]}", None
        if not row:
            return None, f"查不到 {期次} / {机场} / {指标}"
        return f"{row[0]}", None

    return None, f"不认识这个表 {表!r}(可用: meta / 综合得分 / 指标得分)"


# ══════════════════════════════════════════════════════════
#  读填好的表
# ══════════════════════════════════════════════════════════
def read_rows(path):
    from openpyxl import load_workbook
    wb = load_workbook(path, data_only=True)
    ws = wb["填题"]
    rows = []
    for r in ws.iter_rows(min_row=2, values_only=True):
        if r[0] is None:
            continue
        rows.append({
            "题号": r[0], "批次": r[1], "类别": r[2], "问题": r[3],
            "期望去向": r[4], "期望答案": r[5], "出处": r[6],
            "拒答理由": r[7], "测什么": r[8],
        })
    return rows


def check(con, row):
    """对一行做核对。返回 dict(结论, 说明, 值)"""
    去向 = (row["期望去向"] or "").strip()
    答案 = row["期望答案"]
    出处 = row["出处"]
    notes = []

    if not row["问题"]:
        return {"结论": "空", "说明": "还没填", "值": ""}
    if not 去向:
        return {"结论": "★待填", "说明": "『期望去向』没填", "值": ""}
    if 去向 not in ("SQL", "检索", "拒答"):
        return {"结论": "★格式", "说明": f"去向只能填 SQL/检索/拒答,你填的是 {去向!r}", "值": ""}

    # ── 拒答:要的是【理由】,不是出处 ─────────────────────
    if 去向 == "拒答":
        if not (row["拒答理由"] or "").strip():
            return {"结论": "★待填", "说明": "拒答题必须在『拒答理由』里写清为什么拒 —— "
                                          "拒答要是没理由,就和『答不出来』分不清了", "值": ""}
        # ※ 第一版这里卡的是"答案必须是『不回答』"—— 太死。他写"拒答"意思一样。
        #   真正值得报的是【他写了一个具体的值】:那说明他其实认为该答得出来,
        #   去向填拒答就自相矛盾了。
        if numbers_in(答案):
            return {"结论": "★格式",
                    "说明": f"去向填的是拒答,但期望答案里写了一个具体的值({sorted(numbers_in(答案))})—— "
                            f"这两列在打架。要么改成答得出来,要么把答案清空", "值": ""}
        return {"结论": "✅可核", "说明": f"要拒得有理由:{row['拒答理由']}", "值": ""}

    # ── 去向说 SQL,答案却说"拒答" —— 两边打架 ─────────────
    if 去向 == "SQL" and str(答案 or "").strip() in ("拒答", "不回答"):
        return {"结论": "★格式",
                "说明": "『期望去向』填的是 SQL,但『期望答案』写的是拒答 —— 这两列在打架。"
                        "要拒答就把去向改成『拒答』(下拉里有),理由填在『拒答理由』", "值": ""}

    clauses, note, err = parse_cite(出处)
    if err:
        return {"结论": "★格式", "说明": f"出处读不懂 —— {err}", "值": ""}
    if note:
        notes.append(note)

    vals = []
    for d in clauses:
        v, e = lookup_one(con, d, notes)
        if e:
            return {"结论": "★出处", "说明": e, "值": ""}
        vals.append(v)
    val = "\n".join(vals)

    # ── 叙述题:机器只摆原文,硬判的只有"你写的数字在不在原文里" ──
    if 去向 == "检索" or any("chunk" in d for d in clauses):
        if 去向 == "SQL":
            return {"结论": "★格式",
                    "说明": "去向填的是 SQL,但出处指向 chunk(原文)—— 你到底要哪个?", "值": val}
        want, have = answer_numbers(答案, rank=False), numbers_in(val)
        miss = want - have
        if miss:
            return {"结论": "★分歧", "说明": f"你写的这些数在原文里找不到: {sorted(miss)}", "值": val}
        tail = f"你写的数 {sorted(want)} 原文里都有" if want else "没写数字,只摆原文"
        return {"结论": "✅可核", "说明": f"出处存在;{tail}" + (";" + "; ".join(notes) if notes else ""),
                "值": val}

    # ── 数值题:机器能算 ────────────────────────────────
    want, have = answer_numbers(答案), numbers_in(val)
    if not want:
        # ※ 第一版这里直接判 ★待填 —— 太狠。答案里没数字【不等于】答案错,
        #   只等于【机器核不了】。这两件事必须分开说,否则我会把自己的局限
        #   说成他的错误。(和第 3 课"查不了 ≠ 查了没有"是同一个道理。)
        return {"结论": "○机器核不了",
                "说明": "期望答案里没有我能提取的数字(纯文字描述)。右边是库里算出来的,请自己看一眼",
                "值": val}
    miss = want - have
    extra = ""
    if miss:
        still, derived = explain_missing(miss, have)
        if derived:
            extra = ";" + "; ".join(f"{k} 是算出来的差({v})" for k, v in derived.items())
        if still:
            return {"结论": "★分歧",
                    "说明": f"你写的是 {sorted(want)},库里算出来是 {sorted(have)}。"
                            f"差 {sorted(still)} —— 要么你写错了,要么出处没覆盖到这个数"
                            f"(比如你还写了排名,出处就得加上『;字段=排名』;"
                            f"写了两个机场,就用 | 分成两处)", "值": val}
    return {"结论": "✅可核",
            "说明": f"对得上({sorted(want)})" + extra + (";" + "; ".join(notes) if notes else ""),
            "值": val}


# ══════════════════════════════════════════════════════════
#  类别级检查 —— 不查单行对错,查【这把尺子量得准不准】
#
#  ※ 第一版这里是按行查的:"类别=应拒答 但去向≠拒答"就报警。
#    那是错的 —— 他改了这个类的名字之后,这一类的定义就是"两个方向都考",
#    行内不一致是【故意的】。按行报警会把设计说成错误。
#    → 改成按类统计:这个类里两个方向各有多少条。全挤在一边才值得说。
# ══════════════════════════════════════════════════════════
def category_tally(rows, results):
    tally = {}
    for r, res in zip(rows, results):
        c = (r["类别"] or "").strip()
        if not c or not r["问题"]:
            continue
        tally.setdefault(c, {"总": 0, "拒答": 0})
        tally[c]["总"] += 1
        if (r["期望去向"] or "").strip() == "拒答":
            tally[c]["拒答"] += 1
    return tally


def write_out(results, out_path):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    wb = Workbook()
    ws = wb.active
    ws.title = "核对结果"
    heads = ["题号", "类别", "问题", "期望去向", "你写的标准答案", "出处",
             "库里算出来的", "核对结论", "说明", "这题在测什么"]
    widths = [6, 12, 40, 10, 22, 38, 40, 10, 62, 28]
    for c, (h, w) in enumerate(zip(heads, widths), 1):
        cell = ws.cell(1, c, h)
        cell.fill = PatternFill("solid", fgColor="1F3864")
        cell.font = Font(color="FFFFFF", bold=True, size=10)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.column_dimensions[cell.column_letter].width = w
    ws.freeze_panes = "C2"

    FILL = {"✅可核": "E2EFDA", "○机器核不了": "DEEBF7", "★分歧": "FCE4D6", "★格式": "F8CBAD",
            "★出处": "F8CBAD", "★待填": "FFF2CC", "○注意": "FFF2CC", "空": "F2F2F2"}
    thin = Side(style="thin", color="BFBFBF")
    for i, r in enumerate(results, 2):
        vals = [r["题号"], r["类别"], r["问题"], r["期望去向"], r["期望答案"],
                r["出处"], r["值"], r["结论"], r["说明"], r["测什么"]]
        for c, v in enumerate(vals, 1):
            cell = ws.cell(i, c, v)
            cell.font = Font(size=10)
            cell.border = Border(left=thin, right=thin, top=thin, bottom=thin)
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            if c == 8:
                cell.fill = PatternFill("solid", fgColor=FILL.get(r["结论"], "FFFFFF"))
                cell.font = Font(size=10, bold=True)
        ws.row_dimensions[i].height = 28
    wb.save(out_path)


# ══════════════════════════════════════════════════════════
#  自检:用假数据把每一条出处格式都撞一遍
#  理由和"建库时拿非法数据撞约束"一样:格式能不能用,不能靠读代码确认
# ══════════════════════════════════════════════════════════
SELFTEST = [
    dict(题号=901, 类别="自检", 问题="2025Q4 上海浦东国际机场的综合得分是多少",
         期望去向="SQL", 期望答案="4.23", 出处="表=综合得分;期次=2025Q4;机场=上海浦东国际机场",
         拒答理由="", 测什么="正常"),
    dict(题号=902, 类别="自检", 问题="2025Q4 上海浦东排第几,一共多少家机场",
         期望去向="SQL", 期望答案="5/42",
         出处="表=综合得分;期次=2025Q4;机场=上海浦东国际机场;字段=排名",
         拒答理由="", 测什么="排名 + 出处覆盖两个数"),
    dict(题号=903, 类别="自检", 问题="2025Q4 样本量",
         期望去向="SQL", 期望答案="889332", 出处="表=meta;期次=2025Q4;字段=样本量",
         拒答理由="", 测什么="meta 单字段"),
    dict(题号=904, 类别="自检", 问题="2024Q2 各项",
         期望去向="SQL", 期望答案="205164 41 6 31",
         出处="表=meta;期次=2024Q2", 拒答理由="", 测什么="meta 不写字段 → 全给"),
    dict(题号=905, 类别="自检", 问题="2025Q4 前 5 名",
         期望去向="SQL", 期望答案="大兴 4.28 宝安 4.27",
         出处="表=综合得分;期次=2025Q4;取前=5", 拒答理由="", 测什么="前N"),
    dict(题号=906, 类别="自检", 问题="2025Q4 上海浦东机场交通",
         期望去向="SQL", 期望答案="4.46",
         出处="表=指标得分;期次=2025Q4;机场=上海浦东国际机场;指标=机场交通",
         拒答理由="", 测什么="指标"),
    dict(题号=907, 类别="自检", 问题="两期谁高", 期望去向="SQL", 期望答案="4.15 4.23",
         出处="表=综合得分;期次=2023Q3;机场=上海浦东国际机场 | 表=综合得分;期次=2025Q4;机场=上海浦东国际机场",
         拒答理由="", 测什么="一次查两处(|)"),
    dict(题号=908, 类别="自检", 问题="全角冒号 + 短名", 期望去向="SQL", 期望答案="4.15",
         出处="表＝综合得分；期次：2023Q3；机场：上海浦东",
         拒答理由="", 测什么="全角符号 + 唯一前缀匹配"),
    dict(题号=909, 类别="自检", 问题="报告文件名当出处", 期望去向="检索", 期望答案="靠桥率",
         出处="CAPSE_2024Q2_机场服务测评报告P5", 拒答理由="", 测什么="报告名 → chunk_id"),
    dict(题号=910, 类别="自检", 问题="2023 年删掉了哪些指标", 期望去向="检索", 期望答案="删除出发机场特色",
         出处="chunk=2023Q3-P05", 拒答理由="", 测什么="叙述"),
    dict(题号=911, 类别="自检", 问题="拒答", 期望去向="拒答", 期望答案="不回答", 出处="",
         拒答理由="年度报告没入库", 测什么="拒答"),
    # ── 下面几条是【故意错的】,用来证明脚本抓得住 ──────────
    dict(题号=921, 类别="自检·故意错", 问题="2025Q4 上海浦东综合得分",
         期望去向="SQL", 期望答案="4.29",          # ← 写错了
         出处="表=综合得分;期次=2025Q4;机场=上海浦东国际机场",
         拒答理由="", 测什么="人写错了,能不能抓出来"),
    dict(题号=922, 类别="自检·故意错", 问题="上海浦东综合得分和排名",
         期望去向="SQL", 期望答案="4.23 第5名",     # ← 出处没覆盖"5"
         出处="表=综合得分;期次=2025Q4;机场=上海浦东国际机场",
         拒答理由="", 测什么="出处没覆盖,能不能抓出来"),
    dict(题号=923, 类别="自检·故意错", 问题="格式错", 期望去向="SQL", 期望答案="1",
         出处="表=不知道什么表;期次=2025Q4", 拒答理由="", 测什么="表名不认识"),
    dict(题号=924, 类别="自检·故意错", 问题="拒答没理由", 期望去向="拒答",
         期望答案="不回答", 出处="", 拒答理由="", 测什么="拒答没理由"),
    dict(题号=925, 类别="自检·故意错", 问题="两处没分开", 期望去向="SQL", 期望答案="4.15 4.23",
         出处="表=综合得分;期次=2023Q3;机场=上海浦东国际机场，表=综合得分;期次=2025Q4;机场=上海浦东国际机场",
         拒答理由="", 测什么="同一处里出现两次『表=』,必须报错而不是静默覆盖"),
    dict(题号=926, 类别="自检·故意错", 问题="歧义短名", 期望去向="SQL", 期望答案="4.23",
         出处="表=综合得分;期次=2025Q4;机场=上海", 拒答理由="", 测什么="『上海』对得上两个机场 → 不许猜"),
    dict(题号=927, 类别="自检·故意错", 问题="去向和答案打架", 期望去向="SQL", 期望答案="拒答",
         出处="表=综合得分;期次=2025Q4;机场=上海浦东国际机场", 拒答理由="", 测什么="去向=SQL 但答案说拒答"),
    dict(题号=928, 类别="自检·故意错", 问题="叙述题里数字不在原文", 期望去向="检索",
         期望答案="删除2个指标", 出处="chunk=2023Q3-P05", 拒答理由="",
         测什么="『2』原文里没有,能不能抓出来"),
]


def selftest(con):
    print("=== 自检:把每条出处格式和每种错误都撞一遍 ===\n")
    results = []
    for row in SELFTEST:
        # ※ 这里我第一版写错了:先去取 row['结论'],但"结论"是 check() 才产出的字段。
        #   KeyError 立刻炸出来 —— 这是【好的】失败方式(看得见)。
        #   如果它不炸、而是静默按空值走,我就会以为自检跑过了。
        r = {**row, **check(con, row)}
        results.append(r)
        val = (r["值"] or "").replace("\n", " ")[:66]
        print(f"{row['题号']} {r['结论']:<6} {r['说明'][:84]}")
        if val:
            print(f"      库里算出来: {val}")
    bad = [r for r in results if r["结论"].startswith("★")]
    should_be_bad = [r for r in SELFTEST if "故意错" in r["类别"]]
    print(f"\n  {len(results)} 条自检,{len(bad)} 条被标成★")
    print(f"  其中【故意写错的】{len(should_be_bad)} 条。它们必须被标出来 —— 标不出来才叫失败。")
    missed = [r["题号"] for r in results if "故意错" in r["类别"] and not r["结论"].startswith("★")]
    if missed:
        print(f"  ★★ 这些故意错的没被抓出来: {missed} —— 这个脚本本身有问题")
    else:
        print("  ✅ 全部抓到。")
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true", help="用内置假数据撞一遍,不读 xlsx")
    ap.add_argument("--in", dest="inp", default=str(EVAL_IN))
    ap.add_argument("--out", dest="out", default=str(EVAL_OUT))
    args = ap.parse_args()

    con = sqlite3.connect(DB)
    load_vocab(con)
    if args.selftest:
        selftest(con)
        return

    if not Path(args.inp).exists():
        print(f"找不到 {args.inp} —— 先跑 python tools/make_eval_sheet.py")
        return
    rows = read_rows(args.inp)
    filled = [r for r in rows if r["问题"]]
    print(f"读了 {len(rows)} 行,其中填了问题的 {len(filled)} 行\n")

    results = [{**row, **check(con, row)} for row in rows]

    tally = {}
    for r in results:
        tally[r["结论"]] = tally.get(r["结论"], 0) + 1
    print("结论分布:", "  ".join(f"{k}={v}" for k, v in sorted(tally.items())))

    ct = category_tally(rows, results)
    if ct:
        print("\n各类已填条数(『拒答·双向』类要看两个方向有没有都有):")
        for c, v in ct.items():
            mark = ""
            if c == "拒答·双向" and v["总"] >= 2 and v["拒答"] in (0, v["总"]):
                mark = ("   ★ 这一类的题全挤在一边了 —— "
                        "两个方向都考才测得出『过度拒答』")
            print(f"  {c:<12} {v['总']:>2} 条,其中判拒答 {v['拒答']} 条{mark}")

    for r in results:
        if not r["结论"] in ("空", "✅可核"):
            print(f"  {r['题号']:>3} {r['结论']} {r['说明'][:110].replace(chr(10),' ')}")

    write_out(results, args.out)
    print(f"\n结果写到: {args.out}")
    print("※ 脚本没判你『对错』,它只是把 你写的 / 库里算的 摆在一起。")
    print("※ 而且脚本和库是同一条路出来的 —— 真独立的那条路是人回去翻 PDF。")


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    main()
