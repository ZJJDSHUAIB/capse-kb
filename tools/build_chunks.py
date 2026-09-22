# -*- coding: utf-8 -*-
r"""
第 1 课:把 PDF 正文切成可检索的块(基线版)。

═══ 这一版【故意】很朴素 ═══
    基线 = 「一页 = 一块」,只做两件必须的清洗。
    为什么不现在就优化粒度:
        因为"多大算好"没有度量标准 —— 评估体系(第 6 步)还没建。
        现在调粒度,你只是把"感觉"换成了"另一种感觉"。
    正确顺序:先跑通整条链路 → 建评估 → 那时再回来把
        「按页切 / 按段切 / 固定字数带重叠」
    跑成一组对照实验。那才是"用数据选策略",而不是"拍脑袋"。

═══ 第一刀:选料(比切更重要) ═══
    146 页里只有 54 页该进向量库:

        29 页 数据页     —— 42 个分数 + 42 个竖排机场名。
                            这些内容【已经在 capse_scores.csv /
                            capse_indicators.csv 里了】。
                            再切进向量库 = 把同一份数据存两遍,
                            而且踩中"294 行长得一模一样"那个坑:
                            向量检索分不出"上海浦东"和"深圳宝安"。
        63 页 空白/封面/目录 —— 没信息量。
        54 页 叙述页     —— 方法论、口径说明、指标变更。← 这些才该进

    教训:切之前先选。不加区分地全切,等于往库里灌噪声。

═══ 第二刀:清洗(不洗,切出来的块是坏的) ═══
    毛病一:页眉页脚混在正文里
        "10" / "页" / "第" / "Copyright© 2025 CAPSE. All rights reserved."
    毛病二:软换行把词切断
        "办理行\n李托运"          → 应是 "办理行李托运"
        "步行至登机口时间"调整为"到登机口的步行体\n验"  → 中间断了

    清洗规则(两条,不多不少):
        ① 删页眉页脚行 —— 按【特征】认,不按位置认(位置会变)
        ② 合并软换行   —— 但【保留列表结构】:
                           以 (1)/⚫/◆/•/数字. 开头的行是新条目,另起;
                           其余换行是排版折行,接上。

═══ 自检 ═══
    ① 块数 == 叙述页页数
    ② 每个块都非空,且长度在合理区间
    ③ 【块里不许再出现页眉页脚】—— 清洗是否真的生效
       ※ 这一条是"用结果验过程":清没清干净,不看清洗代码,看产出。
"""
import sys, io, json, re
from pathlib import Path
import fitz
from paths import ROOT, DATA, PROCESSED, DOCS, DB, OUTPUT

PROCESSED = DATA / "processed"
OUT       = PROCESSED / "capse_chunks.jsonl"

PERIOD = re.compile(r'CAPSE_(\d{4}Q\d)')
SCORE  = re.compile(r'\d+\.\d+')
AIRPORT= re.compile(r'[\u4e00-\u9fff]+?机场')

# ── 选料用的两个阈值(是【参数】,不是写死的内容) ──────────────
# 它们不绑定任何具体页面或措辞,所以换一份报告也不用改。
# ※ 但它们是启发式的,不是真理。等第 6 步有了评估,要用"漏没漏掉该检索的页"来校准。
BLANK_MAX_CHARS  = 120   # 少于这个字符数的页,装不下一个有意义的段落
DATA_MIN_MARKS   = 20    # 一页列了 20 个以上分数/机场名,就是数据表

# ── 页眉页脚特征 ─────────────────────────────────────────
FOOTER_PAT = [
    re.compile(r'^\s*\d+\s*$'),                                   # 纯页码
    re.compile(r'^\s*[页第]\s*$'),                                 # 竖排页脚残留
    re.compile(r'Copyright|All rights reserved', re.I),           # 版权行
    re.compile(r'^\s*Source\s*[:：]\s*CAPSE\s*$', re.I),           # 数据来源
]

# ── 列表标记:以它开头的行是新条目,不参与软换行合并 ────────────
LIST_START = re.compile(r'^\s*(?:[（(]\s*\d+\s*[)）]|[⚫◆●•·]|[-–—]\s|\d+\s*[.、])')

# ── 私有区(PUA)符号归一化 ────────────────────────────────────
# PDF 里项目符号用的是【字体私有编码】,提取出来落在 Unicode 私有区(U+E000–U+F8FF)。
# 这类字符有两个坑,两个都实打实踩过:
#     ① 渲染时看不见 —— 盯着输出看,会以为"符号丢了";其实它在,只是不显示
#     ② 正则匹配不到 —— 它不等于 "⚫",进不了上面的 [⚫◆●•],列表规则整条失效
# 实测:整个语料只有 2 种,都是装饰性项目符号,不承载数据 ——
#     U+F06C = Wingdings 'l' = ●   用于列表项
#     U+F075 = Wingdings 'u' = ◆   用于小节标题
# 所以映射成可见的等价符号,信息一点不丢。
# (同一个坑之前还以 '机场' 的形态冒充过机场名 —— 见 capse_airport_list.md)
PUA_MAP = {chr(0xF06C): '●', chr(0xF075): '◆'}
PUA_ANY = re.compile('[' + chr(0xE000) + '-' + chr(0xF8FF) + ']')


def is_footer(line):
    return any(p.search(line) for p in FOOTER_PAT)


def classify(page):
    """这一页该不该进向量库?"""
    text = page.get_text()
    n = sum(1 for c in text if not c.isspace())
    if n < BLANK_MAX_CHARS:
        return "空白/封面/目录", n
    marks = len(SCORE.findall(text)) + len(AIRPORT.findall(text))
    if marks >= DATA_MIN_MARKS:
        return "数据页", n
    return "叙述页", n


def clean(raw):
    """归一化私有区符号 → 删页眉页脚 → 合并软换行(保留列表结构)。"""
    # ① 私有区符号归一化。没登记过的 PUA 字符【直接报错】,不静默处理 ——
    #    因为"没见过的符号"意味着"没见过的版式",那正是最该被人看一眼的时候。
    unknown = set(PUA_ANY.findall(raw)) - set(PUA_MAP)
    if unknown:
        raise ValueError(f"发现未登记的私有区字符: {[hex(ord(c)) for c in unknown]} —— 先查清它是什么,再决定映射")
    raw = PUA_ANY.sub(lambda m: PUA_MAP[m.group()], raw)

    lines = [l.rstrip() for l in raw.split("\n")]
    lines = [l for l in lines if l.strip() and not is_footer(l)]

    out = []
    for ln in lines:
        if not out or LIST_START.match(ln):
            out.append(ln.strip())
        else:
            out[-1] += ln.strip()        # 软换行,接到上一行
    return "\n".join(out)


def strip_footer_only(raw):
    """只删页眉页脚,【不做软换行合并】。

    ★ 为什么需要它(而不是直接用 clean()):
      clean() 会把【不以列表标记开头的行】接到上一行(那是为了治排版折行)。
      ★★ 而重排过的分数表,每一行都是"机场 分数" —— 没有列表标记,
          过 clean() 就会被接成一整行,配对又没了。
      ★★★ 所以重排后的文字走这条路:只删页眉页脚,保留换行。
    """
    lines = [l.rstrip() for l in raw.split("\n")]
    lines = [l for l in lines if l.strip() and not is_footer(l)]
    return "\n".join(lines)


def reorder_score_table(raw):
    """把「分数总表」那一页,重排成【机场和分数配好对】的样子。

    ═══ 为什么需要它(2026-09-22)═══
        这一页原来的文字长这样:

            4.28 4.27 4.25 4.25 4.23 … 4.09 4.05 4.05
            平均, 4.15
            北 / 京 / 大 / 兴 / 国 / 际 / 机 / 场 / 深 / 圳 / …

        ★ 分数在上、名字【一个字一行】在下 —— 两边分开印,顺序一一对应。

    ═══ 不重排会怎样 ═══
        ① 用户拿这个出处核不回:"上海浦东多少分?" 他得自己在
           42 个分数和 42 个竖排字里配对。
           ★ 而业界的原话:"a link to a 40-page PDF verifies nothing" ——
             出处要能真的核到那个数。
        ② 当年不收数据页的第二条理由是"向量检索分不出「上海浦东」和「深圳宝安」"。
           ★★ 那是因为每行不自描述。重排之后【每行自带名字】,那条就治了。
           (业界那条:Table rows should be chunked individually and self-describing)

    ═══ 做法 ═══
        锚点:含「平均」且有分数的那一行 —— 名字区在它下面。
        ★★ 为什么用锚点而不是"找第一个单字行":页眉也是竖排的("9"/"页"/"第"),
          不设锚点会从页眉开始连。

    ⚠ 尽力而为:对不齐(分数个数 != 名字个数)就返回 None,【不硬凑】。
      数据页不止这一种结构(还有机场名单、指标表),那些原样收。

    ═══ ★ 两种排版都要认(实测)═══════════════════════════════
        2025Q4 那种:  分数挤在一行   "4.28 4.27 … / 平均, 4.15 / 名字一个字一行"
        2024Q1 那种:  分数一行一个   "4.22 / 4.22 / … / 平均 / ：4.11 / 名字一整行"

      ★ 所以锚点放宽成"含平均就行"(不要求同行有分数),
        名字区的处理【两种都能对付】—— 见下面那段"拼成一个串再按机场切"。
    """
    lines = [l.strip() for l in raw.split("\n")]
    anchor = None
    for i, l in enumerate(lines):
        if "平均" in l:
            anchor = i
            break
    if anchor is None:
        return None

    #  ⚠ 只取【锚点之前】的分数 —— 锚点附近那个数是【行业平均分】,不是任何机场的分。
    #  ★ 不排掉它,分数就会比名字多一个 → 对不齐 → 重排整个失败。
    #    (实测踩过 2025Q4:43 个分数、42 个名字,于是返回 None,那一页没配上对)
    scores = SCORE.findall(" ".join(lines[:anchor]))

    #  ★ 名字区:把锚点之后的【所有行拼成一个串】再按「机场」切。
    #    这样【两种排版都对付】:
    #      · 一个字一行 → 拼起来就是名字串
    #      · 一整行连着写 → 拼起来还是它
    #
    #  ⚠⚠ 拼之前【必须先滤掉页眉页脚】—— 这一条是实测踩出来的:
    #     2025Q4 的 tail 末尾是 "…太原武宿国际机场Source:CAPSE",
    #     而 "Source:CAPSE" 是页脚。不滤的话会切出第 43 个假机场名
    #     ("Source:CAPSE机场")→ 分数 42 个、名字 43 个 → 对不齐 → 整个重排失败。
    #     ★ 而它失败得【很安静】:只表现为"这一页没配上对",不报错。
    body = [l for l in lines[anchor:] if not is_footer(l)]
    tail = "".join(body)
    #  ★ 去掉开头的"平均"和它后面跟的标点数字(如 ":4.11")——
    #    那些都不是汉字,所以一句正则就能清掉,不需要写特例。
    tail = re.sub(r'^[^一-鿿]*平均[^一-鿿]*', '', tail)
    names = [x + "机场" for x in tail.split("机场") if x.strip()]
    if not scores or len(scores) != len(names):
        return None                        # 对不齐 → 不硬凑
    return "\n".join(f"{n} {s}" for s, n in zip(scores, names))


def build():
    chunks = []
    for pdf in sorted(DATA.glob("CAPSE_*.pdf")):
        m = PERIOD.search(pdf.name)
        if not m:
            continue                      # 年度报告没有季度编号,跳过
        period = m.group(1)
        doc = fitz.open(pdf)
        for i, page in enumerate(doc):
            kind, n = classify(page)
            raw = page.get_text()
            if kind == "数据页":
                # ══ ★★★ 2026-09-22 改:数据页【也收】 ═══════════════════
                #  ★ 原来这里是 `if kind != "叙述页": continue` —— 数据页全跳过。
                #    当时的理由两条(见文件头),今天看【只有第二条真的成立】:
                #      ① "数据重复(CSV 里已有)" —— 数据在,但【那一页的文本不在】
                #         → SQL 的答案带出处"第9页",而用户【核不回那一页】。
                #         而业界那句:"a link to a 40-page PDF verifies nothing"
                #      ② "向量检索分不出「上海浦东」和「深圳宝安」" —— 那条是真的。
                #         而重排成【自描述的行】之后,它就治了。
                #         (业界:Table rows should be chunked individually and self-describing)
                #  ★★ 所以:能配对的就重排(配对 + 每行自带名字),不能的原样收。
                #     ——原样收也【比不收好】:至少出处能翻到那一页。
                fixed = reorder_score_table(raw)
                text = strip_footer_only(fixed) if fixed else clean(raw)
                kind = "数据页·已配对" if fixed else "数据页"
            elif kind == "叙述页":
                text = clean(raw)
            else:
                continue                     # 空白/封面/目录 仍然不收
            chunks.append({
                "chunk_id": f"{period}-P{i + 1:02d}",
                "期次": period,
                "页码": i + 1,
                "字符数": len(text),
                "页类型": kind,
                "文本": text,
            })
        doc.close()
    return chunks


def check(chunks):
    if not chunks:
        raise ValueError("一块都没切出来")
    for c in chunks:
        if not c["文本"].strip():
            raise ValueError(f"{c['chunk_id']}: 空块")
        if PUA_ANY.search(c["文本"]):
            raise ValueError(f"{c['chunk_id']}: 还有私有区字符没归一化")
        # ③ 用结果验过程:清洗到底生效没有
        for line in c["文本"].split("\n"):
            if is_footer(line):
                raise ValueError(f"{c['chunk_id']}: 页眉页脚没清干净 -> {line!r}")
    lens = sorted(c["字符数"] for c in chunks)
    return lens


def write(chunks, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    chunks = build()
    lens = check(chunks)                     # ← 先自检
    write(chunks, OUT)

    print(f"写出 {OUT}  ({len(chunks)} 块)\n")
    from collections import Counter
    for p, n in sorted(Counter(c["期次"] for c in chunks).items()):
        print(f"    {p}   {n:>2} 块")
    print(f"\n块长度: 最短 {lens[0]}  中位 {lens[len(lens)//2]}  最长 {lens[-1]}  字符")
    print(f"\n--- 样例:{chunks[0]['chunk_id']} ---")
    print(chunks[0]["文本"][:600])
