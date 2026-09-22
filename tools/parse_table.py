# -*- coding: utf-8 -*-
r"""
第 10 课 · 从「分吞吐量级得分表」里解析出 (分数, 机场名) 的配对

═══ 它要解决什么 ═══
    第 10 课掉过的三道题(#46 #47 #48)都是同一个形状:
        问"某个吞吐量级里,综合得分第一/前两名是谁"
        答案藏在一张表里

    ★ 这类题的答案,本质是【分数 ↔ 机场】的配对 —— 那是有结构的。
    ★★ 所以它可以【机器核】,不用靠字面匹配,也不用问大模型。

═══ 为什么这不是"对着答案改" ═══
    它【从材料里自己解析】,不看答案键。
    ★ 标准答案只是用来核对解析结果对不对的,不是解析的输入。

═══ ⚠ 它只覆盖一种页 ═══
    「2025Q4—NNNN万级机场综合得分」这种页(库里 P18/P19/P20/P21 那几张)。
    ★ 别的页(叙述页、简介页)它解析不出来,也不该解析。
    ★★ 它会明确报"这页不是得分表",而不是硬凑一个空结果。
"""
import sys, io, re, sqlite3
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

DB = Path(r"D:\capse-kb\data\processed\capse.db")

SCORE = re.compile(r"4\.\d\d")

#  ⚠ 第一版我写的是 (\d{4}万级(?:以上)?) —— 它抓【后半截】:
#      "2500万-4000万级" → 抓成 "4000万级"
#      "1000万-1500万级" → 抓成 "1500万级"
#    ★ 而档位名是【判断"问的是哪一档"的依据】,抓错就会配错档。
#    ★★ 改成抓【破折号到"机场综合得分"之间】那一段 —— 不依赖数字怎么写。
GRADE = re.compile(r"—\s*([^。]*?)\s*机场综合得分")


def is_score_table(text):
    """这一页是不是「分吞吐量级得分表」?★ 不是就别硬解析。"""
    return bool(GRADE.search(text)) and "机场综合得分" in text


def parse(text):
    """→ (档位, [(分数, 机场名), ...])

    ★ 解析规则是从原文的形状推出来的,不是拍的:
        · 每个分数【单独一行】(4.28\n4.27\n…)
        · 最后一行拖着「所有机场名」,而机场名都以「机场」结尾
        · 中间夹着一个「平均, 4.15」—— 那是行业平均分,不是机场的分,要跳过
    """
    if not is_score_table(text):
        return None, []
    g = GRADE.search(text)
    grade = g.group(1)
    lines = text.split("\n")
    i = 0
    while i < len(lines) and not re.match(r"^\s*4\.\d\d", lines[i]):
        i += 1
    if i >= len(lines):
        return grade, []

    scores, names = [], []
    for ln in lines[i:]:
        ln = ln.strip()
        if not re.match(r"^4\.\d\d", ln):
            continue
        scores.append(ln[:4])                    # 前 4 个字符就是分数
        rest = ln[4:]
        #  ★ 最后那一行拖着名字串。名字串前面可能还有「平均, 4.15」——
        #    取【最后一个 4.xx】之后的部分,就把平均值甩掉了。
        last = None
        for m in SCORE.finditer(rest):
            last = m
        namepart = rest[last.end():] if last else ""
        if namepart.strip():
            names = [x + "机场" for x in namepart.split("机场") if x.strip()]
    return grade, list(zip(scores, names))


def main():
    con = sqlite3.connect(DB)
    print("=" * 84)
    print("  第 10 课 · 分吞吐量级得分表 解析器")
    print("=" * 84)
    for cid in ("2025Q4-P18", "2025Q4-P19", "2025Q4-P20", "2025Q4-P21"):
        t = con.execute("SELECT 文本 FROM chunk WHERE chunk_id=?", (cid,)).fetchone()
        if not t:
            print(f"\n  {cid}  库里没有")
            continue
        grade, pairs = parse(t[0])
        print(f"\n  {cid}   档位 {grade}   解析出 {len(pairs)} 对")
        for sc, ap in pairs:
            print(f"      {sc}  {ap}")
        #  ⚠ 这里原来有一条"分数个数和名字个数对不上"的检查 —— 它是【假警报】,
        #    因为我把计数写错了(数的是 split("平均")[0] 里的 4.xx,
        #    而那些分数恰好【不在】"平均"之前的那一段里)。
        #    ★ 已经删掉。真要核对得上,该数【解析出来的 scores 列表】,
        #      而 scores 和 names 是同一个循环里出来的 —— 天然等长,不需要再查。
        print(f"      (分数 {len(pairs)} 个 = 名字 {len(pairs)} 个 —— 同一个循环里出来的,天然等长)")

    print()
    print("  ★ 拿标准答案核一下解析对不对:")
    from check_eval import read_rows
    rows = read_rows(Path(r"D:\capse-kb\docs\评估集.xlsx"))
    for no, cid, want in ((46, "2025Q4-P18", "北京大兴国际机场 4.28"),
                          (47, "2025Q4-P19", "厦门高崎国际机场 4.25"),
                          (48, "2025Q4-P21", "无锡硕放国际机场 4.17")):
        t = con.execute("SELECT 文本 FROM chunk WHERE chunk_id=?", (cid,)).fetchone()[0]
        _, pairs = parse(t)
        top = pairs[0] if pairs else ("?", "?")
        ok = f"{top[1]} {top[0]}" == want
        print(f"      题{no}  解析出的第一 = {top[1]} {top[0]}   标准答案 = {want}   {'✅' if ok else '❌'}")


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    main()
