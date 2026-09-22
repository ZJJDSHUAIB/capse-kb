# -*- coding: utf-8 -*-
r"""
第 9 课 · 第二节 · 旋钮扫描 —— 把 merge_rank 的三个旋钮试一圈,看每个值塌在哪。

═══ 它解决什么 ═══
    你不需要改文件、不需要跑命令,只要看这张表里【哪一行的结果你认】。
    认了哪一行,就把那三个数填进 tools/my_merge.py 的参数表。

═══ ★★ 表里最要紧的不是"命中几个",是【塌在哪几行】 ═══
    两个组合可能都是 13/16,但塌的题不同 ——
    ★ 而"在哪一类问法下塌"才是判断依据,总数看不出来。

═══ 怎么用 ═══
    python tools/merge_sweep.py
"""
import sys, io, re, sqlite3
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from variant_test import load, PERIOD, K, ALL, DB
from my_merge import merge_rank

#  ★ 组合 = (关键词权重, 向量权重, 只看前几名)
COMBOS = [
    (1, 0, 0, "只用关键词(= 系统原来的样子)"),
    (0, 1, 0, "只用向量"),
    (1, 1, 0, "两边一样重"),
    (2, 1, 0, "更信关键词(2:1)"),
    (3, 1, 0, "很信关键词(3:1)"),
    (1, 2, 0, "更信向量(1:2)"),
    (1, 3, 0, "很信向量(1:3)"),
    (1, 1, 3, "两边一样重,但只看各自前 3 名"),
    (1, 1, 5, "两边一样重,但只看各自前 5 名"),
    (2, 1, 5, "更信关键词,只看各自前 5 名"),
]


def main():
    rows, _ = load()
    if not rows:
        print("★ 变体表是空的。")
        return
    from build_search import search_multi
    from vector_search import search_vec, load as load_vec

    con = sqlite3.connect(DB)
    load_vec(con)

    data = []          # [(题号, 变体名, 期望, kw_all, vec_all)]
    for r in rows:
        per = sorted(set(PERIOD.findall(r["问法"]))) or None
        kw_all = [str(h["chunk_id"]) for h in search_multi(con, r["检索词"], k=ALL, periods=per)]
        vec_all = [str(h["chunk_id"]) for h in search_vec(con, r["检索词"], k=ALL, periods=per)]
        data.append((r["题号"], r["变体"], r["期望"], kw_all, vec_all))
    N = len(data)

    from merge_variants import only_keyword, union_fill, intersect
    REF = [
        ("── 对照线(不是你的规则)──", None),
        ("  只关键词", lambda a, b: only_keyword(a, b, k=K)),
        ("  并集填位", lambda a, b: union_fill(a, b, k=K)),
        ("  交集", lambda a, b: intersect(a, b, k=K)),
        ("  向量单独", lambda a, b: b[:K]),
        ("── ★ 你的旋钮 ──", None),
    ]

    #  ★ 分组:机械生成的行(variant_expand.py 造的)和 AI 人工设计的行,【分开算】。
    #    为什么:机械那批全是"去期次",同质、而且是把条件人为调坏。
    #    ★★ 如果不分开,一批同质的行会把总分带偏 —— 那正是"一个数变好了先问它测的是什么"。
    grp = ["机械" if nm.startswith("机械·") else "人工" for _, nm, _, _, _ in data]
    idx = {"全部": list(range(N)),
           "人工": [i for i in range(N) if grp[i] == "人工"],
           "机械": [i for i in range(N) if grp[i] == "机械"]}

    print("=" * 108)
    print(f"  旋钮扫描   {N} 行(题 × 变体),k = {K}"
          f"   ——   人工 {len(idx['人工'])} 行 / 机械生成 {len(idx['机械'])} 行")
    print("=" * 108)
    print(f"  {'组合':<34}{'全部':>7}{'人工':>8}{'机械':>8}{'剔除6行':>9}   ★ 塌在哪几行(题·变体)")
    print("  " + "-" * 104)

    allbad = {}          # 组合名 → 塌的行;用来最后找"谁都过不了"的行
    oks = {}             # 组合名 → 每一行的 True/False

    def report(label, fn):
        seqs = [fn(a, b) for _, _, _, a, b in data]
        ok = [all(w in s for w in want) for (_, _, want, _, _), s in zip(data, seqs)]
        oks[label] = ok
        allbad[label] = [f"{no}·{nm}" for (no, nm, _, _, _), o in zip(data, ok) if not o]
        cells = []
        for g in ("全部", "人工", "机械"):
            ids = idx[g]
            cells.append(f"{sum(ok[i] for i in ids)}/{len(ids)}")
        return cells

    ITEMS = []
    for label, fn in REF:
        ITEMS.append((label, fn))
    for w_kw, w_vec, cut, note in COMBOS:
        label = f"  {w_kw}:{w_vec}" + (f" 只看前{cut}" if cut else "") + f"  {note}"
        ITEMS.append((label, lambda a, b, kw=w_kw, vv=w_vec, c=cut:
                      merge_rank(a, b, k=K, 关键词权重=kw, 向量权重=vv, 只看前几名=c)))

    #  ── 第一遍:只算,不打印 ──
    #  ★ 为什么要两遍:"剔除那几行"的那一列,必须先知道【哪几行】才能算。
    #    而"哪几行"要等所有组合都跑完才知道。所以先全算出来,再统一印。
    calc = []
    for label, fn in ITEMS:
        if fn is None:
            calc.append((label, None, None))
            continue
        seqs = [fn(a, b) for _, _, _, a, b in data]
        ok = [all(w in s for w in want) for (_, _, want, _, _), s in zip(data, seqs)]
        calc.append((label, ok, [f"{no}·{nm}" for (no, nm, _, _, _), o in zip(data, ok) if not o]))

    #  ── 找出"所有组合都塌"的行 ──
    #  ★★ 那些行【不是规则的锅,是尺子的锅】:每一种问法都过不了 → 它谁也救不了。
    #     留着(让"有些问法谁也救不了"这件事可见),但【单列一栏】把它的影响摘出去。
    #     ★ 这和告警那条口径是同一套思路:出声归告警率,答对归正确率 ——
    #       让一件事可见,和让它影响结论,是两回事。
    allok = [ok for _, ok, _ in calc if ok is not None]
    every = {i for i in range(N) if all(not ok[i] for ok in allok)}

    #  ── 第二遍:打印 ──
    for label, ok, bad in calc:
        if ok is None:
            print(f"\n  {label}")
            continue
        cells = [f"{sum(ok[i] for i in idx[g])}/{len(idx[g])}" for g in ("全部", "人工", "机械")]
        keep = [i for i in range(N) if i not in every]
        cells.append(f"{sum(ok[i] for i in keep)}/{len(keep)}")
        print(f"  {label:<34}{cells[0]:>7}{cells[1]:>8}{cells[2]:>8}{cells[3]:>9}"
              f"  {'、'.join(bad) if bad else '(全过)'}")

    print("\n" + "=" * 108)
    print(f"  ★★ 所有组合都塌的行(共 {len(every)} 行) —— 这些【不是规则的锅,是尺子的锅】")
    print("=" * 108)
    if every:
        for i in sorted(every):
            no, nm = data[i][0], data[i][1]
            print(f"     {no}·{nm}")
        print(f"""
     ★ 处理方式(已执行):【留着, 但单列一栏】。
       · 留着  —— 它们说明"有些问法谁也救不了",这本身是结论
       · 单列  —— "剔除那 {len(every)} 行"是同一批数据摘掉它们之后的分数
       ★ 理由和告警那条口径一样:让一件事【可见】,和让它【影响结论】,是两回事。
""")
    else:
        print("     (没有 —— 每一种问法至少有一个组合能过)")

    print("""
  ★ 怎么读这张表:
      ① 先看「人工」和「机械」两列【是不是一致】。
         ★ 如果不一致,说明总分被同质的那一批带偏了 —— 那要看"人工"那一列。
      ② 再看「塌在哪几行」—— 不看总数。两个组合可能一样多,
         但一个塌在"基准"、一个塌在"去掉期次",那是两回事。
      ③ 1:0 和 0:1 是两个极端(只用一条路)。你的规则打不过它们 = 合并净亏,
         ★ 那也是合格的结果,不是失败,是"不该合"。
      ④ 认了哪一行,把那三个数填进 tools/my_merge.py 的参数表。
""")


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    main()
