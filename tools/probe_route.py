# -*- coding: utf-8 -*-
r"""
路由层单独体检:只用关键词表跑 route(),不调用大模型。

为什么要有这个:第 7 课每次改 route.py 都跑一次完整 60 道,一次要花
60 次系统调用 + 判分。而上游一变,下游的答案就全作废 —— 在 route.py
还没定型的时候跑满分,等于在流沙上盖房子。

这个脚本把【第①步:要数还是要话】这一层单独拎出来,几秒钟出结果。
它【不是】尺子 —— 判分口径仍然只有 score_eval.py 一个。
判不出(会升级给大模型)的题单独列出来,不计入混淆矩阵。

用法:
    python tools/probe_route.py          # 看当前路由
    python tools/probe_route.py -v       # 连每道题的判定理由一起打
"""
import sys, io, sqlite3, argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from route import (load_airports, load_indicators, route, DB,   # noqa: E402
                   NUMERIC, PROSE, find_indicator, 单值)
from check_eval import read_rows                              # noqa: E402
from paths import ROOT, DATA, PROCESSED, DOCS, DB, OUTPUT

SHEET = DOCS / "评估集.xlsx"
ROUTES = ["SQL", "检索", "拒答"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("-m", "--match", action="store_true",
                    help="打出每道题命中了哪些关键词")
    args = ap.parse_args()

    rows = read_rows(SHEET)
    con = sqlite3.connect(DB)
    airports = load_airports(con)
    indicators = load_indicators(con)

    conf = {(w, g): 0 for w in ROUTES for g in ROUTES + ["判不出"]}
    unknown = []      # 判不出 → 这一层没接上线,要交给大模型
    wrong = []
    hits = {}         # 题号 → 命中的关键词,用于"预期落空时看清为什么"

    for r in rows:
        q = (r["问题"] or "").strip()
        want = (r["期望去向"] or "").strip()
        if not q or want not in ROUTES:
            continue
        got, flag, why = route(con, q, airports, indicators)
        hits[r["题号"]] = (NUMERIC.findall(q), PROSE.findall(q),
                           单值(find_indicator(con, q, indicators)))
        conf[(want, got)] = conf.get((want, got), 0) + 1
        if got == "判不出":
            unknown.append((r["题号"], want, q))
        elif got != want:
            wrong.append((r["题号"], want, got, q, why))

    n = sum(conf.values())
    hit = sum(conf[(w, w)] for w in ROUTES)

    print(f"评估集 {n} 道,只看第①步(要数/要话/拒答),不调用大模型\n")
    print(f"  路由判对 {hit}/{n}   判不出(升级给大模型){len(unknown)}   判错 {len(wrong)}\n")

    print("  混淆矩阵(行=期望,列=实际):")
    print(f"    {'':<8}" + "".join(f"{g:<8}" for g in ROUTES + ["判不出"]))
    for w in ROUTES:
        print(f"    {w:<8}" + "".join(f"{conf[(w, g)]:<8}" for g in ROUTES + ["判不出"]))

    if wrong:
        print(f"\n  ★ 判错 {len(wrong)} 道(这一层的账,改关键词表就能看回来):")
        for tid, want, got, q, why in wrong:
            print(f"    {tid:<4}期望 {want:<4}→ 实际 {got:<4}  {q[:46]}")
            if args.verbose:
                print(f"         理由: {why}")

    if unknown:
        print(f"\n  · 判不出 {len(unknown)} 道(关键词表没覆盖,第 5 课的大模型接在这一层):")
        for tid, want, q in unknown:
            print(f"    {tid:<4}期望 {want:<4}            {q[:46]}")

    if args.match:
        print("\n  ★ 关键词命中明细(改词表前先看这个 —— 哪些题是被哪个词带偏的):")
        for r in rows:
            q = (r["问题"] or "").strip()
            want = (r["期望去向"] or "").strip()
            if not q or want not in ROUTES:
                continue
            got, _, _ = route(con, q, airports, indicators)
            num, prose, ind = hits[r["题号"]]
            if got == want and not num and not prose and not ind:
                continue
            mark = " " if got == want else "★"
            print(f"   {mark}{r['题号']:<4}期望 {want:<4}→ {got:<4} "
                  f"NUM={num} PROSE={prose} 指标={ind!r}")
            print(f"        {q[:52]}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
