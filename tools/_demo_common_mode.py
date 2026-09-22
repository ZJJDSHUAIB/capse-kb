# -*- coding: utf-8 -*-
r"""
演示:共同模式失效(common-mode failure)。

问题:cross_check.py 号称"用两条独立路径互验",
     但两条路径用的是【同一组正则】。同一个正则错了,两边一起错。

                 ┌──[正则 R]──> 值 A ┐
     同一份文本 ─┤                    ├─ 比较:一样? → 报告"✅一致"
                 └──[正则 R]──> 值 B ┘
                      ↑ 同一个 R

本脚本不改任何真实文件,只在内存里把正则改坏。
它只回答一个问题:【cross_check 能不能发现这个 bug?】

═══ 结论:分两类 bug,区别在于「产不产出一个像样的错值」 ═══
    ① 匹配不上 → 两边都 None → 交叉校验判"一致",【发现不了】
       但各路径自己的自检会炸(抓不到值就报错)→ 实际被别的东西拦住
    ② 匹配上了但抓错对象 → 两边同一个错值 → 交叉校验判"一致",【发现不了】
       而且这个值形态合法,没有任何自检会怀疑它 → 【谁都拦不住】

    → 共同模式失效真正致命的是 ②。它要的不是"崩",是"像"。
"""
import re, json, sys, io, csv
from pathlib import Path
from paths import ROOT, DATA, PROCESSED, DOCS, DB, OUTPUT

BLANK = re.compile(r'\s+')

GOOD         = r'二级指标(\d+)项'   # 正确
BAD_NO_MATCH = r'二级指标(\d)项'    # 坏法①:丢了 +,匹配不上
BAD_WRONG    = r'指标(\d+)项'       # 坏法②:丢了"二级"限定,抓到了【一级】的数

SAMPLE = "2023Q3-P07"               # 这一期真实口径 = 6+30


def read(raw_text, pattern):
    """模拟两个文件里的提取动作 —— 两条路径【代码完全相同】。"""
    m = re.search(pattern, BLANK.sub('', raw_text))
    return m.group(1) if m else None


def truth():
    for r in csv.DictReader(open(PROCESSED / "capse_meta.csv", encoding='utf-8-sig')):
        if r['期次'] == "2023Q3":
            return r['二级指标数']
    raise SystemExit("meta 表里没有 2023Q3")


def sample_text():
    for line in open(PROCESSED / "capse_chunks.jsonl", encoding='utf-8'):
        c = json.loads(line)
        if c["chunk_id"] == SAMPLE:
            return c["文本"]
    raise SystemExit(f"找不到 {SAMPLE}")


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    text = sample_text()
    TRUE = truth()
    m = re.search(r'.{0,20}二级指标.{0,6}', BLANK.sub('', text))
    print(f"取样: {SAMPLE}    真实二级指标数 = {TRUE}")
    print(f"原文: …{m.group()}…\n")
    print(f"{'正则版本':<16}{'meta读出':>8}{'chunk读出':>10}{'交叉校验':>12}{'值对不对':>10}{'谁拦住了':>14}")
    print("-" * 72)

    cases = [("正常",          GOOD),
             ("坏法① 丢 +",    BAD_NO_MATCH),
             ("坏法② 丢'二级'", BAD_WRONG)]

    for label, pat in cases:
        meta_val = read(text, pat)
        chunk_val = read(text, pat)

        # cross_check 的动作:比两个值
        cross = "报'一致'" if meta_val == chunk_val else "报'不一致'"

        # 值本身对不对
        correct = (meta_val == TRUE)
        verdict = "对" if correct else "★ 错"

        # 谁拦住了它:
        #   交叉校验只有在两边不等时才报警 → 这里两边都相等,它没出力
        #   各路径自己的自检:拿不到值(None)会炸 → 能拦
        if cross == "报'不一致'":
            who = "交叉校验"
        elif meta_val is None:
            who = "各自的内检(炸)"
        elif not correct:
            who = "★ 没人"
        else:
            who = "无需拦(本来就对)"

        print(f"{label:<16}{str(meta_val):>8}{str(chunk_val):>10}{cross:>12}{verdict:>10}{who:>14}")
