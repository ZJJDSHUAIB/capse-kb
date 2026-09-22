# -*- coding: utf-8 -*-
r"""
第 12 课 · 最小循环的【自检】:它真的能发现并修掉一个编的答案吗?

═══ 为什么非要造一个假的来试 ═══
    跑全量跑不出这一类 —— 实测:15 道检索题,三条"编"的判据报 0 次。
    ★ 也就是说:**它们从来不响。**
    ★★ 而"从来不响"有两个可能,必须分开:
          甲 系统真的不编   → 那太好了
          乙 判据坏了,编了也不响 → 那是最坏的情况(静默失败)
      不造一个假病例,这两种【分不出来】。

═══ 做法:把真答案改坏,看循环怎么办 ═══
    ① 从跑分结果里拿一道【真答案】(不重跑,省一次调用)
    ② 把其中一个数改成一个材料里没有的数 —— 这就是"编"
    ③ 把大模型换成【头一次返回坏的、第二次返回好的】
       (monkeypatch,不真的调两次)
    ④ 跑 gen_with_retry,看它:
          · 认不认得出"编了数字"
          · 会不会重新生成
          · 第二轮好了没有
          · trace 里有没有把过程记下来

    ★★★ 而这里【不用答案键】—— 判据全是硬的(数在不在材料里)。
        所以这个自检本身不依赖评估集,它是【系统自带】的一道体检。

═══ ⚠ 它测不了什么 ═══
    它测的判据是"数在不在材料里"。它【不测】"数用得对不对"
    (比如方向说反了)。那是另一件事,见 report_gen.py 文件头。
"""
import sys, io, re, json, sqlite3
from pathlib import Path
from paths import ROOT, DATA, PROCESSED, DOCS, DB, OUTPUT

sys.path.insert(0, str(Path(__file__).parent))
#  跑分结果 —— 拿真答案用,不再花一次生成的钱
SCORES = sorted((DOCS.glob("评估集_跑分_第1[23]课-*.json")),
                key=lambda p: p.stat().st_mtime)


def loads():
    d = json.load(open(SCORES[-1], encoding="utf-8"))
    return d, SCORES[-1].name


def hits_of(con, row):
    """从【来源】列把材料重建出来 —— 那列是 "chunk_id = 期次 第 N 页"。"""
    out = []
    for s in (row.get("来源") or []):
        cid = str(s).split(" = ")[0].strip()
        r = con.execute("SELECT 期次,页码,文本 FROM chunk WHERE chunk_id=?",
                        (cid,)).fetchone()
        if r:
            out.append({"chunk_id": cid, "期次": r[0], "页码": r[1], "文本": r[2]})
    return out


def tamper(ans, hits):
    """把答案里第一个【材料里没有的】数…不,反过来:
    把第一个【材料里有的】数改成一个材料里没有的数 —— 造一个"编"。

    ★ 为什么改第一个而不是随便改:要保证改完只犯这一个错,
      别顺手把别的判据也触发了(那样就分不清是谁响的)。
    """
    材料 = "".join(h["文本"] for h in hits)
    for m in re.finditer(r'\d+\.\d+', ans):
        x = m.group(0)
        if x in 材料:                       # 找一个【真的】数
            fake = f"{int(x[0])}.{99}" if x[0] != '9' else "9.99"
            if fake in 材料:
                continue
            return ans.replace(x, fake, 1), x, fake
    return None, None, None


def main():
    import ask
    con = sqlite3.connect(DB)
    data, fname = loads()
    print("=" * 78)
    print(f"  最小循环自检 —— 用的真答案是 {fname}")
    print("=" * 78)

    #  挑一道检索题 —— 三个条件,缺一不可:
    #    ① 材料能从【来源】列重建
    #    ② 答案里【有数】,而且那个数真在材料里(才改得坏)
    #    ③ ★ 答案【没有多版本说明】—— 即不以 "★ 第 N 页在" 开头。
    #       为什么非要这条:系统答 = page_notes + 模型那句,而 page_notes 是
    #       【代码算的】,里面的页码/期数【本来就不在材料里】。
    #       不排掉它,审出来的"编"全是那一块 —— 我第一次就踩了,第39题假报 4 个数。
    #       ★★ 生产代码审的是 `a`(只有模型那句),不含 notes;
    #          而【跑分文件里存的是拼好的整段】—— 这个差本身是个坑,见文末。
    pick = None
    for i, row in enumerate(data):
        if row.get("去向") != "检索":
            continue
        h = hits_of(con, row)
        full = str(row.get("系统答") or "")
        if not h or full.lstrip().startswith("★ 第"):
            continue
        if tamper(full, h)[0] and re.search(r'\d{4}Q\d-P\d\d', full):
            pick = (i + 1, row, h, full)
            break
    if not pick:
        print("  没找到合适的题(需要有数、有出处、材料能重建)"); return
    no, row, hits, good = pick
    材料 = "".join(h["文本"] for h in hits)

    #  ── 造三种"编",再加一种"改不好" ───────────────────────
    bad_num, was, now = tamper(good, hits)
    #  ⚠ 找机场名【要用库里的真名字】,不能用正则抽第一个"XX机场" ——
    #    实测:正则抽到的是「万级以上机场」(档位名),改它根本不是"编一个机场"。
    names = sorted(set(ask.load_airports(con).values()), key=len, reverse=True)
    real_air = next((n for n in names if n in good), None)
    fake_air = "桂林两江国际机场"
    bad_air = (good.replace(real_air, fake_air, 1)
               if real_air and fake_air not in 材料 else None)
    c = re.search(r'\d{4}Q\d-P\d\d', good)
    bad_cite = good.replace(c.group(0), "2025Q4-P99", 1) if c else None

    用例 = [
        ("编了数字", "编了数字", bad_num, f"把 {was} 换成 {now}"),
        ("编了出处", "编了出处", bad_cite, "把出处编号换成一个不存在的页"),
        ("编了机场名", "编了机场名", bad_air,
         f"把「{real_air}」换成「{fake_air}」(材料里没有)"),
        ("三次都编", "编了数字", bad_num, "★ 每次都返回坏的 —— 看它会不会【停下来】"),
    ]

    print(f"\n  第 {no} 题")
    print(f"  真答案:{good[:110]}")
    print(f"  材料   {len(hits)} 页\n")
    print("=" * 78)

    allok = True
    for tag, want, bad, 说明 in 用例:
        if bad is None:
            print(f"\n  【{tag}】跳过 —— 这道题里没有可改的东西")
            continue
        #  把大模型换成【按剧本返回】—— 不真的调
        seq = [bad, bad, bad] if tag == "三次都编" else [bad, good]
        calls = []
        real_gen = ask.gen_answer

        def fake_gen(q, h, *a, **kw):
            i = len(calls); calls.append(i)
            return seq[i] if i < len(seq) else seq[-1]

        ask.gen_answer = fake_gen
        try:
            #  ★ kw 传空:check_missed 是"防漏",和"编"不是一类,
            #    空 kw 让它不响 —— 这样响的就一定是"编"那一条。
            #  ★★ airports 必须传!(这是自检脚本第一次跑出来的错)
            #      diagnose 里那条是 `if airports and check_entities(...)` ——
            #      不传就【整条跳过】,于是"编了机场名"永远不响。
            got, trace = ask.gen_with_retry(
                row.get("问题", "") or "?", "", hits, ask.load_airports(con))
        finally:
            ask.gen_answer = real_gen

        hit = any(want in t for t in trace)
        n = len(calls)
        fixed = got == good
        print(f"\n  【{tag}】{说明}")
        for t in trace:
            print(f"      {t}")
        if tag == "三次都编":
            #  ★ 这一条【期望的不是修好】,是【停得住】——
            #    它是"赌",而赌可能输。输了要带着上限停下,不能无限转。
            ok = hit and n == ask.MAX_RETRY
            print(f"      → 认得出{'✅' if hit else '❌'}  "
                  f"跑了 {n} 次(上限 {ask.MAX_RETRY}){'✅' if n == ask.MAX_RETRY else '❌'}")
            print(f"      → ★ 三次都没修好,带着【最后那一版】出去 ——")
            print(f"        这是【赌输了】,不是 bug。而它没无限转,因为有 MAX_RETRY。")
        else:
            ok = hit and n == 2 and fixed
            print(f"      → 认得出{'✅' if hit else '❌'}  "
                  f"重来{'✅' if n == 2 else '❌'}  修好{'✅' if fixed else '❌'}")
        allok = allok and ok

    print("\n" + "=" * 78)
    if allok:
        print("  ★ 四种情况全对:三种编都能认出来并自己重来一次,")
        print("    而【修不好时不会无限转】—— 它带着上限停下来。")
        print("  ★★ 而'修好了'是【硬判据】说的,不是它自己说的。")
    else:
        print("  ⚠ 有打 ❌ 的 —— 那才是要修的地方。")
    print("""
  ⚠ 这个自检【不证明】系统平时会编 —— 实测 15 道检索题它一次没编。
     它证明的是:【万一编了,这套机制会响,而且会自己重来一次;
                 重来还不行,它会停下来,而不是无限转。】""")


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    main()
