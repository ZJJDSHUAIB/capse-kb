# -*- coding: utf-8 -*-
r"""
第 9 课 · 关键词检索 vs 向量检索:**在同一个库、同一批题上,各命中多少?**

═══ 为什么要做这个 ═══
    张君杰问过两次,两次都对:
        "补近义词是不是过拟合?"          → 是(我把答案写进了 prompt 的例子)
        "向量怎么就找不到?意思相近吧"     → 对(量出来它确实找得到)

    ★ 而我两次都是【坐着推】。而这个项目一路的规矩是:
        **凡是能查的,都不许感觉。**

    → 所以这里把两种检索放在【同一批题】上量一遍,让数据说话。

═══ 量什么 ═══
    拿评估集里【走检索】的那些题,用它们【实际的检索词】,分别用两种方式搜:

        关键词   search_multi()   —— 按字面
        向量     search_vec()     —— 按意思

    看【正确的那一页】在不在前 k 条里。

    ★ 判据是硬的:正确页 = 期望出处里的那个 chunk_id。
      多版本题(出处写 `chunk=多版本;页码=NN`)单独处理 —— 它要"两边都命中",
      和单页题不是一回事,不能混在一个数里。

═══ ★★ 最要紧的一格 ═══
        关键词对 · 向量错   ← 如果存在,说明【不能只用向量】
        关键词错 · 向量对   ← 向量补上了关键词的漏
        两个都对            ← 无所谓
        两个都错            ← 病不在检索方式
"""
import sys, io, re, json, sqlite3
from pathlib import Path
from paths import ROOT, DATA, PROCESSED, DOCS, DB, OUTPUT

sys.path.insert(0, str(Path(__file__).parent))

OUT = DOCS / "评估集_跑分.json"
K = 5


def main():
    from check_eval import read_rows, EVAL_IN
    from build_search import search_multi
    from vector_search import search_vec

    rows = read_rows(EVAL_IN)
    gots = json.loads(OUT.read_text(encoding="utf-8"))
    con = sqlite3.connect(DB)

    tally = {"两个都对": [], "关键词对·向量错": [], "关键词错·向量对": [],
             "两个都错": [], "多版本题(另算)": []}
    for r, g in zip(rows, gots):
        if g.get("去向") not in ("检索", "检索·0条"):
            continue
        cite = str(r.get("出处") or "")
        kw = [p.split(":", 1)[1].strip() for p in (g.get("过程") or []) if "检索用词" in p]
        if not kw:
            continue
        kw = kw[0]
        per = sorted(re.findall(r'\d{4}Q\d', str(r.get("问题") or ""))) or None

        a = [h["chunk_id"] for h in search_multi(con, kw, k=K, periods=per)]
        b = [h["chunk_id"] for h in search_vec(con, kw, k=K, periods=per)]

        if "多版本" in cite:
            #  ★ 多版本题要"分界两边都命中",不是"某一页在不在" —— 单独算
            tally["多版本题(另算)"].append((r["题号"], a, b))
            continue
        m = re.search(r'(\d{4}Q\d-P\d+)', cite)
        if not m:
            continue
        want = m.group(1)
        ha, hb = want in a, want in b
        key = ("两个都对" if ha and hb else
               "关键词对·向量错" if ha else
               "关键词错·向量对" if hb else "两个都错")
        tally[key].append((r["题号"], want, a, b))

    n = sum(len(v) for k, v in tally.items() if "多版本" not in k)
    print("=" * 78)
    print(f"  走检索的题里,有单页答案键的 {n} 道(另有多版本题 "
          f"{len(tally['多版本题(另算)'])} 道,判据不同,单独列)")
    print("=" * 78)
    for key in ("两个都对", "关键词对·向量错", "关键词错·向量对", "两个都错"):
        v = tally[key]
        print(f"\n{key}:  {len(v)} 道")
        for no, want, a, b in v:
            print(f"   题 {no:>3}  要 {want}")
            print(f"        关键词 → {a}")
            print(f"        向量   → {b}")

    print(f"\n★ 关键词命中 {sum(len(tally[k]) for k in ('两个都对','关键词对·向量错'))}/{n}"
          f"   向量命中 {sum(len(tally[k]) for k in ('两个都对','关键词错·向量对'))}/{n}")

    if tally["多版本题(另算)"]:
        print("\n多版本题(要两边都命中):")
        for no, a, b in tally["多版本题(另算)"]:
            print(f"   题 {no}:关键词 → {a}")
            print(f"          向量   → {b}")
    print("""
  ★ 怎么读:
       "关键词对·向量错" 这一格 >0  →  **不能只用向量**,得两个都留
       "关键词错·向量对" 这一格     →  向量补上了关键词漏掉的那些
       "两个都错"                  →  病不在检索方式(比如问句里压根没有可搜的词)
""")


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    main()
