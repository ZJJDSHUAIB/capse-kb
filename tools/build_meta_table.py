# -*- coding: utf-8 -*-
r"""
把 9 份 CAPSE 季度报告,汇总成一张元信息表:
    期次 / 样本量 / 机场数 / 一级指标数 / 二级指标数 / 口径版本

═══ 这张表是干什么的 ═══
    capse_scores.csv 里那个 "4.19 分",单独看是个孤立的数字。
    加上这张表,它才被限定成:
        "2023Q3 口径(6+30)、41 家机场、352308 份样本下的 4.19 分"
    【口径版本】那一列就是后面【三档拒答】的总开关:
        问题口径 == 数据口径  → 直接答
        问题跨口径           → 答,但强制标注口径差异
        问题无对应数据       → 拒答

═══ 归一化:先删掉所有空白,再匹配 ═══
    实测发现关键句会被排版切碎,而且切法不统一:
        2023Q3: "CAPSE 有效 样本量 352308 份"    ← "有效"和"样本量"之间断开
        2024Q1: "C APSE 有效 样本量 157819 份"   ← CAPSE 被切成 "C" + "APSE"
        2024Q4: "CAPSE 有效样本量 580610 份"     ← 又连上了
    穷举切法是不可能的。可行解:**空白不携带信息,先全删掉**。
    删完之后上面三种写法统一成 "CAPSE有效样本量NNNNNN份"。
    这就是"不许写死措辞"的具体含义 —— 不是列出所有写法,是不依赖写法。

═══ 指标数:两种语序都要抓,互为交叉验证 ═══
    同一份报告里,同一个数会用两种语序各说一遍:
        第4页: "6 项一级指标,31 项二级指标"      → 数字在前
        第7页: "一级指标 6 项,二级指标 30 项"    → 数字在后
    → 两种语序【分别】提取,合并后必须只剩一个值。
      若两种语序给出不同数字(比如 30 和 31),立刻报错。

═══ 两道自检 + 一道跨文件校验 ═══
    ① 总行数 == 9
    ② 口径版本恰好是 6+30 / 6+31 / 7+28 三种
    ③ 【机场数】来自两个独立信源,必须相等:
         a. 报告原文的 "共测评 N 家"
         b. capse_scores.csv 里该期的实际行数
       (a) 是文本解析,(b) 是另一条完全独立的代码路径数出来的。
       两者对上,才说明 PDF 里的 "N 家" 和表里的 N 行指的是同一批机场。
"""
import sys, io, re, csv
from pathlib import Path
from collections import Counter
import fitz

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, str(Path(__file__).parent))
from build_scores_table import get_pdf_files, get_period
from paths import ROOT, DATA, PROCESSED, DOCS, DB, OUTPUT

SCORES_CSV = PROCESSED / "capse_scores.csv"
OUT        = PROCESSED / "capse_meta.csv"

EXPECTED_ROWS = 9
VALID_VERSIONS = {'6+30', '6+31', '7+28'}

BLANK = re.compile(r'\s+')
# 锚点是"有效样本量" —— 干扰句"国际及港澳台地区机场样本量未达到测评标准"里没有"有效"
SAMPLE  = re.compile(r'有效样本量(\d+)份')
AIRPORT = re.compile(r'(?:共测评|选取)(\d+)家')
L1_FRONT = re.compile(r'(\d+)项一级指标')   # "6项一级指标"
L1_BACK  = re.compile(r'一级指标(\d+)项')   # "一级指标6项"
L2_FRONT = re.compile(r'(\d+)项二级指标')
L2_BACK  = re.compile(r'二级指标(\d+)项')


def squash(text):
    """删掉所有空白。排版怎么切都不影响结果。"""
    return BLANK.sub('', text)


def pick_one(patterns, text, label, where):
    """在若干同义语序里收集取值,要求合并后恰好一个。

    只收集到一个值   → 通过(可能是只有一种语序出现)
    收集到两个不同值 → 报错(两种语序打架,说明切错了)
    一个都没收到     → 报错
    """
    got = set()
    for p in patterns:
        got |= set(p.findall(text))
    if len(got) != 1:
        raise ValueError(f"{where} 的【{label}】抓出 {sorted(got)} —— 应为恰好 1 个值")
    return int(got.pop())


def read_full_text(pdf_path):
    """整份 PDF 的文字拼起来再归一化。

    为什么不按页找:页码会变(2024 在第7页的数,2025 跑到了第5页)。
    这些句子的措辞是唯一的,全文扫不会误伤。
    """
    doc = fitz.open(pdf_path)
    full = squash("".join(page.get_text() for page in doc))
    doc.close()
    return full


def read_meta(pdf_path):
    text = read_full_text(pdf_path)
    where = pdf_path.name
    return {
        "期次":     get_period(where),
        "样本量":   pick_one([SAMPLE], text, "有效样本量", where),
        "机场数":   pick_one([AIRPORT], text, "机场家数", where),
        "一级指标数": pick_one([L1_FRONT, L1_BACK], text, "一级指标数", where),
        "二级指标数": pick_one([L2_FRONT, L2_BACK], text, "二级指标数", where),
    }


def count_airports_in_scores():
    """独立信源②:从已经封板的 capse_scores.csv 里,数每期实际有多少行。

    注意这是【另一条代码路径】——不碰 PDF,只数表。
    它和 PDF 原文的 "共测评 N 家" 对上,才说明两边说的是同一件事。
    """
    with open(SCORES_CSV, encoding='utf-8-sig', newline='') as f:
        return Counter(row['期次'] for row in csv.DictReader(f))


def check(rows, csv_counts):
    if len(rows) != EXPECTED_ROWS:
        raise ValueError(f"总行数 {len(rows)} ≠ 期望 {EXPECTED_ROWS} —— 去找原因,别改数字")

    rows = sorted(rows, key=lambda r: r["期次"])

    for r in rows:
        ver = f"{r['一级指标数']}+{r['二级指标数']}"
        if ver not in VALID_VERSIONS:
            raise ValueError(f"{r['期次']}: 口径版本 {ver} 不在 {sorted(VALID_VERSIONS)} 里 —— 说明指标数切错了")
        r["口径版本"] = ver

        # 跨文件校验:PDF 里说的家数 == 表里实际的行数
        from_pdf = r["机场数"]
        from_csv = csv_counts.get(r["期次"])
        if from_csv is None:
            raise ValueError(f"{r['期次']}: 在 capse_scores.csv 里没有这一期")
        if from_pdf != from_csv:
            raise ValueError(
                f"{r['期次']}: PDF 说 {from_pdf} 家,capse_scores.csv 里却有 {from_csv} 行 —— 两处对不上")

    return rows


def write_csv(rows, path):
    cols = ["期次", "样本量", "机场数", "一级指标数", "二级指标数", "口径版本"]
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    rows = [read_meta(f) for f in get_pdf_files()]
    rows = check(rows, count_airports_in_scores())     # ← 先自检
    write_csv(rows, OUT)

    print(f"写出 {OUT}  ({len(rows)} 行)\n")
    print(f"{'期次':<8}{'样本量':>9}{'机场数':>7}{'一级':>5}{'二级':>5}   口径")
    for r in rows:
        print(f"{r['期次']:<8}{r['样本量']:>9}{r['机场数']:>7}"
              f"{r['一级指标数']:>5}{r['二级指标数']:>5}   {r['口径版本']}")
