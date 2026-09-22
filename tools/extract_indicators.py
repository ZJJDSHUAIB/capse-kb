# -*- coding: utf-8 -*-
r"""
从 2025Q4 报告里,提取【一级指标 × 机场】的分数。

═══ 为什么只有这一份能做到 ═══
    9 份季度报告里,只有 2025Q4 公布了 7 个一级指标各自的机场级排名。
    其余 8 期只公布"综合得分"。
    这个不对称不是缺陷,是测试题的来源:
        "2024Q3 上海浦东的安检得分?"   → 数据不存在 → 第三档:拒答
        "2025Q4 深圳宝安的机场交通?"   → 有         → 第一档:直接答
        "2025Q4 对比 2024Q3 的综合得分?" → 跨口径    → 第二档:答 + 强制标注

═══ 与季度"综合得分"页的三处不同 ═══
    ① 页面顶部多了页眉页脚:"第 N 页" / "Copyright© 2025 CAPSE. All rights reserved."
       两者都不含小数点,不会污染分数正则。
    ② 标题上方多一行"测评子项目"说明,里面藏着【假机场名】:
           "◆机场交通测评子项目:出发地机场交通、目的地机场交通、机场停车场。"
                                    ↑↑↑↑↑↑↑↑          ↑↑↑↑↑↑↑↑
           这两个长得跟真机场名一模一样,会被机场名正则原样抓走。
    ③ 平均的写法变了:
           季度综合得分页:  平均：4.15    (全角冒号)
           这里的一级指标页: 平均, 4.36    (半角逗号)
       —— 又一次"不许写死措辞"。

═══ 解法:以"平均"为刀,把页面劈成两半 ═══
    实测每页的物理顺序是固定的:
        页眉 → 说明 → 标题 → 分数块 → 【平均】 → 机场名块
    所以:
        平均【之前】的部分,只可能有分数,不可能有机场名 → 在那里抓分数
        平均【之后】的部分,只可能有机场名,不可能有分数 → 在那里抓机场名
    这一刀同时解决了 ② 和 ③:
        假机场名在"之前",根本进不了抓取范围;
        平均的写法差异被这一刀直接绕开,连适配都不需要。

    教训:遇到"某某词会被误抓"的问题,优先想【能不能用位置排除】,
          而不是【枚举哪些词是噪声】。枚举永远不全。

═══ 三道自检(与综合得分页同款) ═══
    ① 分数个数 == 机场名个数 == 42
    ② 分数降序
    ③ 实算平均 == 报告自报平均
       ③ 还兼职【防误收】:分吞吐量级页(P18-P21)的标题是
       "2025Q4—4000万级以上机场综合得分",不含"内地机场",本来就匹配不上。
       万一将来版式改了被收进来,那几页的"平均"是【全行业均值】而非本页均值,
       ③ 会立刻报错。自检不只验对错,还能挡住"不该进来的"。
"""
import sys, io, re
from pathlib import Path
import fitz
from paths import ROOT, DATA, PROCESSED, DOCS, DB, OUTPUT


SCORE   = re.compile(r'\d+\.\d+')
AIRPORT = re.compile(r'[\u4e00-\u9fff]+?机场')
DEWRAP  = re.compile(r'(?<=[\u4e00-\u9fff])\s*\n\s*(?=[\u4e00-\u9fff])')
AVG     = re.compile(r'平均\s*[：:,，]\s*(\d+\.\d+)')          # 全角冒号 / 半角逗号都收
# 切在"内地"之后,不是"内地机场"之后 —— "机场"两个字属于【指标名】:
#     "2025Q4 内地 【机场交通】 综合得分"
# 写成"内地机场"会把"机场"吃掉,指标名变成"交通"。
# 注意:三道自检查的是数量/降序/均值,【查不出名字对不对】。名字要靠下面的名单校验。
TITLE   = re.compile(r'\d{4}Q\d内地(.{2,12}?)综合得分')
NOISE   = {"内地机场"}

# 独立信源:每份一级指标页的页眉都会把这 7 个指标名列一遍 ——
#     "◆机场综合得分包含测评项目:机场交通、机场服务与设施、机场商贸、机场安检、出港服务、进港服务、航班不正常保障。"
# 拿它来验"我从标题里切出来的名字"是否真的对得上。
PROJECTS = re.compile(r'包含测评项目[：:](.+?)。')
PROJECT_SPLIT = re.compile(r'[、,，]')

AIRPORTS_PER_PERIOD = 42


def _check(indicator, names, scores, stated_avg, pdf_path, page_i):
    where = f"{Path(pdf_path).stem} 第{page_i + 1}页[{indicator}]"
    if not scores:
        raise ValueError(f"{where}: 一个分数都没找到")
    if len(names) != len(scores):
        raise ValueError(f"{where}: 数量对不上 —— 分数 {len(scores)} 个,机场名 {len(names)} 个\n"
                         f"    机场名: {names}")
    if len(scores) != AIRPORTS_PER_PERIOD:
        raise ValueError(f"{where}: 分数 {len(scores)} 个,应为 {AIRPORTS_PER_PERIOD} 个")
    if scores != sorted(scores, reverse=True):
        raise ValueError(f"{where}: 分数不是降序,可能配错位了\n    {scores}")
    calc = round(sum(map(float, scores)) / len(scores), 2)
    if abs(calc - stated_avg) >= 0.005:
        raise ValueError(f"{where}: 实算平均 {calc} ≠ 报告自报平均 {stated_avg} —— 分数取错了")


def _indicator_of(raw, official, pdf_path, page_i):
    """这一页讲的是哪个一级指标?

    【标题】负责"这一页是不是指标页" —— 只有指标页的标题长成
        "2025Q4 内地 XXX 综合得分"。
        综合得分页(P9)的标题是 "2025Q4内地机场综合得分",也会匹配,
        但切出来的候选是"机场",跟任何官方指标名都对不上,自然被排除。
        (P9 整页都印着"包含测评项目:机场交通、…"那七个名字,
         所以【千万不能】拿整页去认领 —— 一页会认领到七个。)

    【官方名单】负责"机场"两个字归谁 —— 标题本身是有歧义的:
        "2025Q4内地机场出港服务综合得分"
            "…内地 【机场交通】 综合得分"      ← "机场"归指标名
            "…【内地机场】 出港服务 综合得分"  ← "机场"归"内地机场"
        两种切法都讲得通,单看标题永远切不对。
        用【后缀匹配】让官方名单裁决:
            切出"机场交通"     → 官方名单里"机场交通"是它的后缀 ✓
            切出"机场出港服务" → 官方名单里"出港服务"是它的后缀 ✓
        名单里有"机场交通"却没有"机场出港服务",歧义就此消解。

    —— 遇到"两种读法都通"的文本,别堆正则技巧,去找一个能裁决的独立信源。
    """
    m = TITLE.search(raw)
    if not m:
        return None
    candidate = m.group(1)                                   # 比如 "机场交通" / "机场出港服务"
    hits = [n for n in official if candidate.endswith(n)]     # 官方名单里谁是他的后缀
    if not hits:
        return None                                          # 不是指标页(比如 P9 切出的"机场")
    if len(hits) > 1:
        longest = max(hits, key=len)
        if len(longest) == len(hits[0]):                     # 两个等长的后缀,真歧义
            raise ValueError(f"{Path(pdf_path).stem} 第{page_i + 1}页: 标题 {candidate!r} 有歧义,"
                             f"官方名单里 {hits} 都是它的后缀")
        hits = [longest]                                     # 取最长的那个
    return hits[0]


def extract_one_page(raw, pdf_path, page_i, official):
    """一页 = 一个一级指标。不是一级指标页就返回 None。"""
    indicator = _indicator_of(raw, official, pdf_path, page_i)
    if indicator is None:
        return None

    m_avg = AVG.search(raw)
    before, after = raw[:m_avg.start()], raw[m_avg.end():]

    scores = SCORE.findall(before)
    names  = [a for a in AIRPORT.findall(DEWRAP.sub('', after)) if a not in NOISE]
    stated_avg = float(m_avg.group(1))

    _check(indicator, names, scores, stated_avg, pdf_path, page_i)
    return indicator, list(zip(names, scores))


def official_projects(pdf_path):
    """读出报告自己列的【指标名单】。

    报告多处写着:
        "◆机场综合得分包含测评项目:机场交通、机场服务与设施、机场商贸、机场安检、出港服务、进港服务、航班不正常保障。"
    这是独立信源 —— 不是我从标题里切出来的,而是报告自己列的。
    用它才能裁决标题里"机场"两个字的归属(见 _indicator_of)。

    ⚠ 重要:这份报告【自己就不自洽】—— 同一份文件里,这句话出现了两种顺序:
        P9      : 机场交通、机场服务与设施、【机场安检】、【机场商贸】、…
        P18-P21 : 机场交通、机场服务与设施、【机场商贸】、【机场安检】、…
      名字集合相同,顺序不同。这是报告自身的问题,不是提取错误。
    → 所以这个名字表【只能用来认名字,不能用来定顺序】。
      名字集合拿它验;顺序由页面先后(P10→P16)决定,那才是报告实际呈现的顺序。
      这也说明:别把"文档里的一句话"当成绝对权威,先验它自己前后一致不一致。
    """
    doc = fitz.open(pdf_path)
    seen = []
    for page in doc:
        for m in PROJECTS.finditer(page.get_text().replace("\n", "")):
            seen.append([s.strip() for s in PROJECT_SPLIT.split(m.group(1)) if s.strip()])
    doc.close()

    if not seen:
        raise ValueError(f"{Path(pdf_path).name}: 找不到'包含测评项目'那一句,没法校验指标名")

    base = set(seen[0])
    for other in seen[1:]:
        if set(other) != base:
            raise ValueError(f"{Path(pdf_path).name}: 这句名单自己就前后矛盾:\n"
                             f"    {seen[0]}\n    {other}")
    if len({tuple(s) for s in seen}) > 1:
        print(f"  ⚠ {Path(pdf_path).name}: '包含测评项目'名单在文档里有 {len({tuple(s) for s in seen})} 种顺序"
              f"(名字相同)。报告自身不一致,只取名字集合用于仲裁。")
    return base


def extract(pdf_path):
    """把整份报告里所有一级指标页都抓出来。

    不写死页码:判据是"标题长得像一级指标页"。哪一页出现与位置无关。
    """
    # 先读官方名单 —— 它既是"裁决者",也是"验收标准"。
    official = official_projects(pdf_path)

    doc = fitz.open(pdf_path)
    out = []
    for i, page in enumerate(doc):
        got = extract_one_page(page.get_text(), pdf_path, i, official)
        if got:
            out.append((got[0], got[1], i))
    doc.close()

    # 第四道自检:认领到的指标名【集合】要和报告名单一致。
    # 只比集合,不比顺序 —— 报告自己的顺序都不统一,顺序由页面先后决定。
    got_names = [ind for ind, _, _ in out]
    if set(got_names) != official:
        raise ValueError(
            f"{Path(pdf_path).name}: 指标名和报告名单对不上\n"
            f"    实得: {sorted(got_names)}\n"
            f"    名单: {sorted(official)}")
    return out


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    import glob
    f = glob.glob(str(DATA / "CAPSE_2025Q4*.pdf"))[0]
    for indicator, pairs, page_i in extract(f):
        head = " ".join(f"{a}({s})" for a, s in pairs[:3])
        print(f"P{page_i + 1:<3}{indicator:<12}{len(pairs):>3}家   {head} ... {pairs[-1][0]}({pairs[-1][1]})")
