# -*- coding: utf-8 -*-
"""
探路脚本:把每份报告每一页的"开头一截"打出来,供人工判断每页是什么。

只做侦察,不做提取。
目的:在写提取代码之前,先搞清楚 10 份报告的结构差异在哪。

用法:  python tools/probe_pages.py
"""
import sys, io, glob, os, re, fitz
from paths import ROOT, DATA, PROCESSED, DOCS, DB, OUTPUT

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')


files = sorted(glob.glob(os.path.join(DATA, "CAPSE*.pdf")))
print(f"共 {len(files)} 份报告\n")

for f in files:
    name = os.path.basename(f)
    doc = fitz.open(f)
    print("=" * 76)
    print(f"■ {name}    {doc.page_count} 页")

    for i, page in enumerate(doc):
        # 把所有空白(含换行)压成一个空格,取前 62 字,便于一行看完
        t = re.sub(r'\s+', ' ', page.get_text()).strip()
        head = t[:62] if t else "<空 / 无文字层>"
        print(f"  P{i+1:>2} [{len(t):>4}]  {head}")

    doc.close()
    print()
