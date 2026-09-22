# -*- coding: utf-8 -*-
r"""
第 9 课 · 第二节 · 变体测试 —— 【同一道题 × 多种问法 × 各种合并方式】

═══ 为什么不能"在 60 道上量四种走法就完事" ═══
    有人问过一个关键问题(而且是对的):

        "怎么合是需要通过实验来验证的吗?
         那仅仅是针对这个评估集的哦,要考虑多种情况来测试才对吧"

    ★ 同一批题【既用来选、又用来判】—— 那个分数测的是
      "我有多了解这 60 道题",不是"这个方法行不行"。

    ★★ 而且那 60 道题【已经全看过了】:
       第 7 课一道道读过、画过 K 曲线、按《失败地图》押过预期、重写过 39 号的答案键。
       → 标准的「留出法」已经用不了了:留着没看过的题,没有了。

    → 只能造【新的】东西。而最便宜的新东西不是新题,是
      **同一道题的新问法** —— 答案不变,只有问法变。

═══ ★ 这个文件【不重写】合并方式 ═══
    合并规则在 my_merge.py(张君杰的判断)+ merge_variants.py(三条对照线)。
    这里只做一件事:**把它们换一批问法再跑一遍。**
    ★ 判据、口径、条件写法沿用 merge_compare.py —— 换了尺子就没法跟上一轮比。

═══ ⚠⚠ 一条我这轮踩到的坑(它本身就是个发现)═══
    我第一版把【整句问句】直接喂给 search_multi(关键词检索),结果 ——

        2024Q2的著作权声明说了什么   →   命中 0 条

    ★ 为什么:
        search_multi() 按【空格】拆词,每个词再走 trigram 短语匹配。
        整句中文没空格 → 被当成【一个超长的词】→
        trigram 要求这一整串字在原文里挨着出现 → 0 条。

    ★★ 而真系统从不这么干:大模型先把问句改写成【空格分开的检索词】,
       检索词再进 search_multi。所以:
       **本表的「检索词」列才是实际进检索的东西,「问法」列是给人看的。**

    ★★★ 而这一坑牵出一个更值钱的事实 —— #51 系统实际用的检索词是:

        2024Q2 著作权声明 版权声明

       **近义词「版权声明」【大模型自己已经加上了】,关键词检索照样找不到。**
       因为关键词只会去找「版权声明」这四个字本身 ——
       它不知道「版权声明」和原文写的「法律声明」是一回事。
       ★ 所以"给关键词喂近义词"这件事【在机制上就是无效的】。
         (这也是第 7 课那次"补近义词 prompt 过拟合"的机制层解释。)

═══ 怎么用 ═══
    表在 docs/检索变体.tsv,由张君杰填。一行 = 一个 (题号, 变体)。

═══ ★★★ 怎么看结果 ═══
    不看平均分,看【最差的那一格】。

        一种走法平均 8/10,但某一种问法下直接掉到 0  →  那是脆的
        ★ 而静默失败最喜欢的就是"脆" —— 因为脆的东西平时不响。
"""
import sys, io, re, sqlite3, hashlib
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

ROOT = Path(r"D:\capse-kb")
TSV  = ROOT / "docs" / "检索变体.tsv"
DB   = ROOT / "data" / "processed" / "capse.db"
VEC  = ROOT / "data" / "processed" / "capse_vectors.npz"

K   = 5          # ★ 系统实际生效的 k(ask.py 里传的 5)
ALL = 100000     # "要全部" —— 才能看到正确页的【真实名次】,而不是"没进前5"
PERIOD = re.compile(r"\d{4}Q\d")


def md5(p):
    return hashlib.md5(Path(p).read_bytes()).hexdigest()[:10]


def load():
    """读变体表。★ 读不完整就报出来,别跑出一个空结果还说"全过"。"""
    rows, skipped = [], []
    for ln in TSV.read_text(encoding="utf-8").splitlines():
        s = ln.strip()
        if not s or s.startswith("#"):
            continue
        p = [c.strip() for c in s.split("\t")]
        if len(p) < 6 or p[0] == "题号":
            continue
        if not p[4] or not p[5]:
            skipped.append(s[:70])
            continue
        rows.append(dict(题号=p[0], 变体=p[1], 破坏什么=p[2],
                         问法=p[3], 检索词=p[4],
                         期望=[x for x in p[5].split("|") if x]))
    return rows, skipped


def cond_block(rows):
    """条件块 —— 脚本自己吐。★ 手写的条件会和代码脱钩,而脱钩了没人知道。"""
    L = []
    L.append(f"跑的时间        {datetime.now():%Y-%m-%d %H:%M:%S}")
    L.append("")
    L.append("── 输入(md5 钉在这里,用来回答'这是哪一次跑的') ──")
    L.append(f"  库            capse.db            md5={md5(DB)}")
    L.append(f"  向量文件      capse_vectors.npz   md5={md5(VEC)}")
    L.append(f"  变体表        检索变体.tsv        md5={md5(TSV)}   ← ★ 这一变,结果全变")
    L.append("")
    L.append("── 代码 ──")
    for f in ("build_search.py", "vector_search.py", "merge_variants.py", "my_merge.py"):
        star = "   ← ★ 这一行是你的判断,你一改它就变" if f == "my_merge.py" else ""
        L.append(f"  {f:<22} md5={md5(ROOT / 'tools' / f)}{star}")
    L.append("")
    L.append("── 口径 ──")
    L.append(f"  K              {K}(ask.py 实际生效的值);名次另取全库,才能看到真实名次")
    L.append("  期次过滤       开 —— 从【问法】里抽期次。★ 变体故意去掉期次词,过滤就随之关掉")
    L.append("  喂给检索的是   ★「检索词」那一列,不是「问法」—— 见文件头那条坑")
    L.append("  判据           答案键那一页在【该方式实际给出去的条里】→ 算命中")
    L.append("                 (★ 不按前 K 判:并集取前k 按定义就不受 k 约束,")
    L.append("                  用 k 去量它等于要求它把多给的第 6、7 条扔了再算)")
    L.append(f"  变体行数       {len(rows)}   ({len(set(r['题号'] for r in rows))} 道题)")
    return L


def main():
    rows, skipped = load()
    if not rows:
        print("★ 变体表是空的 —— 先把 docs/检索变体.tsv 填了。")
        return

    from build_search import search_multi
    from vector_search import search_vec, load as load_vec
    from my_merge import merge_rank
    import merge_variants

    con = sqlite3.connect(DB)
    load_vec(con)

    #  ★ 列 = 三条对照线 + 「向量单独」+ 「★ 你的」
    #    「向量」不是合并方式,是一条路 —— 但必须摆在一排比,否则看不出合并值不值。
    COLS = list(merge_variants.VARIANTS) + ["向量", "★ 你的"]

    res = {}
    for r in rows:
        per = sorted(set(PERIOD.findall(r["问法"]))) or None
        kw_all  = [str(h["chunk_id"]) for h in search_multi(con, r["检索词"], k=ALL, periods=per)]
        vec_all = [str(h["chunk_id"]) for h in search_vec(con, r["检索词"], k=ALL, periods=per)]
        seqs = {name: [str(c) for c in fn(kw_all, vec_all, k=K)]
                for name, fn in merge_variants.VARIANTS.items()}
        seqs["向量"]   = vec_all[:K]
        seqs["★ 你的"] = [str(c) for c in merge_rank(kw_all, vec_all, k=K)]
        res.setdefault(r["题号"], []).append(
            (r["变体"], r["破坏什么"], r["检索词"], r["期望"], seqs))

    def hit(seq, want):
        return all(w in seq for w in want)

    def rk(seq, want):
        """名次(1 起)。★ 没命中给 None —— 「没进前k」和「全库都没有」不是一回事。"""
        return seq.index(want[0]) + 1 if want[0] in seq else None

    #  ★ 全表摊平,后面逐题和汇总都用它 —— 一处算,两处用,不会打架。
    flat = [(no, nm, what, kw, want, seqs)
            for no, vs in res.items() for nm, what, kw, want, seqs in vs]
    N = len(flat)

    L = cond_block(rows)
    if skipped:
        L.append("")
        L.append(f"  ⚠ {len(skipped)} 行被跳过(检索词或期望是空的): {skipped}")

    # ────────── 逐题 ──────────
    for no, vs in res.items():
        L.append("")
        L.append("=" * 100)
        L.append(f"  题 {no}   ({len(vs)} 个变体)")
        L.append("=" * 100)
        L.append(f"  {'变体':<18}{'实际喂给检索的词':<36}" + "".join(f"{c:<11}" for c in COLS))
        L.append("  " + "-" * 96)
        for nm, what, kw, want, seqs in vs:
            cells = []
            for c in COLS:
                if hit(seqs[c], want):
                    cells.append("✅ 命中    ")
                elif not seqs[c]:
                    cells.append("·  空      ")      # ★ "给了个空集" ≠ "没命中",要分开
                else:
                    r = rk(seqs[c], want)
                    cells.append(f"❌ 第{r}名  " if r else "❌ 全库没  ")
            L.append(f"  {nm:<18}{kw[:34]:<36}" + "".join(f"{c:<11}" for c in cells))
            L.append(f"  {'':<18}↳ 它在破坏:{what[:26]:<26}"
                     f" 答案键 {('+'.join(want))}")
        n = len(vs)
        L.append("  " + "-" * 96)
        L.append(f"  {'命中数':<18}{'共 ' + str(n) + ' 个变体':<36}"
                 + "".join(f"{sum(1 for *_, s in vs if hit(s[c], vs[0][3]))}/{n}".ljust(11)
                           for c in COLS))

    # ────────── 总汇总 ──────────
    L.append("")
    L.append("=" * 100)
    L.append(f"  总汇总   {N} 行(题 × 变体)")
    L.append("=" * 100)
    L.append(f"  {'走法':<12}{'命中':<12}{'平均给几条':<14}{'★ 有变体让它掉到 0 吗'}")
    L.append("  " + "-" * 92)
    for c in COLS:
        h = sum(1 for _, _, _, _, w, s in flat if hit(s[c], w))
        avg = sum(len(s[c]) for *_, s in flat) / N
        zero = sum(1 for _, _, _, _, w, s in flat if not hit(s[c], w))
        L.append(f"  {c:<12}{f'{h}/{N}':<12}{f'{avg:>4.1f} 条':<14}"
                 f"{('★ 有 ' + str(zero) + ' 行') if zero else '没有'}")

    L.append(f"""
  ★ 怎么读:
       ① 横向看一行(一个变体):哪些走法在这一种问法下活下来了
       ② 纵向看一列(一种走法):★★★ 它在多少种问法下活着 —— 最差的那一格才是它的成色
       ③ 「向量」那一列是【一条路】不是合并方式,它在这里的作用是当尺子:
          ★ 如果合并后的最好成绩还不如"向量单独",那这次合并就是白做的。
       ④ "·  空" 和 "❌" 是两回事:
          空 = 这一路压根没给出候选(比如交集两路没重合);
          没命中 = 给了候选,但答案不在里面。**前者是"没意见",后者是"看错了"。**
""")

    text = "\n".join(L)
    print(text)
    out = ROOT / "docs" / "第9课_变体测试.txt"
    out.write_text(text, encoding="utf-8")
    print(f"  ✅ 存到 {out}")


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    main()
