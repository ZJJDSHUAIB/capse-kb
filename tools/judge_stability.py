# -*- coding: utf-8 -*-
r"""
第 11 课 · 判分稳定性逐题矩阵 —— 到底【哪些题】在晃?

═══ 为什么要有它 ═══
    刚才量出"同一批答案,三次判分 58/57/57" —— 但那只是【总分】。
    ★ 总分差 1 道,看不出是哪一道在晃。
    ★★ 所以这里【逐题】跑 N 次,记下每一道题每次判对还是判错。

═══ 它回答什么 ═══
    ① 哪些题【每次都判一样】(稳定的)
    ② 哪些题【在边界上晃】(有时对有时错)
    ③ 晃的那些题,是走 SQL 的、还是走检索的

    ★ 第 ③ 条最要紧:SQL 的答案是【程序算的】(确定),
      检索的答案是【大模型生成的】。
      ★★ 如果晃的题【全在检索那条路】,那说明晃的源头可能是答案本身;
      ★★★ 而这次实验答案【没变】(--from-json)——
          所以如果检索那条路也晃,那晃就只能来自【判分】。
"""
import sys, io, json
from pathlib import Path
from paths import ROOT, DATA, PROCESSED, DOCS, DB, OUTPUT

sys.path.insert(0, str(Path(__file__).parent))

N = 3


def main():
    import score_eval as SE
    from check_eval import read_rows

    tag = sys.argv[1] if len(sys.argv) > 1 else "判分稳定性-边界2"
    rows = read_rows(ROOT / "docs" / "评估集.xlsx")
    gots = json.loads((ROOT / "docs" / f"评估集_跑分_{tag}.json").read_text(encoding="utf-8"))
    SE._NO_CACHE = True                     # ★ 不量缓存,量判分

    print("=" * 92)
    print(f"  判分稳定性逐题矩阵 · {tag} · 每题判 {N} 次")
    print("=" * 92)
    print("  ★ 答案【没重跑】(--from-json),所以答案是不变的")
    print("  ★★ 因此在同一道题上看到的变化,只能来自【判分】")
    print()

    mat = {}
    for r, g in zip(rows, gots):
        no = r["题号"]
        got = g.get("系统答") or ""
        if not got:
            continue
        res = []
        for _ in range(N):
            j = SE.llm_judge(r, got)
            res.append(bool(j and j.get("对")))
        mat[no] = (res, g.get("去向"), str(r.get("问题") or "")[:34])

    stable_t, stable_f, swing = [], [], []
    for no, (res, where, q) in mat.items():
        if all(res):
            stable_t.append((no, where, q))
        elif not any(res):
            stable_f.append((no, where, q))
        else:
            swing.append((no, where, q, res))

    def show(title, items, extra=False):
        print(f"\n  {title}  ({len(items)} 道)")
        for it in items:
            if extra:
                no, where, q, res = it
                marks = "".join("✅" if x else "❌" for x in res)
                print(f"     题 {no:>3}  [{where}]  {marks}   {q}")
            else:
                no, where, q = it
                print(f"     题 {no:>3}  [{where}]  {q}")

    show("★★★ 一直在晃的(有时对有时错)", swing, extra=True)
    show("一直判错的", stable_f)
    print(f"\n  一直判对的  ({len(stable_t)} 道)—— 不逐条列")

    print()
    print("=" * 92)
    print("  ★ 晃的那几道,走的哪条路?")
    for no, where, q, res in swing:
        print(f"     题 {no:>3}  {where}")
    if not swing:
        print("     (没有晃的)")
    print()
    print("  ★★ 答案这次【没重跑】—— 所以同一道题上看到的对错变化,只能来自【判分】。")


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    main()
