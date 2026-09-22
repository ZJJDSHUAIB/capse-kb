# -*- coding: utf-8 -*-
r"""
为什么会"编"?—— 把编出来的那个东西抓出来看。

═══ 为什么需要这个脚本 ═══
    跑分文件里只记了【哪一类】编:
        第39题:第1轮「编了数字」→ 第2轮「编了数字」→ 第3轮 通过
    ★ 而【编的是哪个数、它当时在写什么】—— 没记。

    ★★ 于是"为什么会编"这个问题,靠看跑分文件【答不出来】。
        只能猜。而这个项目一路的规矩是:**不许猜,去量。**

═══ 它做什么 ═══
    对指定的几道题,重跑 N 次生成 —— 每一次都把
      ① 它写出来的原句
      ② 硬判据报出来的那个"编的东西"
    一起打出来。

    ★★★ 然后才有资格谈"为什么":
        看那个数,和材料里的数一对照,原因基本自己就浮出来了。

═══ 用法 ═══
    python tools/why_fabricate.py 39 42          # 默认各跑 5 次
    python tools/why_fabricate.py 39 --n 10
"""
import sys, io, re, json, sqlite3, argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from route import load_airports
import ask
from paths import ROOT, DATA, PROCESSED, DOCS, DB, OUTPUT

SCORES = sorted(DOCS.glob("评估集_跑分_第13课-*.json"),
                key=lambda p: p.stat().st_mtime)


def build_material(con, row):
    """从跑分文件的【来源】列重建当时给它的材料。

    ★ 必须用【它当时真拿到的那几页】—— 不是"库里相关的页"。
      差异就是答案:如果它在编,编的往往是【材料里没有、而它知道】的东西。
    """
    out = []
    for s in (row.get("来源") or []):
        cid = str(s).split(" = ")[0].strip()
        r = con.execute("SELECT 期次,页码,文本 FROM chunk WHERE chunk_id=?",
                        (cid,)).fetchone()
        if r:
            out.append({"chunk_id": cid, "期次": r[0], "页码": r[1], "文本": r[2]})
    return out


def main():
    ap_ = argparse.ArgumentParser()
    ap_.add_argument("nums", nargs="*", type=int, help="题号,可给多个")
    ap_.add_argument("--n", type=int, default=5, help="每题跑几次(默认 5)")
    a = ap_.parse_args()

    con = sqlite3.connect(DB)
    airports = load_airports(con)
    rows = json.load(open(SCORES[-1], encoding="utf-8"))
    from check_eval import read_rows, EVAL_IN
    qs = {r["题号"]: r["问题"] for r in read_rows(EVAL_IN)}

    for no in a.nums:
        row = rows[no - 1]
        hits = build_material(con, row)
        q = qs.get(no, "?")
        print("=" * 78)
        print(f"  第 {no} 题:{q}")
        print(f"  材料 {len(hits)} 页:{[h['chunk_id'] for h in hits]}")
        print("=" * 78)
        材料 = "".join(h["文本"] for h in hits)
        #  ★ 先把材料里的数全列出来 —— 待会儿要拿它对照"编出来的那个数"
        nums = sorted(set(re.findall(r'\d+\.\d+', 材料)))
        print(f"  材料里的所有小数({len(nums)} 个):{nums}")
        print()

        for i in range(1, a.n + 1):
            got = ask.gen_answer(q, hits)
            bn = sorted(ask.audit_answer(got, hits))
            bc = sorted(ask.check_citations(got, hits))
            be = ask.check_entities(got, hits, airports)
            tag = []
            if bn: tag.append(f"★ 编数字 {bn}")
            if bc: tag.append(f"★ 编出处 {bc}")
            if be: tag.append(f"★ 编机场名 {be}")
            print(f"  ── 第 {i} 次 ──  {' / '.join(tag) if tag else '通过'}")
            print(f"     {got[:300]}")
            print()
        print()


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    main()
