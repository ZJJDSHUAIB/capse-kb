# -*- coding: utf-8 -*-
r"""
校验层第一块:用【两条独立路径】核对同一批事实。

═══ 校验什么 ═══
    "某期的口径是多少"这件事,在项目里存了两份:
        capse_meta.csv     —— build_meta_table.py 直接扫 PDF 全文抓出来的【值】
        capse_chunks.jsonl —— build_chunks.py 清洗切块后,再从块里抓出来的【文本】
    两条路径互不相干(一条走全文正则,一条走清洗后的分块),
    所以它们对上,才算"两份提取都没错"。

═══ 为什么这不是多此一举 ═══
    同一个事实的多个副本,有两种用法,结论相反:
        当【校验】用 → 好事:两个独立来源互相印证
        当【数据源】用 → 坏事:副本会漂移,而且——
                        meta 里是【值】(7+28),chunk 里是【文本】("一级指标7项,二级指标28项")
                        文本每次用都要重新解析,而解析正是错误来源
    所以项目规矩:
        【同一个事实可以有多个副本,但必须指定唯一的「真相源」;
          其他副本只能用来校验,不能用来取值。】
        本项目真相源 = capse_meta.csv(结构化、可比较、能答"口径怎么变的")
        chunk 里的那句话 = 副本(供人阅读 / 回答"为什么")

═══ 与前面用过的同一手法 ═══
    extract_scores.py 的第三道自检也是"独立信源":
        实算平均  vs  报告自报平均
    那次抓出了 4 类静默错误。这次是同一个思路,只是跨了两份产物。
"""
import sys, io, json, re, csv
from pathlib import Path

PROCESSED = Path(r"D:\capse-kb\data\processed")
BLANK = re.compile(r'\s+')

# 两种语序都收 —— 报告里 "6项一级指标" 和 "一级指标6项" 都出现过
L1 = [re.compile(r'(\d+)项一级指标'), re.compile(r'一级指标(\d+)项')]
L2 = [re.compile(r'(\d+)项二级指标'), re.compile(r'二级指标(\d+)项')]


def version_in(text):
    """从一段文字里读出 (几+几)。读不出、或读出多个不同值,返回 None。"""
    flat = BLANK.sub('', text)
    a = set().union(*[set(p.findall(flat)) for p in L1])   # 一级指标:两个语序各抓一遍,取并集
    b = set().union(*[set(p.findall(flat)) for p in L2])
    if len(a) == 1 and len(b) == 1:
        return f"{a.pop()}+{b.pop()}"
    return None


def main():
    meta = {r['期次']: r['口径版本']
            for r in csv.DictReader(open(PROCESSED / "capse_meta.csv", encoding='utf-8-sig'))}

    per_period = {}
    with open(PROCESSED / "capse_chunks.jsonl", encoding='utf-8') as f:
        for line in f:
            c = json.loads(line)
            v = version_in(c["文本"])
            if v:
                per_period.setdefault(c["期次"], set()).add(v)

    print(f"{'期次':<9}{'meta表':>8}{'chunk正文':>12}   一致?")
    print("-" * 46)
    ok = True
    for p in sorted(meta):
        got = per_period.get(p, set())
        shown = next(iter(got)) if len(got) == 1 else (f"{len(got)}种" if got else "没写")
        same = (len(got) == 1 and shown == meta[p])
        ok &= same
        print(f"{p:<9}{meta[p]:>8}{shown:>12}   {'一致' if same else '★不一致'}")
    print("-" * 46)
    if not ok:
        raise SystemExit("★ 有不一致 —— 必须查清哪边错,不许改数字")
    print("两条独立路径全部对上。")


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    main()
