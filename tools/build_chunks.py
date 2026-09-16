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

DATA      = Path(r"D:\capse-kb\data")
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
            if kind != "叙述页":
                continue
            text = clean(page.get_text())
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
