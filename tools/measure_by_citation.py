# -*- coding: utf-8 -*-
r"""
第 10 课 · 用【出处】量张君杰的口径 —— 不用字面匹配,改核编号

═══ 它替掉了哪把尺子 ═══
    原来量他的口径,靠 measure_noise.py 的【字面匹配】(回答的每段去材料里找)。
    ★ 那把尺子修了四次,最后还是判不了 —— 因为生成层【本来就要重组材料】,
      重组过的句子字面上找不到,于是被误判成"没据"。

    ★★ 现在回答里标了出处,于是可以换一把【硬得多】的尺子:
       出处的编号是【系统自己发的】—— 核对它,没有中间地带。

═══ 口径(张君杰定)═══
    "1，就 0
     2，算 都没有按照规定的期次来是错  那万一有一期的变了呢?
     3，只允许回答精准  有其他的无关内容都算错"
    + "甲(内容一样但期次错也算错)"

    落成:回答的内容必须【只来自期望的那一块】。

═══ 怎么判(纯代码)═══
    期望 = 答案键里的 chunk_id
    回答里标的出处 = 从 (出处:YYYYQn-Pnn) 里抽出来的编号

        · 出处【全部 == 期望】          → ✅ 真对
        · 出处里【有别的页】             → ❌ 违反③(有别的页的内容)
        · 出处【完全没标】               → ⚠ 说不清 —— 不算对,也不算错,单列
        · 标了【材料里没有的编号】        → ❌ 编的出处

    ★ 第 3 条要说清:没标出处不是"错",是"这把尺子判不了"。
      **把它算进任何一边都是假精确。所以单列。**
"""
import sys, io, re, json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from ask import CITE, CID          # ★ 和系统用同一套正则 —— 不另发明一份
from paths import ROOT, DATA, PROCESSED, DOCS, DB, OUTPUT

#  ⚠ 2026-09-22 路径迁移时这行【原本在 import 上面】,于是 ROOT 还没定义就用了它。
#    原因是这个文件的 import 块【是分散的】(中间夹着 sys.path.insert),
#    而迁移脚本把 `from paths import` 插在"最后一个 import 之后" —— 落在了使用之后。
#  ★ 所以顺手把它改成 DOCS —— 比 "ROOT / docs" 少一次拼接,也不容易再错位。
EVAL_IN = DOCS / "评估集.xlsx"


def main():
    tag = sys.argv[1] if len(sys.argv) > 1 else None
    if not tag:
        print(__doc__)
        return
    RUN = ROOT / "docs" / f"评估集_跑分_{tag}.json"
    if not RUN.exists():
        print(f"★ 没有这个文件:{RUN}")
        return

    from check_eval import read_rows
    rows = read_rows(EVAL_IN)
    got = json.loads(RUN.read_text(encoding="utf-8"))

    print("=" * 96)
    print(f"  第 10 课量具(出处版) · {tag}")
    print("=" * 96)
    print("  口径:回答的内容必须【只来自期望的那一块】")
    print("  ★ 判据 = 核回答里标的出处编号(不是字面匹配)")
    print()

    good, bad, unclear = [], [], []
    for r, g in zip(rows, got):
        if g.get("去向") not in ("检索", "检索·0条"):
            continue
        cite = str(r.get("出处") or "")
        if "多版本" in cite:
            continue
        m = re.search(r"(\d{4}Q\d-P\d+)", cite)
        if not m:
            continue
        want = m.group(1)
        ans = g.get("系统答") or ""
        mat = {s.split(" = ")[0].strip() for s in (g.get("来源") or [])}
        cites = CID.findall(" ".join(CITE.findall(ans)))

        if not cites:
            verdict, why = "⚠ 说不清", "回答里没标出处"
            unclear.append(r["题号"])
        else:
            ghost = [c for c in cites if c not in mat]
            others = [c for c in cites if c != want and c in mat]
            if ghost:
                verdict, why = "❌ 编的出处", f"标的编号材料里没有:{ghost}"
                bad.append(r["题号"])
            elif others:
                verdict, why = "❌ 有别的页", f"除了 {want} 还标了 {sorted(set(others))}"
                bad.append(r["题号"])
            elif set(cites) == {want}:
                verdict, why = "✅ 真对", f"出处全是 {want}"
                good.append(r["题号"])
            else:
                verdict, why = "❌ 没标期望那块", f"标的是 {sorted(set(cites))}"
                bad.append(r["题号"])

        print(f"  题 {r['题号']:>3}  {verdict:<12} 答案键 {want}")
        print(f"          出处 {sorted(set(cites)) if cites else '【无】'}   {why}")

    n = len(good) + len(bad) + len(unclear)
    print()
    print("=" * 96)
    print(f"  {n} 道走检索的题里:")
    print(f"      ✅ 真对      {len(good):>2}   {good}")
    print(f"      ❌ 错        {len(bad):>2}   {bad}")
    print(f"      ⚠ 说不清    {len(unclear):>2}   {unclear}   (没标出处,这把尺子判不了)")
    print()
    print("  ★ 对照:同一批题")
    print("      旧口径(答案在不在文本里)  →  15/15")
    print("      张君杰口径·字面匹配版       →   0/14  ← 那把尺子判不了生成,已弃用")
    print("      张君杰口径·出处版(现在)     →  看上面")
    print()
    print("  ★★ 而 ⚠ 那几道【不能算进任何一边】—— 塞进「对」或「错」都是假精确。")


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    main()
