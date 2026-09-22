# -*- coding: utf-8 -*-
r"""
第 10 课 · 核「某档位第 N 名是谁」这类题的答案 —— 用表核,不用字面匹配

═══ 它补的是哪一块 ═══
    已有的三道检查都【核不到答案本身】:
        audit_answer     核数字有没有据           → 抓不到"答漏了一个机场"
        check_citations  核出处真不真             → 出处是真的,只是答漏了
        check_missed     核"说没有而材料里有"      → 它没"说没有",它答了一半

    ★ 这一类题(分档排名)的答案【有结构】—— 分数↔机场的配对。
    ★★ 所以能算:第一名有几个?前两名是谁?答案里说全了吗?

═══ 怎么算(纯代码)═══
    ① 从问句里抽【档位】和【要几名】
    ② 从给它的材料里找那一档的页 → parse_table 解析出配对
    ③ 取前 N 名(★ 并列的要一起取 —— 分数相同就是并列)
    ④ 核:这些机场名,回答里都提到了吗?

    ★ 第 ③ 步是这一环的关键:"并列"是【从分数算出来的】,
      不是从标准答案抄的。两道题分数一样 → 那就是并列第一。

═══ ⚠ 它只覆盖这一类题 ═══
    问句里同时有【档位】和【名次】的。
    别的题它明确报"不适用",不硬凑。
"""
import sys, io, re, sqlite3
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from parse_table import parse, GRADE, SCORE

GRADE_Q = re.compile(r"(\d{4}万(?:-\d{4}万)?级(?:以上)?)")
RANK_Q = [("前两名", 2), ("前三名", 3), ("前五名", 5),
          ("前五", 5), ("前二", 2), ("第一", 1), ("第二名", 2), ("第三名", 3)]


def needed(q):
    """问句要的是哪一档、要几名?抽不出来就返回 None —— 不适用。"""
    g = GRADE_Q.search(q)
    if not g:
        return None, None
    n = None
    for word, k in RANK_Q:
        if word in q:
            n = max(n or 0, k)
    return g.group(1), n


def top_of(grade, hits, n):
    """材料里【那一档】的表,前 n 名是谁?★ 并列的一起给。"""
    for h in hits:
        g, pairs = parse(h["文本"])
        if g is None or g != grade or not pairs:
            continue
        cut = min(n or 1, len(pairs))
        best = pairs[cut - 1][0]                       # 第 n 名的分数
        #  ★ 并列:凡是分数 == 第 n 名的,都算进来
        return [p for p in pairs[:cut]] + [p for p in pairs[cut:] if p[0] == best], h["chunk_id"]
    return None, None


def check(ans, q, hits):
    """→ (适不适用, 缺了哪些机场)"""
    grade, n = needed(q)
    if not grade or not n:
        return False, []
    want, src = top_of(grade, hits, n)
    if want is None:
        return False, []                              # 材料里没有那一档的表
    miss = [f"{ap} {sc}" for sc, ap in want if ap not in ans]
    return True, miss


def main():
    import json
    from check_eval import read_rows
    ROOT = Path(r"D:\capse-kb")
    con = sqlite3.connect(ROOT / "data" / "processed" / "capse.db")

    print("=" * 88)
    print("  第 10 课 · 核「某档位第 N 名」这类题(用表核)")
    print("=" * 88)
    print("  ① 拿【现在的回答】核 —— 应该全过")
    d = json.loads((ROOT / "docs" / "评估集_跑分_第10课-去旧告警.json").read_text(encoding="utf-8"))
    rows = read_rows(ROOT / "docs" / "评估集.xlsx")
    hit_n = 0
    for r, g in zip(rows, d):
        if g.get("去向") not in ("检索", "检索·0条"):
            continue
        q = str(r.get("问题") or "")
        ans = g.get("系统答") or ""
        mat = [{"chunk_id": s.split(" = ")[0].strip(), "文本": ""}
               for s in (g.get("来源") or [])]
        for h in mat:
            t = con.execute("SELECT 文本 FROM chunk WHERE chunk_id=?", (h["chunk_id"],)).fetchone()
            h["文本"] = t[0] if t else ""
        ok, miss = check(ans, q, mat)
        if not ok:
            continue
        hit_n += 1
        print(f"  题 {r['题号']:>3}  {'✅ 答全了' if not miss else '❌ 缺 ' + str(miss)}   {q[:40]}")

    print()
    print("  ② ★ 拿【第一次跑那版漏了并列的回答】核 —— 应该抓得住")
    old = json.loads((ROOT / "docs" / "评估集_跑分_第10课-生成层-跑3.json").read_text(encoding="utf-8"))
    r48 = rows[47]
    g48 = old[47]
    mat = []
    for s in (g48.get("来源") or []):
        cid = s.split(" = ")[0].strip()
        t = con.execute("SELECT 文本 FROM chunk WHERE chunk_id=?", (cid,)).fetchone()
        mat.append({"chunk_id": cid, "文本": t[0] if t else ""})
    ok, miss = check(g48.get("系统答") or "", str(r48.get("问题") or ""), mat)
    print(f"      题48 那版回答:{(g48.get('系统答') or '')[:60]}")
    print(f"      检查结果:{'❌ 缺 ' + str(miss) if miss else '✅ 没抓到'}")
    print()
    print(f"  ★ 适用这类题的共 {hit_n} 道")
    print("  ★★ 它只核【说全了没有】—— 不核「说得对不对」。两件事。")


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    main()
