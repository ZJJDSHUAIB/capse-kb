# -*- coding: utf-8 -*-
r"""
第 9 课 · 第二节 · 机械扩充变体 —— 只做【不需要判断】的那一种。

═══ 为什么只做"去期次" ═══
    给一道题设计新问法,是【判断】:你得想"破坏哪一条假设"。那是张君杰的活。
    但"去期次"不是判断 —— 它就是一个固定动作:把期次词拿掉。谁做都一样。

    ★ 而它恰好是最有区分度的那一类:拿掉期次过滤之后,
      同一页的多个期次版本会【互抢前 k 名】—— 而两条路抢法不同。
      实测(题 45):关键词把答案排第 2,向量排第 6。**第一次出现「关键词对·向量错」。**

═══ 它做什么 ═══
    读 评估集 + 跑分.json,取【所有走检索的题】,对每一道:
        问法   = 去掉期次词
        检索词 = 去掉期次词
        期望   = 出处里的 chunk_id
    然后把它们【追加】到 docs/检索变体.tsv(不覆盖已有的行)。

    ⚠ 跳过两类,并把它们列出来(不静默丢):
        · 出处是"多版本"的题   —— 判据不同,期望不是一个 chunk_id
        · 问法里压根没有期次词 —— 去期次 = 原样,加了没意义

═══ 怎么用 ═══
    python tools/variant_expand.py
"""
import sys, io, re, json
from pathlib import Path
from paths import ROOT, DATA, PROCESSED, DOCS, DB, OUTPUT

sys.path.insert(0, str(Path(__file__).parent))

TSV = ROOT / "docs" / "检索变体.tsv"
PERIOD = re.compile(r"\d{4}Q\d")
MARK = "# ── 以下是 variant_expand.py 机械生成的行(去期次)──"


def strip_period(s):
    """去掉期次词,顺手把多余空格收一收。"""
    return re.sub(r"\s+", " ", PERIOD.sub("", s)).strip()


def idf_of(con, term):
    """这个词在库里出现在多少块里?★ 出现得越多 = 区分力越低。

    ★ 为什么用"出现在几块"当区分力:一个词如果每块都有,它就没法把任何一块挑出来。
      这就是 IDF 的朴素版本 —— 不需要什么公式,数一数就行。
    """
    return con.execute("SELECT COUNT(*) FROM chunk WHERE 文本 LIKE ?",
                       (f"%{term}%",)).fetchone()[0]


def main():
    from check_eval import read_rows, EVAL_IN
    import sqlite3

    con = sqlite3.connect(ROOT / "data" / "processed" / "capse.db")
    rows = read_rows(EVAL_IN)
    gots = json.loads((ROOT / "docs" / "评估集_跑分.json").read_text(encoding="utf-8"))

    made, skipped = [], []
    for r, g in zip(rows, gots):
        if g.get("去向") not in ("检索", "检索·0条"):
            continue
        cite = str(r.get("出处") or "")
        kws = [p.split(":", 1)[1].strip() for p in (g.get("过程") or []) if "检索用词" in p]
        if not kws:
            continue
        kw = kws[0]
        q = str(r.get("问题") or "")

        if "多版本" in cite:
            skipped.append((r["题号"], "出处是多版本,期望不是一个 chunk_id"))
            continue
        m = re.search(r"(\d{4}Q\d-P\d+)", cite)
        if not m:
            skipped.append((r["题号"], f"出处里没找到 chunk_id:{cite[:40]}"))
            continue
        want = m.group(1)

        if PERIOD.search(q):
            made.append((r["题号"], "机械·去期次", "破坏期次过滤(机械生成,无判断)",
                         strip_period(q), strip_period(kw), want))

        #  ★ 第二种机械扩充:只留【最独特】/【最普通】的那一个词。
        #    目的:直接检验"目标页有没有独一份的词"那条发现。
        #    ★ 挑哪个词不用判断 —— 数它在库里出现几次就行。
        terms = [t for t in kw.split() if len(re.sub(r"\W", "", t)) >= 3]
        if len(terms) >= 2:
            ranked = sorted(terms, key=lambda t: idf_of(con, t))
            lo, hi = ranked[0], ranked[-1]
            #  ⚠ 踩过的坑:期次词(如「2023Q3」)在 【chunk 文本里】出现 0 次
            #    (它印在期次那一列,不在正文里)。按"出现次数最少"排序,它会排第一,
            #    于是被标成"最独特的词" —— ★ 而"库里一次都没有"和"很独特"是两回事。
            #    ★★ 这和 merge_compare.py 里那条教训是同一个病:
            #       **把"不存在"说成了"排得靠后"。** 所以这里分开命名。
            made.append((r["题号"],
                         "机械·只留库里没有的词" if idf_of(con, lo) == 0 else "机械·只留最独特的词",
                         f"破坏'多个词一起用'(取出现 {idf_of(con, lo)} 次的词)",
                         q, lo, want))
            made.append((r["题号"], "机械·只留最普通的词",
                         f"破坏'多个词一起用'(取出现 {idf_of(con, hi)} 次的词)",
                         q, hi, want))

    if not made:
        print("★ 没生成任何行 —— 检查评估集是不是变了。")
        return

    txt = TSV.read_text(encoding="utf-8")
    #  ★ 重跑保护:【整段重建】而不是"追加没见过的"。
    #    为什么:改了生成规则(比如上面那个"库里没有的词"的命名)之后,
    #    "只追加新的"会把旧标签的行留在表里 —— 于是同一行出现两种说法。
    #    ★ 这和"向量文件过期了就重建"是同一个道理:派生出来的东西,
    #      要么跟着源头走,要么就会静默变旧。
    head = txt.split(MARK)[0].rstrip("\n")
    old_n = len([1 for ln in txt.splitlines()
                 if ln.count("\t") >= 5 and not ln.startswith("#")]) - \
            len([1 for ln in head.splitlines()
                 if ln.count("\t") >= 5 and not ln.startswith("#")])
    lines = [head, MARK] + ["\t".join(str(x) for x in m) for m in made]
    TSV.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"重建机械段:原来 {old_n} 行 → 现在 {len(made)} 行")
    print(f"  → {TSV}")
    print("\n机械生成的行:")
    for no, nm, what, q, kw, want in made:
        print(f"  {no:>3}  {nm:<20}{kw:<24} → {want}")
    if skipped:
        print(f"\n⚠ 跳过 {len(skipped)} 道(没静默丢,列在这里):")
        for no, why in skipped:
            print(f"  {no:>3}  {why}")


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    main()
