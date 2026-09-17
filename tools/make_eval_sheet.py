# -*- coding: utf-8 -*-
r"""
第 6 课 · 生成评估集填写模板。

═══ 这个脚本干什么 ═══
    生成 docs/评估集.xlsx —— 60 行空位,题号和类别已经排好,等张君杰填。
    【它不生成任何一个问题】。出题是他的活,这一课的核心产出就是那 60 道。

═══ 为什么封面是"类别"而不是"题号顺序" ═══
    出题的时候人是按【类别】想的:"什么算一道该拒答的题"。
    如果随机排序,他要为每一道题单独想一遍"这题算什么类型",那是白费力气。
    → 同类挨着排,他可以一口气想完一类,再换下一类。

═══ 为什么"出处"这一列要写成【机器能读的键】而不是一段话 ═══
    这是整个模板里唯一一个【为了机器】做的设计。理由:

        标准答案错了,整把尺子就废了 —— 而且是静默地废。
        你以为系统答错了,跑去改代码,越改越糟。

    防御办法和第 2 课一样:【两条独立的路,对得上才算数】。
        你:人工读 PDF → 写标准答案
        脚本:拿你写的出处 → 去库里/原文里取值 → 得到值
        两边对不上 → 有一边错了,摊开给你看

    但这件事有个前提:脚本得知道你让他去哪查。
    "报告第 5 页那张表" 脚本读不懂;"表=综合得分;期次=2025Q4;机场=上海浦东国际机场"
    脚本一个 SQL 就能取到值。所以出处的格式必须定死(见"填表说明"页)。

    ※ 注意分清两件事:
      出处是给【机器核对】用的,不是给【人看】的。
      人看的出处是 "capse_scores.csv 期次=2025Q4" 那种,机器读不了分号键值对。
      这个取舍是有意的 —— 机器核对能覆盖 60 道,人工核对只能抽查几道。

    ※ 而"对不上"不自动等于"系统错了"。对不上时脚本把三样一起摊开:
          你写的标准答案 / 系统答的 / 库里实际的值
      由人判。框架假装能自动分辨"人错了"和"系统错了",那才是真的危险。

═══ 为什么结果不写在同一个文件里 ═══
    你填的 xlsx 是【真相源】,跑分结果是【派生物】。
    而且 Excel 打开着文件时脚本写不进去(文件锁)。
    → 结果写到 docs/评估集_结果.xlsx,你填的那份永远只有你填的东西。
    这也是为什么"系统实录"没有做成这个文件里的第二张表 ——
    你写标准答案的时候,系统答案不该出现在旁边(会不自觉地往上靠)。
"""
import sys, io
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.utils import get_column_letter

OUT = Path(r"D:\capse-kb\docs\评估集.xlsx")

# ── 60 道的分配(2026-09-16 张君杰确认) ─────────────────────
# 原则:按【系统会怎么失败】分配,不是按【用户会怎么问】分配。
# 所以"应拒答"给了 10 道(它是最贵的失败:答错了用户能核,拒错了用户不知道),
# "叙述·检索"给了 15 道(它最容易静默失败:搜不到就是 0,不报错)。
ALLOC = [
    ("数值·单点",   8,  "问某一期某个机场的一个数。最基础的一类,用来发现'连基本查询都错'"),
    ("数值·比较",   8,  "两期/两个机场比。跨口径的题在这里 —— 系统必须自己查口径,不许凭感觉"),
    ("数值·排名",   5,  "前 N 名 / 排第几。SQL 也会静默答错的一类(排名是派生量)"),
    ("数值·指标",   6,  "一级指标级的数据。库里【只有 2025Q4 一期】—— 这是语料的真实形状,不是缺失"),
    # ※ 这一类原来叫"应拒答"。2026-09-16 张君杰填题时改的 —— 他往这一类里
    #   同时放了【该拒的】和【不该拒的】,两类都写"该答的有没有被拒"。
    #   他补上了我漏掉的方向:真按"应拒答"命名,这一类就永远考不出【过度拒答】,
    #   而那恰恰是第 4 课最贵的失败(拒错了,用户拿不到数据而且不会知道)。
    #   → 名字改成"拒答·双向":考的是拒答判得对不对,两个方向都考。
    ("拒答·双向",  10,  "该拒的拒了没有 + 不该拒的有没有被拒。两个方向都要有"),
    ("叙述·检索",  15,  "答案在文字里。最容易静默失败:检索返回 0 条,不报错,看着像'库里没有'"),
    ("边界·刁钻",   8,  "规则会【有把握地判错】的问法。'表现如何''什么水平''涨了吗'"),
]

# 第一批要填哪几行(各类至少一道,用来先把格式跑通)
# 理由:先填 10 道 → 发现格式问题 → 再填 50 道。
# 反过来是写完 60 道才发现格式要改。
FIRST_BATCH = {
    0, 1,          # 数值·单点 第 1、2 道
    8,             # 数值·比较 第 1 道
    16,            # 数值·排名 第 1 道
    21,            # 数值·指标 第 1 道
    27, 28,        # 应拒答   第 1、2 道
    37, 38,        # 叙述·检索 第 1、2 道
    52,            # 边界·刁钻 第 1 道
}

HEADERS = [
    ("题号",           6,  "已填好,1~60。别改 —— 结果文件靠它对齐"),
    ("批次",           6,  "1 = 先填这 10 道(黄底),发我核对格式;2 = 格式没问题后填剩下的 50 道"),
    ("类别",          12,  "已填好。按【系统会怎么失败】分的。填的过程中觉得哪类不合适,可以改,但改完告诉我"),
    ("问题",          46,  "你写的问句。【要像真实用户会问的】,不要写成 SQL。口语没关系 —— 口语才是系统真正的输入"),
    ("期望去向",      10,  "SQL / 检索 / 拒答 三选一(下拉)。这一列是【你的判断】,不是抄系统的"),
    ("期望答案",      22,  "数值题填数(如 4.23);排名题填名次(如 5/42);拒答题填'不回答';检索题填关键点(如'新增靠桥率')"),
    ("出处",          42,  "【机器读的】,必须按格式写,否则脚本读不懂。格式见'填表说明'页。拒答题留空"),
    ("拒答理由",      26,  "只有拒答题填。写【为什么拒】。与出处是两样东西:一个答案里,来源和理由是分开的"),
    ("这题在测什么",  30,  "用一句话写。例:'测系统会不会把跨口径的数字直接比'。面试时被问'你怎么设计的评估集',答案在这一列"),
]

# ── 样式 ──────────────────────────────────────────────
H_FILL   = PatternFill("solid", fgColor="1F3864")
H_FONT   = Font(color="FFFFFF", bold=True, size=10)
FIRST_F  = PatternFill("solid", fgColor="FFF2CC")   # 第一批:黄底
GRAY_F   = PatternFill("solid", fgColor="F2F2F2")   # 已预填的列
THIN     = Side(style="thin", color="BFBFBF")
BORDER   = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)

TITLE = Font(bold=True, size=13, color="1F3864")
SUB   = Font(bold=True, size=10, color="1F3864")
MONO  = Font(name="Consolas", size=9)


def build_fill_sheet(ws):
    ws.freeze_panes = "D2"
    for c, (name, width, _) in enumerate(HEADERS, 1):
        cell = ws.cell(1, c, name)
        cell.fill, cell.font, cell.border = H_FILL, H_FONT, BORDER
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.column_dimensions[get_column_letter(c)].width = width
    ws.row_dimensions[1].height = 30

    # 逐类铺满 60 行
    row, n = 2, 0
    for 类别, count, _ in ALLOC:
        for _ in range(count):
            idx = n
            ws.cell(row, 1, idx + 1)
            ws.cell(row, 2, 1 if idx in FIRST_BATCH else 2)
            ws.cell(row, 3, 类别)
            for c in (1, 2, 3):
                ws.cell(row, c).fill = GRAY_F
                ws.cell(row, c).font = Font(size=10, bold=(idx in FIRST_BATCH))
            ws.cell(row, 2).alignment = Alignment(horizontal="center")
            ws.cell(row, 1).alignment = Alignment(horizontal="center")
            ws.cell(row, 3).alignment = Alignment(horizontal="center")
            for c in range(1, len(HEADERS) + 1):
                cell = ws.cell(row, c)
                cell.border = BORDER
                if cell.font.size is None or c > 3:
                    cell.font = Font(size=10)
                if c in (4, 6, 7, 8, 9):
                    cell.alignment = Alignment(vertical="top", wrap_text=True)
            if idx in FIRST_BATCH:
                for c in range(4, len(HEADERS) + 1):
                    ws.cell(row, c).fill = FIRST_F
            ws.row_dimensions[row].height = 30
            row += 1
            n += 1

    dv = DataValidation(type="list", formula1='"SQL,检索,拒答"', allow_blank=True,
                        showErrorMessage=True, errorTitle="只能填这三个",
                        error='去向只有三种:SQL / 检索 / 拒答。判不出是系统的状态,不是标准答案。')
    ws.add_data_validation(dv)
    dv.add(f"E2:E{row - 1}")


def build_help_sheet(ws):
    ws.column_dimensions["A"].width = 14
    ws.column_dimensions["B"].width = 96
    ws.column_dimensions["C"].width = 60
    r = 1

    def para(text, font=None, col=1, span=2, height=None):
        nonlocal r
        ws.cell(r, col, text).font = font or Font(size=10)
        ws.cell(r, col).alignment = Alignment(vertical="top", wrap_text=True)
        if span > 1:
            ws.merge_cells(start_row=r, start_column=col, end_row=r, end_column=col + span - 1)
        if height:
            ws.row_dimensions[r].height = height
        r += 1

    def table(rows, widths=(14, 96)):
        nonlocal r
        for i, (a, b) in enumerate(rows):
            ca = ws.cell(r, 1, a)
            cb = ws.cell(r, 2, b)
            ca.alignment = Alignment(vertical="top", wrap_text=True)
            cb.alignment = Alignment(vertical="top", wrap_text=True)
            ca.border = cb.border = BORDER
            if i == 0:
                ca.fill = cb.fill = H_FILL
                ca.font = cb.font = H_FONT
            else:
                ca.font = Font(size=10, bold=True)
                cb.font = Font(size=10)
            ws.row_dimensions[r].height = None
            r += 1
        r += 1

    para("填表说明", TITLE)
    para("")
    para("一、你担心的那件事:标准答案写错了怎么办", SUB)
    para("标准答案错了,整把尺子就废了 —— 而且是【静默地】废:你以为系统答错了,跑去改代码,越改越糟。"
         "所以这个模板里,【出处】那一列不是给你看的,是给脚本读的。脚本拿它自动去库里取值,"
         "跟你写的标准答案逐字比。对不上就摊开给你看 —— 你写的 / 系统答的 / 库里实际的,三样一起。", Font(size=10))
    para("但『对不上』不自动等于『系统错了』。可能是你写错了,也可能是库错了。脚本不该替你判这个。", Font(size=10))
    para("")
    para("二、出处怎么写(这一列格式错,脚本就只能报『这行我读不懂』)", SUB)
    table([
        ("题型", "出处格式(分号分隔的键=值;必须用英文分号和等号)"),
        ("综合得分", "表=综合得分;期次=2025Q4;机场=上海浦东国际机场"),
        ("排名/名次", "表=综合得分;期次=2025Q4;机场=上海浦东国际机场;字段=排名"),
        ("样本量", "表=meta;期次=2025Q4;字段=样本量"),
        ("机场数", "表=meta;期次=2025Q4;字段=机场数"),
        ("口径版本", "表=meta;期次=2025Q4;字段=口径版本"),
        ("一级指标得分", "表=指标得分;期次=2025Q4;机场=上海浦东国际机场;指标=机场交通"),
        ("前 N 名", "表=综合得分;期次=2025Q4;取前=5"),
        ("叙述题", "chunk=2023Q3-P05      (多个用英文逗号: chunk=2024Q1-P05,2024Q1-P07)"),
        ("拒答题", "留空 —— 拒答题要的是【理由】,不是出处。理由填在右边那一列"),
    ])
    para("　可用的期次(9 个):2023Q3 / 2024Q1 / 2024Q2 / 2024Q3 / 2024Q4 / 2025Q1 / 2025Q2 / 2025Q3 / 2025Q4", MONO)
    para("　可用的指标(7 个,只有 2025Q4 有):机场交通 / 机场服务与设施 / 机场商贸 / 机场安检 / 出港服务 / 进港服务 / 航班不正常保障", MONO)
    para("　机场名要写全称。库里是「上海浦东国际机场」「北京首都国际机场」这种,不是「浦东」「首都机场」", Font(size=10, italic=True))
    para("　可用的 chunk:\n" + "、".join(sorted(
        ["2023Q3-P05", "2023Q3-P07", "2023Q3-P11", "2023Q3-P12", "2023Q3-P13", "2023Q3-P14",
         "2024Q1-P05", "2024Q1-P07", "2024Q1-P11", "2024Q1-P12", "2024Q1-P13", "2024Q1-P14",
         "2024Q2-P05", "2024Q2-P07", "2024Q2-P11", "2024Q2-P12", "2024Q2-P13", "2024Q2-P14",
         "2024Q3-P05", "2024Q3-P07", "2024Q3-P11", "2024Q3-P12", "2024Q3-P13", "2024Q3-P14",
         "2024Q4-P05", "2024Q4-P07", "2024Q4-P11", "2024Q4-P12", "2024Q4-P13", "2024Q4-P14",
         "2025Q1-P07", "2025Q1-P10", "2025Q1-P11", "2025Q1-P12", "2025Q1-P13",
         "2025Q2-P07", "2025Q2-P11", "2025Q2-P12", "2025Q2-P13", "2025Q2-P14",
         "2025Q3-P07", "2025Q3-P11", "2025Q3-P12", "2025Q3-P13", "2025Q3-P14",
         "2025Q4-P07", "2025Q4-P18", "2025Q4-P19", "2025Q4-P20", "2025Q4-P21",
         "2025Q4-P23", "2025Q4-P24", "2025Q4-P25", "2025Q4-P26"])), MONO)
    para("")
    para("三、出题时最容易犯的错(都是这个项目里真实踩过的)", SUB)
    table([
        ("错误", "为什么错 / 怎么避免"),
        ("凭印象写标准答案", "第 4 课真实发生过:凭『感觉口径变了』去拒答,一查 meta 发现 2025Q1→Q4 压根没变过。"
                            "→ 写答案前【先去库里查一遍】,出处那一列就是逼你查的"),
        ("把『判不出』当标准答案", "去向只能填 SQL/检索/拒答 三种。『系统判不出』是系统的状态,不是正确答案。"
                                  "如果你自己也判不出这题该去哪 —— 那说明这题本身有问题,换一道"),
        ("出题出成 SQL", "『查询 2025Q4 上海浦东的综合得分』不是用户会说的话。用户会说『上海浦东去年考了多少分』。"
                        "口语、模糊、指代不清 —— 那才是系统真正的输入,也才是能暴露问题的输入"),
        ("只出系统能答对的题", "全是送分题,评估集就变成自我表扬。"
                              "应拒答那 10 道、边界那 8 道,就是专门出给系统答不对的"),
    ])
    para("")
    para("四、我会怎么核对(你填完之后脚本做的事)", SUB)
    table([
        ("步骤", "做什么"),
        ("① 读出处", "按上面的格式解析。解析不了的行 → 单独报『这行我读不懂』,不静默跳过"),
        ("② 去查", "数值题:一个 SQL 取到值。叙述题:去 chunk 表看那段原文里有没有你写的关键点"),
        ("③ 比", "你写的标准答案 vs 库里实际的值。一致 → 打勾"),
        ("④ 分歧摊开", "不一致 → 三样一起列给你:你写的 / 系统答的 / 库里实际的。不替你判谁对"),
        ("⑤ 出结果", "写到 docs/评估集_结果.xlsx。你填的这份从头到尾只有你填的东西"),
    ])
    para("　为什么先填 10 道:先跑通格式,再扩到 60。反过来是写完 60 道才发现格式要改。", Font(size=10, bold=True))
    para("")


def guard(out_path, force):
    """★ 地雷:这个脚本是【重新生成】整个文件的。谁再跑一次,已填的题就没了。

    ※ 为什么必须拦:
      它是一个【看起来无害】的命令 —— "重新生成模板",听起来就是刷新一下。
      而实际上它会静默地删掉 60 道题的工作量,而且删完文件看起来很正常(就是空的)。
      这正是第 3 课说的"坏了":错了你看不出来。
      → 所以它必须自己知道自己会造成什么,并且拒绝。
    """
    if force or not out_path.exists():
        return
    from openpyxl import load_workbook
    try:
        ws = load_workbook(out_path, data_only=True)["填题"]
        filled = [r[0] for r in ws.iter_rows(min_row=2, values_only=True) if r[3]]
    except Exception as e:
        print(f"读不出来 {out_path}({e})—— 先关掉 Excel 再试")
        sys.exit(1)
    if filled:
        print(f"★ 拒绝执行:{out_path} 里已经有 {len(filled)} 道填好的题"
              f"(题号 {filled[:10]}{'…' if len(filled) > 10 else ''})。")
        print("  这个脚本会【重新生成整个文件】,你填的东西会没。")
        print("  确实要重来一遍,加 --force。")
        sys.exit(1)


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="明知会覆盖已填的题,也要重新生成")
    args = ap.parse_args()
    guard(OUT, args.force)

    wb = Workbook()
    ws = wb.active
    ws.title = "填题"
    build_fill_sheet(ws)
    build_help_sheet(wb.create_sheet("填表说明"))
    wb.active = 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    wb.save(OUT)
    print(f"已生成: {OUT}")
    print(f"  填题页: 60 行,标黄的是第一批要填的 {len(FIRST_BATCH)} 道")
    for 类别, count, _ in ALLOC:
        print(f"    {类别:<12} {count:>2} 道")


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    main()
