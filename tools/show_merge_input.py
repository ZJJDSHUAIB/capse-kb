# -*- coding: utf-8 -*-
r"""
第 9 课 · 给你写 merge_rank() 用的"看得见输入"的小工具。

═══ 它解决什么 ═══
    merge_rank(kw_ranked, vec_ranked, k) 的两个输入,你在纸上想不出来 ——
    ★ 因为它们是【库里真实的名次】,不是你能猜的。
    这个工具把它打出来,顺便告诉你【答案在第几位】。

═══ 怎么用 ═══
    python tools/show_merge_input.py 51
        → 用评估集里题 51 的【真实检索词】和【真实答案键】

    python tools/show_merge_input.py "CAPSE 创立 指标 系统"
        → 用你自己给的检索词(不带期次过滤)

    python tools/show_merge_input.py "2024Q2 著作权声明 版权声明" 2024Q2-P14
        → 顺便指定答案键,它就能告诉你答案在第几名

═══ ★ 为什么要标出"答案在第几位" ═══
    因为你写规则的目标就是这个:
        让答案【从第 6 名挤进前 k】,或者【别从第 2 名掉出去】。
    不标出来,你看着 50 个 chunk_id 是没有信息量的。
"""
import sys, io, re, json, sqlite3
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

ROOT = Path(r"D:\capse-kb")
DB = ROOT / "data" / "processed" / "capse.db"
K = 5
PERIOD = re.compile(r"\d{4}Q\d")


def from_eval(no):
    """从评估集拿这个题号【真实用过的检索词】和答案键。"""
    from check_eval import read_rows, EVAL_IN
    rows = read_rows(EVAL_IN)
    gots = json.loads((ROOT / "docs" / "评估集_跑分.json").read_text(encoding="utf-8"))
    for r, g in zip(rows, gots):
        if str(r.get("题号")) != str(no):
            continue
        kws = [p.split(":", 1)[1].strip() for p in (g.get("过程") or []) if "检索用词" in p]
        kw = kws[0] if kws else None
        m = re.search(r"(\d{4}Q\d-P\d+)", str(r.get("出处") or ""))
        return kw, (m.group(1) if m else None), str(r.get("问题") or "")
    return None, None, None


def main():
    from build_search import search_multi
    from vector_search import search_vec

    a1 = sys.argv[1] if len(sys.argv) > 1 else None
    if not a1:
        print(__doc__)
        return

    if a1.isdigit():
        kw, want, q = from_eval(a1)
        if not kw:
            print(f"★ 题 {a1} 不是走检索的题,或者找不到它的检索词。")
            return
        print(f"题 {a1}   问法:{q}")
    else:
        kw, want = a1, (sys.argv[2] if len(sys.argv) > 2 else None)

    per = sorted(set(PERIOD.findall(kw))) or None
    con = sqlite3.connect(DB)
    a = [str(h["chunk_id"]) for h in search_multi(con, kw, k=100000, periods=per)]
    b = [str(h["chunk_id"]) for h in search_vec(con, kw, k=100000, periods=per)]

    def mark(lst, cid):
        if cid not in lst:
            return "★ 全库都没命中"
        r = lst.index(cid) + 1
        return f"★ 第 {r} 名" + ("  ← 在前 k 里 ✅" if r <= K else "  ← 没进前 k ❌")

    print(f"\n检索词:{kw}")
    print(f"期次过滤:{per if per else '关(检索词里没有期次)'}")
    print(f"k = {K}\n")
    print(f"  kw_ranked   共 {len(a)} 条" + (f"   {mark(a, want)}" if want else ""))
    print(f"      {a[:8]}")
    print(f"  vec_ranked  共 {len(b)} 条" + (f"   {mark(b, want)}" if want else ""))
    print(f"      {b[:8]}")
    if want:
        print(f"\n  答案键 = {want}")
    print(f"""
  ★ 你要写的规则,目标就是这个:
        kw_ranked  和  vec_ranked  两个名次表 → 合成一个【最多 {K} 条】的列表,
        让答案键那一块【排进前 {K}】。
  ★ 而"关键词优先,空位补向量"这条能过一部分、过不了另一部分 —— 哪一部分过不了?
        看 kw_ranked 是不是【已经占满了 {K} 个位置,但占错了】。
""")


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    main()
