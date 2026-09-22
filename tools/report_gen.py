# -*- coding: utf-8 -*-
r"""
第 8 课 · 报告的第二半:**把数据交给大模型组织成话,然后【硬查它有没有造数】。**

═══ 分工(张君杰问"这是硬编码吗"之后定的)═══
    代码管  「说什么数」      ← 硬:报告_data.py 已经把三种比法都算好了
    大模型管「怎么把数说成话」← 软:但它【只能用手里的数】
    代码再查「数有没有出处」  ← 硬:这一环

    **一句话:硬的地方管"有没有"和"对不对",软的地方管"怎么说"。**
    因为"有没有"和"对不对"必须可核;"怎么说"可以灵活。

═══ ★ 这道"硬查"是这个项目第三次用同一个形状 ═══
    第 7 课  检索答错了 → 报警(硬判据:正确的那一页在不在来源里)
    挑战集   规则漏了   → 报警(硬判据:正确页在不在取到的页里)
    现在     报告里出现了一个【数据里没有的数】→ 报警

    **都是同一件事:让"说不出出处的"东西自己冒出来。**

═══ ⚠ 它查不出来的东西(必须写清) ═══
    这道检查只保证【数字都有据】,它【不保证用得对】。
    数字:A 说"比同档低 0.35" —— 数对,但方向说反了。这道检查抓不住。
    **它不是安全保证,是把"完全没查"变成"查了一道"。**
"""
import sys, io, re, json, sqlite3
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

DB = Path(r"D:\capse-kb\data\processed\capse.db")


def collect_numbers(data, acc=None):
    """把 data 里所有数值收成一个集合 —— 这是"允许出现的数"。"""
    if acc is None:
        acc = set()
    if isinstance(data, dict):
        for v in data.values():
            collect_numbers(v, acc)
    elif isinstance(data, (list, tuple)):
        for v in data:
            collect_numbers(v, acc)
    elif isinstance(data, (int, float)) and not isinstance(data, bool):
        acc.add(round(float(data), 2))
        acc.add(int(data)) if float(data).is_integer() else None
    elif isinstance(data, str):
        # ★ 第一版漏了这个分支,于是报了一堆假的"找不到":
        #     '09' '10'  ← 从 "2025Q4-P09" 里切出来的页码
        #     '2025' '3' ← 从 "2025Q3" 里切出来的
        #     '4000'     ← 从 "4000万级以上" 里切出来的
        #     '3.19' '3.31' ← 这些是真的数据,但它们写在 how 字符串里
        #   **数据里一半的数是写在字符串里的**(期次、页码、档位名、自算说明)。
        #   只收数值型 = 判据没跟上数据的形状。这一课第四次了。
        for m in NUM.finditer(data):
            x = float(m.group(0))
            acc.add(round(x, 2))
            if x.is_integer():
                acc.add(int(x))
    return acc


NUM = re.compile(r'\d+(?:\.\d+)?')


# ★ 编号后面必须跟【空白】—— 否则 `**4.23**` 会被剔成 `4`,那就漏了真数据。
#   实测踩过:`**1. 综合得分处于同档中上游**` ——
#   第一版写的是 `\*\*?\d+[.、]\*\*?`,要求数字后紧跟 `**`,而实际是紧跟【空格】→ 没剔掉。
# 编号后面可以是 . 、 : ： —— 实测踩过「**建议 1:」
ORD = re.compile(r'\*\*?\d+[.、:：]\s|^\s*\d+[.、:：]\s|第\s*\d+\s*[名位条项个]', re.M)


def audit(report, data):
    """报告里出现的每一个数,在 data 里找得到吗?返回找不到的那些。

    ★ 抽数之前要先剔掉两类【不是数据】的东西(都实测踩过):
        ① 表格/列表的【编号】  "**1.**" "2. "    ← 排版
        ② 【序数】            "第 1 名" "第 3 位"  ← 说的是"排第几",不是"值是多少"
      不剔的话,它们会被当成"数据里没有的数"报到用户面前 ——
      **而那是【假警报】。假警报多了,真警报就没人看了。**

    ⚠ 剩下的假阳性还是有的(比如某些"N 项"),但已经不影响判读了。
    """
    body = ORD.sub(" ", report)
    allowed = collect_numbers(data)
    bad = set()
    for m in NUM.finditer(body):
        x = float(m.group(0))
        if round(x, 2) in allowed or int(x) in allowed:
            continue
        bad.add(m.group(0))
    return bad


PROMPT = """你在根据【已经查好的数据】写一份机场满意度报告的一段。**只准用这些数据。**

规则(必须遵守):
1. **每一个数字都必须来自下面的数据。你不许自己算、不许自己编。**
2. 如果某个数在数据里没有,就不写它 —— **不要用"大约""可能"来凑。**
3. 说明"这个数从哪来"时,用数据里给的 src(比如 2025Q4-P09)。
4. 数据里标了「自算」的,说明它是算出来的、不是报告原文印的 —— 提到时要写"(自算)"。
5. 同一项若"比全体"和"比同档"结论相反,**两个都要说** —— 那是这个机场的真实处境。

要写的内容:{sections}

数据(JSON):
{data}

直接输出报告正文,不要解释你怎么写的。"""


def main():
    from report_data import build, DB as RDB
    from llm import chat

    con = sqlite3.connect(RDB)
    d = build(con)
    print("=" * 78)
    print(f"  {d['机场']} {d['期次']} —— 生成 + 硬查")
    print("=" * 78)

    brief = json.dumps(d, ensure_ascii=False, default=str)
    prompt = PROMPT.format(sections="1 总体表现 / 2 核心指标 / 3 变化与对比 / 4 问题与亮点",
                           data=brief)
    try:
        report = chat(prompt, max_tokens=1200)
    except Exception as e:
        print(f"  ★ 大模型没跑成:{type(e).__name__}: {e}")
        return

    print("\n──── 大模型写的 ────")
    print(report)

    bad = audit(report, d)
    print("\n" + "=" * 78)
    print("  ★ 硬查:报告里出现的每一个数,数据里有没有?")
    print("=" * 78)
    if not bad:
        print("  ✅ 全部有据 —— 报告里没有一个数是它自己造的")
    else:
        print(f"  ★ 这些数在数据里找不到:{sorted(bad)}")
        print("     它们要么是大模型算的、要么是编的 —— **都不许发出去。**")
    print("""
  ⚠ 这道检查只保证【数字都有据】,不保证【用得对】。
     比如"比同档低 0.35"—— 数对,但方向说反了,它抓不住。""")


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    main()
