# -*- coding: utf-8 -*-
r"""
第 8 课 · 「同一页有多个版本」—— 这是这一课挖出来的【根因】。

═══ 张君杰的问题 ═══
    "程序为什么不知道有多页?那以后遇到类似问题不都回答不了了吗?"

    **他问的不是 #39 一道题,是一整类。** 查出来的答案:

        chunk 表【有】页码列 —— 程序知道哪几条页码相同。
        **但它从来没有拿这个信息做过任何事。**
        检索时每条 chunk 是一个【独立的候选】,谁得分高谁上来,
        它不知道"你俩说的是同一页"。

    而库里有【83%】是这个形状:
        15 个页码,6 个跨期 —— 第7页9期、第11页8期、第12页8期、
        第13页8期、第14页7期、第5页5期,共 45 条块 / 全库 54 条。

═══ ★★ 这一课【所有】检索类失败,根都在这里 ═══
    #39  多版本不可见   → 只取到 9 条里的 1 条
    #42  跨期矛盾       → 同时取到 2024Q2-P07 和 2025Q2-P07,拼在一起矛盾
                          ★ 因为它不知道这两个是同一页
    #48/#51/#52 取错页  → P07 有 9 条,每条都在竞争,★ 一页就占了 3 个名额
                          把真正有答案的 P05/P21 挤出去了
    期次污染 37%        → 同一个根

    **五个症状,一个根。而前面每一轮都是【按症状在治】。**

═══ 判据:三行清理 + 精确比对,【没有阈值】 ═══
    这是本文件最要紧的地方 —— 一路踩过的坑都是"我拍了一个阈值,阈值吃掉事实"。

        ① 抹掉【期次名】  —— 「CAPSE 2024Q2 国际及港澳台…」里的 2024Q2
                              它说的是"这段是哪一期的",【不是版本差异】
        ② 抹掉【所有空白】—— 排版噪音。实测 2024Q4 就比 2024Q3 多一个空格!
                              不抹的话,一个空格就能分出一"组"
        ③ 精确比对        —— 一样就是同一版,不一样就是不同版

    ★ 为什么不相似度:量过 ——
        30项→31项 的相似度是 0.9955,而【只差一个空格】是 0.9933
        两个数几乎一样高,**没有任何阈值能同时"合并空格"和"分开 30/31"**。
      而三行清理之后,30/31 是【真的不同】,空格是【真的没了】—— 精确比对就分开了。

    ★ 结果(实测,和真相完全一致):
        第 7 页 9 期 → 3 组:2023Q3 / 2024Q1~Q4 / 2025Q1~Q4
                            ↑ 正好是答案键说的"三档"
"""
import re

PERIOD = re.compile(r'\d{4}Q\d')
WS = re.compile(r'\s+')


def norm(text):
    """归一化:抹掉期次名,再抹掉所有空白。

    ※ 这两条是【结构性的清理】,不是阈值 —— 它们去掉的是"排版噪音"和
      "这段是哪一期的",留下的才是内容本身。
    """
    return WS.sub('', PERIOD.sub('◇', text or ''))


def versions(con, page):
    """这一页有几个版本?

    返回 [(期次列表, 代表文本, 代表期), ...],按期次先后排。
    只有一组 → 这一页跨期是同一段文字,没有版本问题。
    """
    rows = con.execute(
        "SELECT chunk_id, 期次, 文本 FROM chunk WHERE 页码=? ORDER BY chunk_id",
        (int(page),)).fetchall()
    if not rows:
        return []
    groups, sig = [], {}
    for cid, per, t in rows:
        k = norm(t)
        if k in sig:
            groups[sig[k]][0].append(per)
        else:
            sig[k] = len(groups)
            groups.append([[per], t, per, cid])
    return [(g[0], g[1], g[2]) for g in groups]


def describe(con, page):
    """给人看的一句话。多版本才返回;单版本返回 None(不啰嗦)。"""
    vs = versions(con, page)
    if len(vs) <= 1:
        return None
    lines = [f"★ 第 {page} 页在 {sum(len(p) for p, _, _ in vs)} 期里有 {len(vs)} 个版本:",
             "  ⚠ 别只看其中一个 —— 报告跨期比较时,这里会让结论反过来。"]
    for pers, text, _ in vs:
        span = pers[0] if len(pers) == 1 else f"{pers[0]}~{pers[-1]}"
        #  只截一小段当指纹 —— 全文太长,而差异通常在开头
        lines.append(f"    · {span}(共 {len(pers)} 期):{text[:70].strip()}…")
    return "\n".join(lines)


if __name__ == "__main__":
    import sys, io, sqlite3
    from pathlib import Path
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    con = sqlite3.connect(r"D:\capse-kb\data\processed\capse.db")
    print("库里所有跨期的页,各有多少个版本:\n")
    for (pg,) in con.execute(
            "SELECT 页码 FROM chunk GROUP BY 页码 HAVING COUNT(DISTINCT 期次)>1 ORDER BY 页码"):
        vs = versions(con, pg)
        n = sum(len(p) for p, _, _ in vs)
        print(f"  第 {pg:>2} 页  {n} 期 → {len(vs)} 个版本")
        for pers, _, _ in vs:
            span = pers[0] if len(pers) == 1 else f"{pers[0]}~{pers[-1]}"
            print(f"        {span}")
