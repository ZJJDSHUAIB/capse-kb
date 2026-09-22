# -*- coding: utf-8 -*-
r"""
第 7 课 · 造挑战集。

═══ 它为什么必须存在 ═══
    我给「硬限定词」写了一条规则(route.py 的 LIMIT),然后在同一套 60 题上量出
    "3 真 0 假 = 100%" —— **那是个不能信的数**:
    我是先看到 #48 #51 #52 才想出那条规则的。**那不叫"规则",那叫"记住答案"。**

    要分清楚,只有一条路:**拿一批【没参与设计】的题去撞。**
    这就是挑战集。

═══ 它的判据为什么是硬的 ═══
    期望答案不来自我的判断,来自数据库:

        正确的那一页(X)在不在系统取到的来源里?

        X ∈ 来源  且 报警   →  ★ 误报
        X ∈ 来源  且 不报   →  ✅ 正常
        X ∉ 来源  且 报警   →  ✅ 命中
        X ∉ 来源  且 不报   →  ★ 漏报(静默)

    **它只比对 chunk_id,完全不看我那条 LIMIT 规则。**
    → 所以"我的规则有没有过拟合",这个判据答得了。

═══ 三部分 ═══
    A  限定词【在库里】(正确页里含它)      → 该取到那一页
    B  限定词【不在库里】(把它改成一个不存在的值) → 该报警
    C  SQL 那条路的软肋                      → 手工模板 + 库里参数

═══ 怎么保证"没参与设计" ═══
    ① 数据从库里【随机】取(种子固定,可复现)
    ② 限定词从【那一页的真实文本】里抽,不由我编
    ③ 我只提供【问句模板】—— 模板是"形状",不是"答案"
"""
import sys, io, re, json, random, sqlite3
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

DB = Path(r"D:\capse-kb\data\processed\capse.db")
OUT = Path(r"D:\capse-kb\docs\挑战集.xlsx")
SEED = 20260918          # 固定种子 —— 可复现,而且我事先不知道抽到哪些

# ── 从一页文本里抽"限定词"候选 ─────────────────────────
#   ※ ⚠ 这里【故意】不照着 LIMIT 的形状抽,而是抽得比它宽 ——
#     要测的正是"LIMIT 认不出来的那些",所以候选必须比 LIMIT 大。
#     如果只抽 LIMIT 认得的,这个集就测不出任何东西。
CAND = [
    re.compile(r'\d+万\s*[-~]\s*\d+万'),
    re.compile(r'\d+万级以上|\d+万级'),
    re.compile(r'[一-鿿]{2,6}声明'),
    re.compile(r'[一-鿿]{2,6}简介'),
    re.compile(r'CAPSE'),
]
#  ⚠ 这里【只留通顺的形状】。原来还有「XXXX指数|率|值|系统|指标」那一类,
#    它生出了一堆半句话(「到多指数」「致力成为值」)。
#    删它不是为了"让规则好过",是因为【成题不像人话】——
#    一条"筛人话"的规矩可以;一条"筛我的规则能不能过"的规矩不可以。
#
#  ⚠⚠ 但要如实说清这带来的局限:
#    **这五类形状,和我那条 LIMIT 规则认得的形状【是同一批】。**
#    所以这个挑战集测的是【参数泛化】(新期次、新数字档位),
#    **测不了【形状泛化】** —— 那要靠 C 部分(它的软肋是结构,不是形状)。

# ── 问句模板:形状固定,参数随机 ─────────────────────────
TEMPLATES = [
    "{per}的{lim}是什么",
    "{per}里,{lim}是多少",
    "{per}的{lim}说的是什么",
    "{per}报告中{lim}的内容是什么",
]


# ══ ★ 专有性门槛 ══════════════════════════════════════════
#  第一版没这道门槛,生出了一批【到处都有】的词当限定词:
#      「CAPSE」在库里 50/54 页出现过 —— 它根本不构成"限定"。
#      拿它当判据,检查永远不报;而那不是"检查失效",是【这个词没有区分力】。
#
#  ※ 这跟"规则过拟合"是两码事。第一版跑出 3 道静默,我差点当成规则漏报 ——
#    查了才发现是题出得不好。**判据先得问一句:这个限定词够专有吗?**
#  ※ 门槛是【量出来的】,不是我拍的:实测三个真限定词(4000万级以上 /
#    1000万-1500万 / 2500万-4000万)在库里都是 【1/54 页】。
MAX_PAGES = 3


def distinctive(con, w):
    """这个词在库里出现几页?超过 MAX_PAGES 就不算限定。"""
    return con.execute("SELECT COUNT(*) FROM chunk WHERE 文本 LIKE ?", (f'%{w}%',)).fetchone()[0] <= MAX_PAGES


def pick_limits(con, text, rnd, n=1):
    """从一页的真实文本里抽限定词候选。

    ⚠ 必须过【边界检查】—— 第一版没这道检查,生出来一堆半句话:
        「整优化测评指标」「到多指数」  ← 正则从句子中间往回啃了
      检查:候选的【前一个字】不能是汉字(除非在行首)。
      这一条不针对任何具体的词,是针对"一个词该有边界"这个结构。
    """
    out = []
    for pat in CAND:
        for m in pat.finditer(text):
            x = m.group(0).strip()
            if not (2 <= len(x) <= 14) or x in out:
                continue
            i = m.start()
            if i > 0 and re.match(r'[一-鿿]', text[i - 1]):
                continue                      # 前面还连着汉字 → 是从句子中间啃下来的
            if x.endswith('的') or x.startswith('的'):
                continue
            if not distinctive(con, x):      # ★ 到处都有的词,当不了限定词
                continue
            out.append(x)
    rnd.shuffle(out)
    return out[:n]


def fake(x):
    """把限定词改成一个【库里不存在】的值(B 部分用)。"""
    m = re.match(r'(\d+)万', x)
    if m:
        return f"{int(m.group(1)) + 700}万"      # 抬到一个不存在的档
    if x.startswith("CAPSE"):
        return "CASPE"
    return "ZZ" + x[:4]


def main():
    rnd = random.Random(SEED)
    con = sqlite3.connect(DB)
    # 只挑【叙述页】里的长文本 —— 短页抽不出限定词
    rows = con.execute(
        "SELECT chunk_id, 期次, 页码, 文本 FROM chunk "
        "WHERE 字符数 > 150 ORDER BY chunk_id").fetchall()
    print(f"库里可用的页:{len(rows)} 页")

    A, B = [], []
    pool = rows[:]
    rnd.shuffle(pool)
    for cid, per, pg, text in pool:
        if len(A) >= 14 and len(B) >= 14:
            break
        lims = pick_limits(con, text, rnd, 1)
        if not lims:
            continue
        lim = lims[0]
        tpl = TEMPLATES[rnd.randrange(len(TEMPLATES))]
        if len(A) < 14:
            q = tpl.format(per=per, lim=lim)
            A.append({"类别": "挑战A·限定词在库里", "问题": q,
                      "期望说明": f"限定词「{lim}」在 {cid} 里,那一页该被取到",
                      "正确页": cid, "期次": per, "页码": pg})
        if len(B) < 14:
            flim = fake(lim)
            if flim != lim:
                q = tpl.format(per=per, lim=flim)
                B.append({"类别": "挑战B·限定词不在库里", "问题": q,
                          "期望说明": f"限定词「{flim}」库里一页都没有 —— 系统该报警",
                          "正确页": "", "期次": per, "页码": pg})
    # ── C:SQL 那条路的软肋(模板固定,参数从库里取)──
    airports = [r[0] for r in con.execute(
        "SELECT 机场 FROM 综合得分 WHERE 期次='2025Q4' ORDER BY 得分 DESC")]
    top5 = set(airports[:5])
    low = [a for a in airports if a not in top5]        # 挑【不在前 5】的,让"前5名"盖不住
    C = []
    short = lambda a: a.replace("国际机场", "").replace("机场", "")
    # C3:用户用简称说两个【都不在前5名】的机场
    for i in range(3):
        a1, a2 = low[rnd.randrange(len(low))], low[rnd.randrange(len(low))]
        if a1 == a2:
            continue
        C.append({"类别": "挑战C3·简称认不出", "问题": f"2025Q4{short(a1)[-2:]}和{short(a2)[-2:]}的得分分别是多少",
                  "期望说明": f"用户用简称说了「{short(a1)[-2:]}」「{short(a2)[-2:]}」两个机场,"
                              f"系统该答这两个的得分({a1} / {a2}),不许答成「前5名」",
                  "正确页": "", "期次": "2025Q4", "页码": ""})
    # C1:限定条件被忽略
    for lim in ["靠桥率", "行李服务", "旅客满意度", "净推荐值"]:
        C.append({"类别": "挑战C1·限定被忽略",
                  "问题": f"2025Q4上海浦东国际机场的{lim}排名第几",
                  "期望说明": f"「{lim}」要么不在库里、要么不是 2025Q4 的指标 —— "
                              f"系统【不该】答成「综合得分排名」",
                  "正确页": "", "期次": "2025Q4", "页码": ""})
    # C2:机场认不出
    for name in ["合肥骆岗机场", "上海龙华机场", "北京南苑机场"]:
        C.append({"类别": "挑战C2·机场认不出",
                  "问题": f"2025Q4{name}综合得分是多少",
                  "期望说明": f"「{name}」不在库里 —— 系统不该答成「全期前5名」",
                  "正确页": "", "期次": "2025Q4", "页码": ""})

    allrows = A + B + C
    print(f"  A {len(A)} 道 / B {len(B)} 道 / C {len(C)} 道  合计 {len(allrows)}")
    Path(r"D:\capse-kb\docs\_挑战集.json").write_text(
        json.dumps(allrows, ensure_ascii=False, indent=1), encoding="utf-8")
    for r in allrows:
        print(f"  [{r['类别']}] {r['问题']}")
    print(f"\n写到 docs\\_挑战集.json")


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    main()
