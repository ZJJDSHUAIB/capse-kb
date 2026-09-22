# -*- coding: utf-8 -*-
r"""
第 10 课 · 量"回答里的内容,有据吗" —— 有据 = 在那 5 页里找得到

═══ ★★★ 口径是【张君杰】定的 ═══
    他 2026-09-19 的原话:
        "1，就 0
         2，算 都没有按照规定的期次来是错  那万一有一期的变了呢?
         3，只允许回答精准  有其他的无关内容都算错"
    后来又补:"甲(内容一样但期次错也算错)"

    落成:回答的内容必须【只来自期望的那一块】。

═══ ⚠⚠ 这份量具改过两版,两版都是【尺子】的错,不是系统的错 ═══

    第一版:按【页码】认亲。
       ★ 错在:同一份内容在不同期里页码不一样
              (2025Q2 的 CAPSE简介在 P11,2025Q4 的在 P23)
       ★★ 结果:14 道判 0 道。

    第二版:按【相似度 ≥ 0.95】认亲。
       ★ 错在:2024Q2-P14 和 2025Q2-P14 只差【一个空格】,
              相似度 0.9286,被 0.95 挡在外面 → 题51 判成"假错"。
       ★★ 病根:同一份内容各期的差异是【连续的】(0字/1空格/8字),
               用阈值切一刀,切错了你看不出来。

    第三版(现在这版):★★ 改两件事 ——
       ① 认亲用【抹掉期次名和空白后精确比对】(第 9 课 page_versions 那一套)
          ★ 能精确比的地方,不该拍一个阈值。
       ② 匹配范围从【全库】改成【给它的那几页】
          ★★ 关键:系统手里只有那 5 页 —— 它不可能从别处抄。
             在全库找匹配,是在【错的池子里找】。
          ★★★ 而这一改,顺带解决两件事:
              · "期次对不对"自然消解(材料里只有那一期)
              · 它变成了第 10 课计划里的【代码校验】——
                量具和校验,本来就是一件事。

═══ 它怎么算(纯代码,不用大模型)═══
    ① 把回答按句号/换行切成段
    ② 每段去【给它的那几页】里找最像的一块 —— 8 字滑窗
    ③ 归类:
         · 在期望那份内容的家族里  → 期望那份   (要的)
         · 在材料里但属于别的页    → 别的页     (判他错)
         · 材料里压根找不到        → ★ 没据     (它自己加的)
    ④ 按他的口径判:只有【全部来自期望那份】才算真对
"""
import sys, io, re, json, sqlite3
from pathlib import Path
from paths import ROOT, DATA, PROCESSED, DOCS, DB, OUTPUT

sys.path.insert(0, str(Path(__file__).parent))

DB = ROOT / "data" / "processed" / "capse.db"
EVAL_IN = ROOT / "docs" / "评估集.xlsx"
NGRM = 8
MIN_SEG = 12
LOW = 0.35


def _sh(t, n=NGRM):
    return {t[i:i + n] for i in range(len(t) - n + 1)}


#  ★ 和第 9 课 page_versions.py 用同一套归一化 —— 不另发明一份。
_PERIOD = re.compile(r"\d{4}Q\d")
_WS = re.compile(r"\s+")


def _norm(t):
    return _WS.sub("", _PERIOD.sub("◇", t or ""))


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

    con = sqlite3.connect(DB)
    chunks = {r[0]: r[1] for r in con.execute("SELECT chunk_id, 文本 FROM chunk")}
    norm_of = {c: _norm(t) for c, t in chunks.items()}
    #  ⚠⚠ 第三版的第四个错,还是同一个病:【格式差异被当成内容差异】。
    #     材料写「一级指标7 项」(数字和「项」之间有个空格),
    #     回答写「一级指标7项」—— 差一个空格,8 字滑窗就错开一位,
    #     8 个窗口只剩 1 个命中 → 判"没据" → 判它错。**又一个假错。**
    #     ★ 修法:匹配前两边都抹掉空白 —— 那正是 _norm 干的事,
    #       我只是没把它用到【找匹配】这一步上,只用到【认亲】上。
    grams = {c: _sh(_norm(t)) for c, t in chunks.items()}

    print("=" * 96)
    print(f"  第 10 课量具 · {tag}")
    print("=" * 96)
    print("  口径(张君杰定):回答的内容必须【只来自期望的那一块】")
    print("  ★ 匹配范围 = 【给它的那几页】(不是全库)—— 系统手里只有那些")
    print()

    tally = {"真对": [], "错": []}
    for r, g in zip(rows, got):
        if g.get("去向") not in ("检索", "检索·0条"):
            continue
        cite = str(r.get("出处") or "")
        if "多版本" in cite:
            print(f"  题 {r['题号']:>3}  ⚠ 多版本题,期望不是一个 chunk,跳过")
            continue
        m = re.search(r"(\d{4}Q\d-P\d+)", cite)
        if not m:
            continue
        want = m.group(1)
        ans = g.get("系统答") or ""

        #  ★ 给它的材料:从来源列表拿
        mat = [s.split(" = ")[0].strip() for s in (g.get("来源") or [])]
        mat = [c for c in mat if c in chunks]
        if not mat:
            print(f"  题 {r['题号']:>3}  ⚠ 来源是空的(可能是 0 条检索),跳过")
            continue
        fam = {c for c in chunks if norm_of[c] == norm_of[want]} & set(mat)

        def classify(seg):
            ss = _sh(_norm(seg))          # ★ 和材料一样,先抹空白再切窗
            if not ss:
                return "认不出", 0.0, []
            sc = [(c, len(ss & grams[c]) / len(ss)) for c in mat]
            top = max(s for _, s in sc)
            if top < LOW:
                return "没据", top, []          # ★ 材料里压根找不到 —— 它自己加的
            ties = sorted(c for c, s in sc if s >= top - 0.02)
            if any(c in fam for c in ties):
                return "期望那份", top, ties
            return "别的页", top, ties

        segs = [s.strip() for s in re.split(r"[。\n]", ans) if len(s.strip()) >= MIN_SEG]
        bucket = {"期望那份": 0, "别的页": 0, "没据": 0, "认不出": 0}
        detail = []
        for s in segs:
            k, sc, ties = classify(s)
            if k == "认不出":
                k = "没据" if not _sh(s) else k
            bucket[k] += len(s)
            detail.append((k, ties, s))

        ok = bucket["期望那份"] > 0 and bucket["别的页"] == 0 and bucket["没据"] == 0
        tally["真对" if ok else "错"].append(r["题号"])
        print(f"  题 {r['题号']:>3}  {'✅ 真对' if ok else '❌ 错'}   答案键 {want}   "
              f"(家族 {len(fam)} 块 / 材料 {len(mat)} 页)")
        print(f"          期望那份 {bucket['期望那份']:>5} 字   "
              f"别的页 {bucket['别的页']:>5} 字   ★ 没据 {bucket['没据']:>5} 字")
        if not ok:
            for k, ties, s in detail:
                if k != "期望那份":
                    print(f"          └ [{k}] {str(ties[:2]):<30} {s[:40]}")

    print()
    print("=" * 96)
    n = len(tally["真对"]) + len(tally["错"])
    print(f"  按张君杰的口径:{n} 道走检索的题里")
    print(f"      真答对  {len(tally['真对']):>2}/{n}   {tally['真对']}")
    print(f"      错      {len(tally['错']):>2}/{n}   {tally['错']}")
    print()
    print("  ★ 和旧口径(答案在不在文本里)比 —— 旧口径下这批题是 15/15。")


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    main()
