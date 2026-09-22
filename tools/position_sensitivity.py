# -*- coding: utf-8 -*-
r"""
第 10 课 · 哪些题【对材料位置敏感】?敏感的那些有什么共同点?

═══ ⚠⚠ 这个脚本【不改库、不改问法】 ═══
    我上一轮提过两个测试:"把答案改成一句话""把问句换个动词"。
    ★ 两个都是错的 —— 一个动库(真相源),一个动考题(评估集)。
    ★★ 那条规矩刚学过:对着答案改,改了当然对,但那不算数。

    所以这里只做一件事:【把同一份材料换个位置放,看结果变不变】。
    被动的都是【位置】这一个变量,别的全不动。

═══ 怎么判"它看不看得见" ═══
    ★ 不用逐题定关键词 —— 用一条通用的判据:
        回答【不是】"材料里没有"这一类 → 算它看见了

    ★★ 这个判据判不出"答得对不对",但对这个实验够了 ——
       我要测的是"它看没看见",不是"它答得准不准"。

═══ 它回答什么 ═══
    ① 哪些题对位置敏感(第1位 vs 第3位,答出率差多少)
    ② 敏感的那些,共同点是什么 —— 看相关性,不推因果
"""
import sys, io, re, json, sqlite3, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

ROOT = Path(r"D:\capse-kb")
DB = ROOT / "data" / "processed" / "capse.db"
OUT = ROOT / "docs" / "第10课_位置敏感性.txt"
REPS = 6
K = 5

NONE_PAT = re.compile(r"材料里没有|材料中没有|没有提到|未提及|无法确定")


def main():
    from ask import gen_answer
    from check_eval import read_rows, EVAL_IN
    from build_search import search_merged
    import ask as askmod

    con = sqlite3.connect(DB)
    askmod.USE_MERGE = True

    rows = read_rows(EVAL_IN)
    gots = json.loads((ROOT / "docs" / "评估集_跑分_第9课-RRF各半.json").read_text(encoding="utf-8"))
    chunks = {r[0]: r[1] for r in con.execute("SELECT chunk_id, 文本 FROM chunk")}

    cases = []
    for r, g in zip(rows, gots):
        if g.get("去向") not in ("检索", "检索·0条"):
            continue
        cite = str(r.get("出处") or "")
        if "多版本" in cite:
            continue
        m = re.search(r"(\d{4}Q\d-P\d+)", cite)
        if not m:
            continue
        kws = [p.split(":", 1)[1].strip() for p in (g.get("过程") or []) if "检索用词" in p]
        cases.append((r["题号"], str(r.get("问题") or ""), m.group(1), kws[0] if kws else ""))

    L = ["=" * 96,
         "  第 10 课 · 哪些题对材料位置敏感?",
         "=" * 96,
         f"  每格跑 {REPS} 次;位置是【唯一被动的变量】—— 不动库、不动问法", ""]
    L.append(f"  {'题':>4} {'第1位':>7} {'第3位':>7} {'差':>6}  答案页长  问题词在答案页里出现几个")
    L.append("  " + "-" * 90)

    out = []
    for no, q, ans_cid, kw in cases:
        per = sorted(set(re.findall(r"\d{4}Q\d", q))) or None
        hits = search_merged(con, q, k=K, periods=per)
        order = [str(h["chunk_id"]) for h in hits]
        by_id = {str(h["chunk_id"]): h for h in hits}
        if ans_cid not in by_id:
            L.append(f"  {no:>4}  ⚠ 答案页 {ans_cid} 不在检索结果里,跳过")
            continue

        def at(pos):
            rest = [c for c in order if c != ans_cid]
            seq = rest[:pos - 1] + [ans_cid] + rest[pos - 1:]
            sub = [by_id[c] for c in seq]
            ok = 0
            for _ in range(REPS):
                try:
                    a = gen_answer(q, sub)
                except Exception as e:
                    a = f"(出错 {e})"
                if not NONE_PAT.search(a):
                    ok += 1
                time.sleep(0.15)
            return ok

        a1, a3 = at(1), at(3)
        aw = chunks.get(ans_cid, "")
        hit_words = sum(1 for t in kw.split() if t in aw)
        out.append((no, a1, a3, len(aw), hit_words, kw, order))
        L.append(f"  {no:>4} {a1:>4}/{REPS} {a3:>4}/{REPS} {a1 - a3:>+6}  {len(aw):>8}  "
                 f"{hit_words}/{len(kw.split())}   {order}")

    L.append("")
    L.append("=" * 96)
    L.append("  按【差值】排序 —— 差得多的就是位置敏感的题")
    L.append("=" * 96)
    for no, a1, a3, ln, hw, kw, order in sorted(out, key=lambda x: -(x[1] - x[2])):
        bar = "█" * max(0, a1 - a3) * 3
        L.append(f"  {no:>4}  第1位 {a1}/{REPS}  第3位 {a3}/{REPS}   差 {a1 - a3:+d} {bar}")

    L.append("")
    L.append("  ★★ 怎么读:差值 > 0 = 放中间会变差;= 0 = 位置无关")
    L.append("  ★★★ 共同点那两列是【相关】,不是因果 —— 样本只有几道,别下结论。")
    text = "\n".join(L)
    print(text)
    OUT.write_text(text, encoding="utf-8")
    print(f"\n  ✅ 存到 {OUT}")


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    main()
