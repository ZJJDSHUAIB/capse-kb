# -*- coding: utf-8 -*-
r"""
第 9 课 · 第二节 · 量具:关键词 / 向量 / 合并,在【同一批题、同一个 k】下各把正确页排到第几?

═══ 它回答的问题 ═══
    第一节量的是"正确页在不在前 5"(是/否)。
    这一节量的是"正确页排第几"(名次)。

    ★ 为什么名次比"在不在"值钱:
      "在不在前5"是【一个是非题】,它把第 1 名和第 5 名当成一回事。
      而合并要做的正是【排序】—— 排序这件事,只有名次看得见。

═══ ★★ 先说清一件事:并集和交集不是"实验结果" ═══
        并集  命中率【必然】≥ 两条路各自
        交集  命中率【必然】≤ 两条路各自

    这不是数据说的,是【集合运算的性质】。所以这两个数【没有信息量】——
    它们只说明"多拿一定不会更少命中"和"少拿一定不会更多命中",是废话。

    ★ 真正的问题是:【k 不变】的时候,谁在前 k 名。
      而并集想不变大,就只能排序;两种分数又不可比 → 只能按名次排。
      所以"交集/并集"真正的对照意义是:
          交集 = "丢了东西值多少"
          并集 = "多拿了东西值多少"(第 7 课量过:多拿的既可能是答案,也可能是噪音)

═══ 条件写在结果旁边 ═══
    输出文件开头有一段【脚本自己吐出来的】条件块:库 md5 / 向量 md5 /
    答案键 md5 / 检索词从哪来 / K / 期次过滤规则 / 判据 / 代码 md5 / 跑的时间。
    ★ 不是我手写在一旁 —— 手写的条件会和代码脱钩,而脱钩了没人知道。
      项目规矩第 ⑧ 条:凡是读一个"跑出来的文件",先确认它是【哪一次】跑的。
      所以这里把每个输入文件的 md5 都钉在结果头上。

═══ ⚠ 这把尺子只够得着 14 道题 ═══
    60 道里只有 15 道走检索,其中 14 道有单页答案键。
    所以【检索层的数不能代表系统】—— 它只告诉你"机制动没动"。
    要说用户受不受益,必须看端到端总分(python tools/score_eval.py)。
    ★ 第 7 课的教训:期次过滤把"污染率 37%→0"变成一场大胜,实际只修好 2 道题。
      过程指标夸大了 7.5 倍。**两把尺子都要看,而且先看端到端。**
"""
import sys, io, re, json, sqlite3, hashlib
from pathlib import Path
from datetime import datetime
from paths import ROOT, DATA, PROCESSED, DOCS, DB, OUTPUT

sys.path.insert(0, str(Path(__file__).parent))

DB       = ROOT / "data" / "processed" / "capse.db"
VEC      = ROOT / "data" / "processed" / "capse_vectors.npz"
EVAL_IN  = ROOT / "docs" / "评估集.xlsx"
RUN_JSON = ROOT / "docs" / "评估集_跑分.json"
OUTDIR   = ROOT / "docs"

K   = 5          # ★ 系统实际生效的 k(ask.py 里传的 5)
ALL = 100000     # "要全部" —— 传个大数,才能看到正确页的【真实名次】,而不是"没进前5"


def md5(p):
    return hashlib.md5(Path(p).read_bytes()).hexdigest()[:10]


def _t(p):
    return f"{datetime.fromtimestamp(Path(p).stat().st_mtime):%m-%d %H:%M}"


def cond_block(con, tag, n_single, n_multi):
    """条件块 —— 脚本自己吐,不手写。"""
    from vector_search import load
    ids, vecs = load(con)      # ← 顺手触发"库变了就重建",保证向量和库对得上

    L = []
    L.append(f"轮次            {tag}")
    L.append(f"跑的时间        {datetime.now():%Y-%m-%d %H:%M:%S}")
    L.append(f"跑了几次        1   (这四条路线都是确定性的 —— 同一题跑两次结果逐字相同;"
             f"下一节做 agent 时这把尺子就不够了)")
    L.append("")
    L.append("── 输入(每个文件的 md5 钉在这里,用来回答'这是哪一次跑的') ──")
    L.append(f"  库            capse.db             md5={md5(DB)}   {_t(DB)}")
    L.append(f"  向量文件      capse_vectors.npz    md5={md5(VEC)}   {_t(VEC)}   "
             f"{len(ids)} 块 × {vecs.shape[1]} 维")
    L.append(f"  答案键        评估集.xlsx           md5={md5(EVAL_IN)}   {_t(EVAL_IN)}")
    L.append(f"  检索词来源    评估集_跑分.json       md5={md5(RUN_JSON)}   {_t(RUN_JSON)}"
             f"   ← ★ 它是【哪一次】跑的,就是这一行")
    L.append("")
    L.append("── 代码 ──")
    for f in ("build_search.py", "vector_search.py", "my_merge.py"):
        star = "   ← ★ 这一行是你的判断,你一改它就变" if f == "my_merge.py" else ""
        L.append(f"  {f:<22} md5={md5(ROOT / 'tools' / f)}{star}")
    L.append("")
    L.append("── 口径(数字怎么算出来的) ──")
    L.append(f"  K              {K}(ask.py 实际生效的值)。名次表另取全库,才能看到真实名次")
    L.append("  期次过滤       开 —— 问句里出现 2024Q2 这类期次才生效;没出现就【不过滤】")
    L.append("                 (第 7 课定的规矩:空集是有意不过滤,不是漏了)")
    L.append("  检索词         用系统【实际用过】的词(取自上面那个 跑分.json),不是我另写的")
    L.append("  判据·单页题    答案键里的 chunk_id 出现在结果前 K 名 → 算命中")
    L.append(f"  判据·多版本题  判据不同(要看分界两边),单独列,不混进命中率 —— 共 {n_multi} 道")
    L.append("  合并按什么排   ★ 名次,不是分数 —— BM25 是负数、余弦是 0~1,两种分数不可比")
    L.append("  分母           " + str(n_single) + " 道(走检索且有单页答案键的题)")
    return L


def main():
    tag = sys.argv[1] if len(sys.argv) > 1 else "未命名轮"

    from check_eval import read_rows
    from build_search import search_multi
    from vector_search import search_vec, load
    from my_merge import merge_rank
    import merge_variants

    rows = read_rows(EVAL_IN)
    gots = json.loads(RUN_JSON.read_text(encoding="utf-8"))
    con = sqlite3.connect(DB)
    load(con)

    single, multi, no_key = [], [], []
    for r, g in zip(rows, gots):
        if g.get("去向") not in ("检索", "检索·0条"):
            continue
        cite = str(r.get("出处") or "")
        kws = [p.split(":", 1)[1].strip() for p in (g.get("过程") or []) if "检索用词" in p]
        if not kws:
            continue
        kw = kws[0]
        per = sorted(re.findall(r'\d{4}Q\d', str(r.get("问题") or ""))) or None

        # ★ str() 一下:向量的 id 从 .npz 读出来是 numpy 的字符串类型,
        #   直接打印会长成 np.str_('2025Q4-P24') —— 值没错,但没人想读那个。
        kw_all  = [str(h["chunk_id"]) for h in search_multi(con, kw, k=ALL, periods=per)]
        vec_all = [str(h["chunk_id"]) for h in search_vec(con, kw, k=ALL, periods=per)]
        merged  = [str(c) for c in merge_rank(kw_all, vec_all, k=K)]
        # ★ 所有合并方式一起算 —— 这样它们在【同一批题、同一个 k】下比,
        #   而不是"今天量这条、明天量那条"(那种数不能比)。
        ways = {name: [str(c) for c in fn(kw_all, vec_all, k=K)]
                for name, fn in merge_variants.VARIANTS.items()}
        ways["★ 你的"] = merged

        if "多版本" in cite:
            pg = re.search(r'页码=(\d+)', cite)
            multi.append((r["题号"], int(pg.group(1)) if pg else None, kw_all, vec_all, merged))
            continue
        m = re.search(r'(\d{4}Q\d-P\d+)', cite)
        if not m:
            no_key.append((r["题号"], kw, cite))
            continue
        single.append((r["题号"], m.group(1), kw, per, kw_all, vec_all, merged, ways))

    def rank(seq, want):
        """名次从 1 数。没命中给 None —— 注意【没命中】和【排第 40】不是一回事。"""
        return seq.index(want) + 1 if want in seq else None

    # ★ 两列的"没找到"意思【不一样】,措辞必须分开 ——
    #   关键词/向量那两列是【全库排名】,找不到 = 那条路压根没把它排进来;
    #   合并那一列是【前 k 条】,找不到 = 没进前 k,而它可能在库里排第 6。
    #   ⚠ 我第一版两列都写"全库都没命中" → 题 52 被显示成"库里没有",
    #     而它其实排第 6。**这不是笔误,是把"没选上"说成了"不存在"。**
    def show(rk, missing="全库都没命中"):
        if rk is None:
            return " " + missing
        return f"第{rk:>2}名 {'✅' if rk <= K else '✗ '}"

    def cell(seq, want, missing="全库没命中"):
        """表里用的窄版。名次 + 进没进前 k。"""
        rk = rank(seq, want)
        if rk is None:
            return missing
        return f"第{rk}名" + ("✅" if rk <= K else "✗")

    n = len(single)
    L = cond_block(con, tag, n, len(multi))
    L.append("")
    L.append("=" * 96)
    L.append("  二、逐题:答案键那一页,排第几?关键词那 5 个位置占满了吗?")
    L.append("=" * 96)
    L.append("")
    L.append("   题号 | 答案键        | 关键词占位 | 关键词名次 | 向量名次   | 并集填位   | ★ 你的")
    L.append("  " + "-" * 92)
    for no, want, kw, per, a, b, mg, ways in single:
        L.append(f"   {no:>4} | {want:<13} | {min(len(a), K):>2}/{K}      | "
                 f"{cell(a, want):<11}| {cell(b, want):<11}| "
                 f"{cell(ways['并集填位'], want, f'没进前{K}'):<11}| "
                 f"{cell(mg, want, f'没进前{K}')}")
    if no_key:
        L.append("")
        L.append(f"  ⚠ {len(no_key)} 道走检索但答案键不是单页 chunk_id,没进上面的表:"
                 f" {[x[0] for x in no_key]}")

    # ── 汇总:所有合并方式在【同一批题、同一个 k】下 ──
    #
    # ⚠ 我第一版有两个错,都是【尺子】的错,不是数据的错:
    #
    #   ① 判据和被测的东西对不上。
    #      我对每一种方式都用了「答案在前 5 名」这一个判据。
    #      但【并集取前k】按定义就不受 k 约束(它返回最多 10 条)——
    #      用"前 5 名"去量它,等于要求它把自己多给的第 6、7 条扔掉再算。
    #      ★ 结果:它明明把答案给了,却被判"没命中"。
    #      **一个不受 k 约束的东西,不能用 k 当尺子。**
    #
    #   ② 占位那一列拿【全量列表】去比 k。
    #      kw_all 是取全库的结果,可能给出 6 条、9 条,
    #      显示成"9/5"—— 5 个位置怎么会被占 9 个?那不是占位,那是我没截。
    #      **占位 = min(给出几条, k)。超过 k 的部分不叫"占位",叫"用不上"。**
    #
    #   → 统一改成:判据 = 【答案在不在【系统真正会交给大模型的那些条】里】。
    #     这个判据对【封顶的】和【不封顶的】两种都成立,不需要分情况。
    def hits(seqs):
        return sum(1 for (_, w, _, _, _, _, _, _), s in zip(single, seqs) if w in s)

    L.append("")
    L.append("=" * 96)
    L.append(f"  三、汇总(分母 = {n} 道)")
    L.append("=" * 96)
    L.append("")
    L.append("    合并方式      命中     给几条(平均/最多)  判据 / 这一行是什么")
    L.append("  " + "-" * 88)
    rows = [("只关键词",   [x[7]["只关键词"] for x in single],  "答案在给出去的条里   = 系统现在的样子(基准)"),
            ("并集填位",   [x[7]["并集填位"] for x in single],  "同上   ★ 只填空位,不挤掉任何一条"),
            ("交集",       [x[7]["交集"] for x in single],      "同上   反面:证明\"丢\"值多少"),
            ("并集取前k",  [x[7]["并集取前k"] for x in single], "同上   ⚠ 它不受 k 约束,给得多是必然的"),
            ("向量",       [x[5][:K] for x in single],          "同上   对照(不是合并方式,是一条路)")]
    def size(seqs):
        avg = sum(len(s) for s in seqs) / n
        return f"{avg:>4.1f} / {max(len(s) for s in seqs):>2}"

    for name, seqs, note in rows:
        L.append(f"    {name:<12} {hits(seqs):>2}/{n}    {size(seqs):>10} 条     {note}")
    L.append("  " + "-" * 88)
    L.append(f"    ★ 你的        {hits([x[6] for x in single]):>2}/{n}    "
             f"{size([x[6] for x in single]):>10} 条     ← 只有这一行是判断的结果")
    L.append("")
    L.append("  ★ 读这张表要连着看两列:")
    L.append("      命中  ×  平均给几条")
    L.append("      给得多 ≠ 更好 —— 第 7 课量过:多拿的每一条既可能是答案,也可能是噪音,")
    L.append("      而噪音不是\"没用\",是\"有害\"。所以【在同一个条数下比命中】才有意义。")
    L.append(f"      ★ 真正公平的比较只有:只关键词 / 并集填位 / 交集(都封顶在 {K} 条)")

    # ── 分歧清单:他写合并规则的依据 ──
    L.append("")
    L.append("=" * 96)
    L.append("  四、分歧清单 —— ★ 这一段是你写合并规则的依据")
    L.append("=" * 96)
    diff_top = [(no, w, a, b) for no, w, _, _, a, b, _, _ in single if a[0] != b[0]]
    L.append("")
    L.append(f"  ① 两条路的【第一名不是同一页】的题:{len(diff_top)}/{n} 道")
    who_kw = sum(1 for _, w, a, b in diff_top if a[0] == w)
    who_vc = sum(1 for _, w, a, b in diff_top if b[0] == w)
    L.append(f"       其中答案键那一页 = 关键词的第1名 : {who_kw} 道")
    L.append(f"                        = 向量的第1名   : {who_vc} 道")
    L.append(f"                        = 谁的第1名都不是 : {len(diff_top) - who_kw - who_vc} 道")
    for no, w, a, b in diff_top:
        L.append(f"         题 {no:>3}  要 {w:<14} 关键词第1={a[0]}   向量第1={b[0]}")

    flip = [(no, w, a, b) for no, w, _, _, a, b, _, _ in single
            if (rank(a, w) is None or rank(a, w) > K) != (rank(b, w) is None or rank(b, w) > K)]
    L.append("")
    L.append(f"  ★★ ② 真正决定命运的题:{len(flip)} 道")
    L.append("       判据:正确页在【一条路里进不了前 k】、在【另一条路里进了】。")
    L.append("       只有这些题,换检索方式才会改变答案;其余题两条路看法一致,怎么合都一样。")
    for no, w, a, b in flip:
        L.append(f"         题 {no:>3}  要 {w:<14} 关键词{show(rank(a, w))}   向量{show(rank(b, w))}")

    if multi:
        # ★ 多版本题【不能】列全库排名 —— 那是 54 行噪声(#39 第一次跑就是这样),
        #   而它真正要看的只有一件事:**同一页的各个版本,各排第几。**
        #   判据(第 7 课定的)是"分界两边都要在",所以只要看这一页。
        from page_versions import versions
        L.append("")
        L.append(f"  ③ 多版本题 {len(multi)} 道(判据不同:不看前 k,要看【分界两边都在不在】):")
        for no, pg, a, b, mg in multi:
            L.append(f"         题 {no:>3}  第 {pg} 页 —— 这一页的各个版本,在两条路里各排第几:")
            L.append(f"                期次      | 关键词        | 向量          | ★ 你的合并")
            for pers, _, _ in versions(con, pg):
                cid = f"{pers[0]}-P{pg:02d}"
                L.append(f"                {str(pers[0]):<9} | {show(rank(a, cid)):<14} | "
                         f"{show(rank(b, cid)):<14} | {show(rank(mg, cid), f'没进前{K}')}")
            on_page = [c for c in mg if re.fullmatch(rf'\d{{4}}Q\d-P{pg:02d}', c)]
            L.append(f"                ★ 合并结果的前 {K} 条里,这一页占了 {len(on_page)} 个名额: "
                     f"{on_page}")

    L.append("")
    L.append("=" * 96)
    L.append("  五、★ 你的那一块")
    L.append("=" * 96)
    L.append("   tools/my_merge.py 的 merge_rank() —— 现在它是占位(直接返回关键词排名)。")
    L.append("   上表第四行「★ 你的合并」那一列,就是你写完之后的样子。")

    text = "\n".join(L)
    print(text)
    out = OUTDIR / f"第9课_合并对比_{tag}.txt"
    out.write_text(text, encoding="utf-8")
    print(f"\n  ✅ 存到 {out}")


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    main()
