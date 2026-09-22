# -*- coding: utf-8 -*-
r"""
第 7 课 · 跑挑战集。

═══ 它为什么存在 ═══
    我给「硬限定词」写了一条规则(route.py 的 LIMIT),然后在同一套 60 题上量出
    "3 真 0 假" —— **那是个不能信的数**:我是先看到 #48 #51 #52 才想出那条规则的。
    那不叫"规则",那叫"记住答案"。

    要分清,只有一条路:**拿一批【没参与设计】的题去撞。**

═══ 判据(全硬,不看我那条规则)═══
    只看一件事:**正确的那一页(X)在不在系统取到的来源里?**

        ✅ 答对          取到了正确页
        ★ 静默          没取到、也没出声        ← 最贵
        ◐ 出声未答对     没取到、但出声了
        ★ 误报          取到了却还报警

═══ ★ 口径(张君杰定的 2026-09-18):「算出声,但不算正确答案」═══
    「出声」有三种,都算:
        拒答        「我不回答」
        检索·0条    「我找了,没找到」
        警告非空    「我给了答案,但你别信」
    **而它们都不算答对** —— 用户还是没拿到数据。

    → 两个数分开记:出声归告警率,答对归正确率。
      拒答在这两个数里结果相反,正说明它们必须分开。
"""
import sys, io, re, json, sqlite3
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

DB = Path(r"D:\capse-kb\data\processed\capse.db")
SRC = Path(r"D:\capse-kb\docs\_挑战集.json")
SPOKEN = ("拒答", "检索·0条")


def main():
    rows = json.loads(SRC.read_text(encoding="utf-8"))
    from ask import ask
    from route import load_airports, load_indicators
    con = sqlite3.connect(DB)
    ap, ind = load_airports(con), load_indicators(con)

    print("=" * 78)
    print(f"  挑战集:{len(rows)} 道   (这批题【没参与过】那条规则的设计)")
    print("=" * 78)

    tally = {"答对": [], "静默": [], "出声未答对": [], "误报": []}
    for r in rows:
        a = ask(con, r["问题"], ap, ind)
        spoke = bool(a.get("警告")) or a.get("去向") in SPOKEN
        x = r.get("正确页") or ""
        got = set(re.findall(r'\d{4}Q\d-P\d+', " ".join(a.get("来源") or [])))
        print(f"\n[{r['类别']}] {r['问题']}")
        if x:
            hit = x in got
            key = ("答对" if hit else "静默") if not spoke else ("误报" if hit else "出声未答对")
            tally[key].append(r["问题"])
            mark = {"误报": "★误报", "答对": "✅答对",
                    "出声未答对": "◐出声未答对", "静默": "★静默"}[key]
            print(f"   正确页 {x}   系统取到 {sorted(got) or '无'}   → {mark}")
            if spoke:
                why = a["警告"][0][:64] if a.get("警告") else f"去向={a['去向']}"
                print(f"   出声方式:{why}")
        else:
            print(f"   去向={a['去向']}  → {'出声了 ✅' if spoke else '★没出声'}")
            for l in (a["答案"] or [])[:2]:
                print(f"     {l[:70]}")
            if r.get("期望说明"):
                print(f"   ⚠ 期望:{r['期望说明'][:76]}")

    tot = sum(len(v) for v in tally.values())
    print("\n" + "=" * 78)
    print("  A/B 的四个格(全硬判据,只看 chunk_id):")
    print(f"     ✅ 答对(取到了正确页)         {len(tally['答对']):>3} 道")
    print(f"     ◐ 出声未答对(没取到,但出声了)  {len(tally['出声未答对']):>3} 道")
    print(f"     ★ 静默(没取到,也没出声)        {len(tally['静默']):>3} 道  ← 最贵")
    print(f"     ★ 误报(取到了却还报警)         {len(tally['误报']):>3} 道")
    if tot:
        missed = len(tally["静默"]) + len(tally["出声未答对"])
        spoke_n = len(tally["出声未答对"]) + len(tally["误报"])
        print("\n     ★ 出声 ≠ 答对,两个数分开记:")
        print(f"       正确率  取到正确页的          {len(tally['答对'])}/{tot}"
              f" = {len(tally['答对'])/tot:.0%}")
        if missed:
            print(f"       告警率  没取到的里面出声了    "
                  f"{len(tally['出声未答对'])}/{missed} = {len(tally['出声未答对'])/missed:.0%}")
        if spoke_n:
            print(f"       出声的里面,真的没取到的      "
                  f"{len(tally['出声未答对'])}/{spoke_n} = {len(tally['出声未答对'])/spoke_n:.0%}")
    print("\n  ⚠ 拿这个数去和正式 60 题上的比 —— 差多少,就是过拟合有多少。")


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    main()
