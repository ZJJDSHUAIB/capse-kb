# -*- coding: utf-8 -*-
r"""
第 5 课:把链子串起来 —— 问一句,真的给一个答案。

═══ 这一课的规则是张君杰定的,不是我提的 ═══
    我问:"一个答案里必须包含什么,才算对用户负责?"
    他答:
        ① 必须给来源          → "用户凭什么相信 4.23?他得能自己去核"
        ② 跨口径必须说明       → 两期的尺子不同时,光给两个数就是误导
    代码只是把他这两句话写下来。

═══ 答案不是一个字符串,是一个【结构】═══
    这是本课最关键的设计决定,也是他①号规则逼出来的:
        如果答案只是一个字符串 "4.23",那"来源"就没地方放,
        只能在渲染的时候临时拼进去 —— 那是"事后补",不是"必须带"。

    所以: 答案对象自带【来源】字段。没有来源的答案,在结构上就【构造不出来】。
        ※ 约束放在结构里,不放在人心里 —— 第 2 课库约束是同一个思路。

    ANSWER = {
        问题 / 去向 / 答案 / 来源 / 标注 / 警告
    }

═══ 链子长什么样 ═══
    问题
     └ 路由(第4课)  → SQL / 检索 / 拒答 / 判不出
        └ 执行     → 查表 / 检索
           └ 验证(第4课) → 走检索的题,回来那几段话答得了这个问题吗?
              └ 组装  → 答案对象(来源必填)
                 └ 渲染 → 给人看的一段

═══ 这一课会暴露的第一个缺口(跑完见分晓) ═══
    "必须给来源"这条规则,对两条路的要求是不一样的:
        检索路: 回来就带着 chunk_id / 期次 / 页码 / 原文  → 来源【完整】
        SQL 路: 只有表名和主键                     → 来源【只到表,到不了 PDF 页码】

    → 用户拿着 SQL 答案,想回原文核一眼,核不了。
      不是代码写错了,是【第 1 课入库时没记页码】。
      他这条规则,一句话就把一个一直存在、但没人注意到的缺口照出来了。
      —— 这就是"先定规则,再写代码"的价值:规则会替你发现代码没想到的事。
"""
import sys, io, re, sqlite3
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from route import (load_airports, load_indicators, find_periods, find_airport,
                   find_indicator, route, verify)
from build_search import search, searchable, search_multi
from route_llm import judge_intent, rewrite_query
from llm import LLMError

DB = Path(r"D:\capse-kb\data\processed\capse.db")


# ══════════════════════════════════════════════════════════
#  执行层:走 SQL 的题,怎么从库里把数取出来
# ══════════════════════════════════════════════════════════
def answer_sql(con, q, periods, airport, indicator):
    """数值型。返回 (答案行列表, 来源列表)。

    ※ 规则版只能认这几种问法,认不出的走最后的兜底。
      兜底撞墙的地方 = 规则版的边界,故意留着,不和稀泥。
    """
    ps = sorted(periods)
    lines, src = [], []

    # ── meta 类:样本量 ──────────────────────────────
    if re.search(r'样本量|样本数', q):
        for p in ps:
            row = con.execute("SELECT 样本量, 机场数 FROM meta WHERE 期次=?", (p,)).fetchone()
            if row:
                lines.append(f"{p}:样本量 {row[0]:,} 份,覆盖 {row[1]} 家机场")
                src.append(f"capse.db / meta 表,期次={p}")
        return lines, src

    # ── 指标级:只有 2025Q4 有 ────────────────────────
    if indicator:
        for p in ps:
            sql = "SELECT 机场, 得分 FROM 指标得分 WHERE 期次=? AND 指标=?"
            args = [p, indicator]
            if airport:
                sql += " AND 机场=?"
                args.append(airport)
            rows = con.execute(sql + " ORDER BY 得分 DESC", args).fetchall()
            if rows:
                lines.append(f"{p} {indicator}:" + "、".join(f"{a} {s}" for a, s in rows[:5]))
                src.append(f"capse.db / 指标得分 表,期次={p},指标={indicator}")

    # ── 问"哪项指标最高",但没点名是哪个指标 ────────────
    #    ※ 这一段是补的。补之前,这个问法【掉进了下面的综合得分分支】,
    #      答出来的是 4.23 —— 答案带着来源、格式漂亮、就是答非所问。
    #      静默答错,没人会看出来。这是第 6 个静默失败的样子。
    elif airport and re.search(r'指标', q):
        for p in ps:
            rows = con.execute(
                "SELECT 指标, 得分 FROM 指标得分 WHERE 期次=? AND 机场=? ORDER BY 得分 DESC",
                (p, airport)).fetchall()
            if rows:
                lines.append(f"{p} {airport} 各一级指标:" +
                             "、".join(f"{i} {s}" for i, s in rows))
                lines.append(f"  → 最高的是「{rows[0][0]}」{rows[0][1]},"
                             f"最低的是「{rows[-1][0]}」{rows[-1][1]}")
                src.append(f"capse.db / 指标得分 表,期次={p},机场={airport},共 {len(rows)} 项")

    # ── 前 N 名(没指定机场时才用) ─────────────────────
    elif not airport and re.search(r'前\s*(\d+)', q):
        k = int(re.search(r'前\s*(\d+)', q).group(1))
        for p in ps:
            rows = con.execute(
                "SELECT 排名, 机场, 得分 FROM 综合得分排名 WHERE 期次=? ORDER BY 排名 LIMIT ?",
                (p, k)).fetchall()
            if rows:
                lines.append(f"{p} 前 {k} 名:" + ";".join(f"第{r}名 {a} {s}" for r, a, s in rows))
                src.append(f"capse.db / 综合得分排名 视图,期次={p}(视图,不存数据)")

    # ── 综合得分:单机场按机场查,无机场则取全期排名 ────
    else:
        for p in ps:
            if airport:
                row = con.execute(
                    "SELECT 得分 FROM 综合得分 WHERE 期次=? AND 机场=?", (p, airport)).fetchone()
                rank = con.execute(
                    "SELECT 排名, 本期机场数 FROM 综合得分排名 WHERE 期次=? AND 机场=?",
                    (p, airport)).fetchone()
                if row:
                    lines.append(f"{p} {airport}:综合得分 {row[0]},排名第 {rank[0]}/{rank[1]}")
                    src.append(f"capse.db / 综合得分 表,期次={p},机场={airport}")
            else:
                rows = con.execute(
                    "SELECT 排名, 机场, 得分 FROM 综合得分排名 WHERE 期次=? ORDER BY 排名 LIMIT 5",
                    (p,)).fetchall()
                if rows:
                    lines.append(f"{p} 前 5 名:" + ";".join(f"第{r}名 {a} {s}" for r, a, s in rows))
                    src.append(f"capse.db / 综合得分排名 视图,期次={p}")
    return lines, src


# ══════════════════════════════════════════════════════════
#  执行层:走检索的题
# ══════════════════════════════════════════════════════════
def answer_search(con, q, k=3):
    """叙述型。返回 (命中的 chunk 列表, 来源列表, 实际用的查询词)。

    ═══ 这里补上了链子里原来缺的一环 ═══
        第 5 课验收之前,这一步是【把整句问句丢进去搜】:
            "报告的测评指标为什么调整过" → 0 条
        看起来像"知识库没有",其实是"检索方式不对"。四个原因叠在一起:
            整句短语匹配 / 词不对(调整 vs 变更) / 2 字词搜不了 / k 太小

        现在:先让大模型把问句改写成关键词,再【按空格拆开分别搜】。
        改写结果会一起返回,因为它必须能被人看见 ——
        不然"为什么搜出来是这几个"就又是一笔糊涂账。

    ═══ 检索这一路的来源是完整的 ═══
        chunk 自带期次和页码,能回到 PDF 的哪一页。
        对比 SQL 那一路只能给到表名 —— 这个不对称是第 5 课的第一个发现。
    """
    try:
        kw = rewrite_query(q)
    except LLMError as e:
        # 模型没连上,退回整句搜。会搜不到,但【是看得见的搜不到】,不是静默失败。
        kw = q
    hits = search_multi(con, kw, k=k)
    src = [f"{h['chunk_id']} = {h['期次']} 第 {h['页码']} 页" for h in hits]
    return hits, src, kw


# ══════════════════════════════════════════════════════════
#  组装层:把执行结果包成一个【必须带来源】的答案对象
# ══════════════════════════════════════════════════════════
def ask(con, q, airports, indicators):
    periods = find_periods(q)
    airport = find_airport(con, q, airports)
    indicator = find_indicator(q, indicators)

    where, flag, why = route(con, q, airports, indicators)

    out = {"问题": q, "去向": where, "答案": [], "来源": [], "标注": [],
           "警告": [], "备注": []}

    # 关键词表判不出 → 交给大模型重判一次,再走【同一条】后面的流程。
    #   ※ 不是"另起一条路",是"回到岔路口重新走" ——
    #     后面的可用性检查 / 跨口径检查,一个字都不用重写。
    if where == "判不出":
        try:
            a = judge_intent(q)
            if a in ("A", "B"):
                where, flag, why = route(con, q, airports, indicators, intent=a)
                out["去向"] = where
                out["备注"].append(
                    f"关键词表判不出 → 大模型判定「{'要数' if a == 'A' else '要话'}」")
            else:
                out["备注"].append("关键词表判不出 → 大模型也说拿不准")
        except LLMError as e:
            # 模型挂了,【保持判不出】,不猜。这是第 4 课那条:判不出看得见,判错看不见。
            out["备注"].append(f"★ 模型没连上({e}) —— 保持「判不出」,不猜")

    # 他定的规则②:跨口径必须说明
    if flag:
        out["标注"].append(why)

    if where == "拒答":
        out["答案"] = [f"不回答。{why}"]
        return out

    if where == "判不出":
        out["警告"].append("路由判不出这题要数还是要话 —— 不知道该查表还是翻文档")
        return out

    if where == "SQL":
        out["答案"], out["来源"] = answer_sql(con, q, periods, airport, indicator)
        if not out["答案"]:
            out["答案"] = ["库里没有匹配的数据(注意:这不同于'问得不对')"]
        return out

    # ── 检索 ────────────────────────────────────────
    hits, src, kw = answer_search(con, q)
    out["来源"] = src
    out["备注"].append(f"检索用词:{kw}")

    # ★ 0 条检索 ≠ 拒答 —— 两种不同的失败,不能共用一个去向。
    #
    #   口径(张君杰定的):"0 条检索属于检索失败;主动拒答属于模型在【有/无证据】条件下
    #   选择不回答。" 前者是"路走了没找到",后者是"我知道我不该答"。
    #
    #   ※ 为什么必须提成【字段】,不能只留在答案文本里:
    #     改之前它写作 ["没搜到相关内容"] —— 去向仍然是"检索"。
    #     于是任何按去向统计的东西,都会把【一次都没搜到】算进"检索成功"。
    #     文本不是字段,统计看不见它。这和"静默失败"是同一个病:
    #     出了事,但没有任何一个能被程序读到的地方记着它出过事。
    if not hits:
        out["去向"] = "检索·0条"
        out["答案"] = ["检索 0 条 —— 该走的路走了,没找到东西。这【不是】拒答,是检索失败。"]
    else:
        out["答案"] = [h["文本"][:120] + "…" for h in hits]

    # 第 4 课建的验证:走检索的题,回头看一眼这题真的该走检索吗
    warn = verify(con, q, periods, airport, hits)
    if warn:
        out["警告"].append(warn)
    return out


# ══════════════════════════════════════════════════════════
#  渲染层:把答案对象变成给人看的一段
# ══════════════════════════════════════════════════════════
def render(a):
    print(f"\n{'─' * 74}")
    print(f"问:{a['问题']}")
    print(f"〔去向〕{a['去向']}")
    if a["答案"]:
        print("〔答案〕")
        for line in a["答案"]:
            print(f"    {line}")
    if a["来源"]:
        print("〔来源〕")
        for s in a["来源"]:
            print(f"    · {s}")
    elif a["去向"] in ("SQL", "检索"):
        print("〔来源〕★ 空 —— 按规则,有答案就必须有来源,这个不该发出去")
    # ※ 拒答不要求来源 —— 它要的不是出处,是【理由】,理由在答案里。
    #   一开始我把拒答也标成"不该发出去",那是把规则用错了地方。
    for n in a["标注"]:
        print(f"〔标注〕{n}")
    for n in a["备注"]:
        print(f"〔过程〕{n}")
    for w in a["警告"]:
        print(f"〔警告〕★ {w}")


# ══ 验收用的一组问题 ═══════════════════════════════════
QUESTIONS = [
    "2025Q4 上海浦东国际机场的综合得分是多少",
    "2025Q4 的样本量是多少",
    "2025Q4 综合得分前 5 名是哪些机场",
    "2023Q3 和 2025Q4 的上海浦东,哪个分高",
    "2025Q4 上海浦东在 7 个一级指标里,哪项最高",
    "报告的测评指标为什么调整过",
    "2023 年删掉了哪些指标",
    "2024Q3 上海浦东国际机场的机场安检得分是多少",
    "2024年度报告里,全年得分最高的机场是哪个",
    "2025Q4上海浦东表现如何",
]


def main():
    con = sqlite3.connect(DB)
    airports = load_airports(con)
    indicators = load_indicators(con)

    for q in QUESTIONS:
        render(ask(con, q, airports, indicators))

    # ── 把"来源够不够"单独拉出来看 ──────────────────
    print(f"\n\n{'═' * 74}")
    print("═══ 本课第一个发现:两条路的【来源】完整程度不一样 ═══")
    n_src = n_nosrc = 0
    for q in QUESTIONS:
        a = ask(con, q, airports, indicators)
        if a["去向"] in ("SQL", "检索"):
            if a["来源"]:
                n_src += 1
            else:
                n_nosrc += 1
                print(f"  ★ 有答案但没有来源:{q}")
    print(f"\n  有来源 {n_src} 题 / 无来源 {n_nosrc} 题")
    print("""
  SQL 这一路的来源只能写到【表名】:
       capse.db / 综合得分 表,期次=2025Q4,机场=上海浦东国际机场
  用户拿着它,回不到 PDF 的哪一页去核。

  检索这一路是完整的:
       2025Q4-P19 = 2025Q4 第 19 页

  → 这不是代码写错了,是【第 1 课入库时没记页码】。
    张君杰那条"必须给来源"的规则,一句话就把这个缺口照出来了。""")
    con.close()


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    main()
