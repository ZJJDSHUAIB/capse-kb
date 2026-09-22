# -*- coding: utf-8 -*-
r"""
第 13 课 · ⚠ **这是一个【试过、量过、做不成】的东西 —— 留着是为了留下这三代的过程。**

═══ 本来想做什么 ═══
    这一轮唯一丢分的那次(第39题,判 0)是这么来的:

        材料里有【第7页的三个版本】——同一句指标说明,三期数字不同(6/30、6/31、7/28)。
        而答案【一个字都没提那段的数字】,整段省掉了。
        ★ 而所有硬判据都是空的,过程栏还写着"通过"。

    **因为那些判据核的是"写出来的东西有没有据",而【没写的东西它们不核】。**

    → 想补一道:"材料里有 N 个版本,而答案对它一字不提" → 出声。

═══ ★★★ 三代判据,三代都错(全部实测)═══

    第一代:材料里【所有】多版本页,判"提没提"
        结果 16 处 —— 几乎全是噪声:
          第 9 页 ['3.96'…'4.01']  ← 分数表,9 期的分数本来就该不同
          第12 页 ['0551','1999','2012'] ← 电话区号、年份,PDF 抽取的细小差异
        ★ 它们和问题【根本无关】,答案不提它们完全正确。
        ★★ 而"有没有提"这件事,对【无关的页】和【相关却被漏掉的页】长得一模一样 ——
           所以第一代不是量具,是噪声发生器。

    第二代:只看【答案自己引用过】的页 —— 引用了就说明用到了,那它的版本差异就该说清
        16 处 → 3 处。但剩下 3 处还是误报,而且原因和第一代不同:
          第45题 问的是"创立了哪些指标或系统",答案从 P11 找到了答案;
                 而 P11 的版本差异是"经过 10/12/13 年" —— 和这问题无关。
          ★ 它引用了 P11,但引的是 P11 里【另一段话】。
        ★★ 根因:判据拿【整页】算差异,而答案引用的是【页里的一句话】。

    第三代:拿【已知的真案例】验第二代(第39题那次漏掉指标段的原文)
        ★ 连真案例都判不出来:
          第7页的差异数字是 6/30、6/31、7/28,而判据说"答案提到了" ——
          因为答案里写了「2025Q2-P07」,那个 '2025' 被算成了"提过"。
        ★★ 出处里的年份,把判据自己污染了。

═══ ★★★ 结论(这才是要留下的东西)═══
    **这个判据做不出来 —— 不是没调好,是它要判的东西不在硬判据的能力范围内。**

    判"漏了"必须知道【该说什么】,而"该说什么"只有两个来源:

        ① 问题本身     → 需要"理解" → 那是【软判据】(大模型)
        ② 评估集标准答案 → 那是【外部真值】,系统自己没有

    ★ 硬判据只能判「写出来的东西有没有据」,
      判不了「没写的东西该不该写」—— 这不是调参能绕过去的。

    分清这一点很要紧:没有这三代记录,下一次还会有人(包括我)
    拿"再加一道判据"去解这个问题,然后再错三次。

═══ 下面这段代码保留原样 ═══
    它是第三代的形态。跑它是为了能看到上面那些数 —— 不是因为它能用。
"""
import sys, io, re, json, sqlite3, argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from page_versions import versions, norm
from paths import ROOT, DATA, PROCESSED, DOCS, DB, OUTPUT

NUM = re.compile(r'\d+(?:\.\d+)?')


def diff_numbers(texts):
    """这一页的【版本差异数字】——至少一版有、而【不是所有版都有】的。

    ★ 为什么要这条限定:年份、页码这些【每版都有】,
      拿它们当判据等于没判据(实测:三个版本里"2025"出现在两版,
      会把"提没提该页"这件事整个糊掉)。
    """
    sets = [set(NUM.findall(t)) for t in texts]
    if not sets:
        return set()
    全都有 = set.intersection(*sets)
    return set().union(*sets) - 全都有


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default="", help="跑分文件;不给就用最新的第13课那份")
    a = ap.parse_args()
    f = Path(a.file) if a.file else sorted(
        DOCS.glob("评估集_跑分_第13课-*.json"),
        key=lambda p: p.stat().st_mtime)[-1]

    con = sqlite3.connect(DB)
    data = json.load(open(f, encoding="utf-8"))
    print("=" * 78)
    print(f"  多版本页「一字不提」的量 —— 用的跑分文件:{f.name}")
    print("=" * 78)

    n_applicable = 0
    silent = []
    unmeasurable = []
    for i, row in enumerate(data):
        if row.get("去向") not in ("检索",):
            continue
        hits = []
        for s in (row.get("来源") or []):
            cid = str(s).split(" = ")[0].strip()
            r = con.execute("SELECT 期次,页码,文本,页类型 FROM chunk WHERE chunk_id=?",
                            (cid,)).fetchone()
            if r:
                hits.append({"chunk_id": cid, "期次": r[0], "页码": r[1],
                             "文本": r[2], "页类型": r[3]})
        if not hits:
            continue
        #  ═══ ★★★ 只审【模型写的那一段】═══════════════════════════
        #  【为什么不能用"系统答" —— 实测踩到,而且踩了四次】
        #      系统答 = 多版本说明 + 模型那句,而多版本说明是【代码算出来的】,
        #      里面本来就有页码期数、有「第 7 页在 9 期里有 3 个版本」这种话 —— 全是数字。
        #
        #      ★ 后果:第39题那次【模型整段没提指标数】,
        #        而这个量具报"没漏" —— 因为那段说明里什么数都有。
        #      ★★ 拿"系统答"当输入,这个量具【根本量不出它要量的东西】。
        #
        #  ★★★ 所以:2026-09-22 起,ask() 把模型那句单独存成 模型答。
        #      没有这个字段的旧跑分文件 —— 【明说量不了】,不静默跳过。
        ans = row.get("模型答")
        if ans is None:
            unmeasurable.append(i + 1)
            continue
        ans = str(ans)
        #  ① 材料里有多版本的页
        multi = {}
        for h in hits:
            vs = versions(con, h["页码"], h["页类型"])
            if len(vs) > 1:
                multi[h["页码"]] = vs
        if not multi:
            continue                       # 这题的材料不涉及多版本 → 判据不适用
        n_applicable += 1
        #  ═══ ★★★ 2026-09-22 第二版判据:只看【答案自己引用过的】那一页 ═══
        #  【第一版为什么不行 —— 实测出来的】
        #      第一版对材料里【所有】多版本页都判"提没提",结果 16 处里几乎全是噪声:
        #        第 9 页 ['3.96'…'4.01']  ← 分数表,9 期的分数本来就该不同
        #        第12 页 ['0551','1999','2012'] ← 电话区号、年份,PDF 抽取的细小差异
        #      ★ 它们和问题【根本没关系】,答案不提它们完全正确。
        #      ★★ 而"有没有提"这件事,对【无关的页】和【相关但被漏掉的页】
        #         长得一模一样 —— 第一版分不开,所以它不是量具,是噪声发生器。
        #
        #  ★★★ 第二版:只对【答案自己引用了的页】判。
        #      理由:答案引用了那一页,就说明它【用到了那一页】;
        #           那么那一页的版本差异,它就该说清。不提才是"漏"。
        #      没引用的页 —— 那是"和问题无关",不是"漏"。
        引用页 = {int(m.group(1)) for m in re.finditer(r'(?:\d{4}Q\d)-P(\d+)', ans)}
        for pg, vs in sorted(multi.items()):
            if pg not in 引用页:
                continue                   # 答案没引用这一页 → 不适用
            diff = diff_numbers([t for _, t, _ in vs])
            if not diff:
                continue                   # 各版数字一样 → 不存在"混着说"的风险
            hit = [d for d in diff if re.search(rf'(?<!\d){re.escape(d)}(?!\d)', ans)]
            if not hit:
                silent.append((i + 1, pg, len(vs), sorted(diff)[:6]))

    if unmeasurable:
        #  ★ 不静默跳过 —— "量不了"本身是要报出来的事实。
        print(f"\n  ⚠ 量不了(那份跑分文件里没有 模型答 字段,是老版本):"
              f"{unmeasurable}")
        print("     → 重新跑一次 score_eval 就有了(ask.py 现在会存这个字段)。")
    print(f"\n  ★ 材料涉及多版本页的题:{n_applicable} 道")
    print(f"  ★★ 其中【对某一页的差异数字一字不提】的:{len(silent)} 处\n")
    for no, pg, nv, diff in silent:
        print(f"     第 {no} 题 —— 第 {pg} 页有 {nv} 个版本,"
              f"而答案里这些数一个都没出现:{diff}")
    if not silent:
        print("     (一处都没有)")
    print("""
  ⚠⚠ 上面这个数【不能用】—— 它是第三代判据的输出,而第三代【连已知的真案例都判不出】。
     留下的原因见文件头:让下一个想"再加一道判据"的人(包括我自己)
     先看到已经错过三次,而不是再错第四次。

  ★ 真正的结论:
      硬判据只能判「写出来的东西有没有据」;
      判不了「没写的东西该不该写」——
      后者需要"该说什么",而那个只有【问题(要理解)】和【评估集(外部真值)】能给。""")


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    main()
