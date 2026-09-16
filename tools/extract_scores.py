# -*- coding: utf-8 -*-
r"""
从 CAPSE 机场服务测评报告中,提取「机场 → 综合得分」。

═══ 为什么这样写 ═══

先说清三件【不做】的事:

  ① 不写死页码 —— 版式年年变:2024 指标体系在 P4,2025 跑到了 P5。
                   所以改成"按内容找页":哪一页的分数最多,哪一页就是得分表页。
  ② 不写死家数 —— 2023/2024 是 41 家,2025 是 42 家。
                   所以家数由数据自己决定,只检查"分数数 == 名字数"。
  ③ 不用白名单 —— 白名单是"过去的快照",会杀死新增机场(无锡硕放)
                   和改名机场(乌鲁木齐地窝堡→天山)。
                   所以只用一个极小的【黑名单】扔掉确定不是机场的噪音,
                   其余一律保留 —— 让不认识的东西暴露出来,而不是被悄悄丢掉。

再说清两处【必须归一化】的排版差异(都是实测发现的):

  ① 分数的排版在 2025Q2 变了:
       2024 及以前: '4.22 \n4.22 \n4.20 \n...'   ← 每行一个
       2025Q2 起  : '4.29 4.26 4.24 4.23 ...'     ← 空格分隔,全挤一行
     更狠的是 2025Q4 同一份文件里两种都有(第9页空格分隔,第18-21页每行一个)。
     解法:不要求"独占一行",改用通用数字正则 \d+\.\d+ 一把抓。

  ② 机场名在 2025 起变成【竖排】:一个汉字一行
       '深\n圳\n宝\n安\n国\n际\n机\n场\n'
     解法:把"夹在两个汉字之间的换行"删掉(就是处理重庆江\n北国际机场的同一招)。

═══ 三道自检 ═══
    ① 分数个数 == 机场名个数      → 不多不少
    ② 分数是降序                  → 顺序没乱位
    ③ 实算平均 == 报告自报平均    → 分数本身取对了(独立信源,最强)

用法:  python D:/capse-kb/tools/extract_scores.py
"""
import sys, io, os, re, glob
import fitz

DATA = r"D:\capse-kb\data"

# ---- 正则 ----
SCORE   = re.compile(r'\d+\.\d+')                                    # 通用,不要求独占一行
AIRPORT = re.compile(r'[\u4e00-\u9fff]+?机场')                        # 注意是 \u9fff 不是 \uf999
DEWRAP  = re.compile(r'(?<=[\u4e00-\u9fff])\s*\n\s*(?=[\u4e00-\u9fff])')  # 合并竖排
AVG     = re.compile(r'平均\s*[：:,，]\s*(\d+\.\d+)')                  # 分隔符有冒号也有逗号

# 黑名单:只放"确定不是机场名"的东西。不认识的一律保留。
NOISE = {"内地机场"}


def find_score_page(doc):
    """按内容找得分表页:哪一页的分数最多,哪一页就是。

    不依赖页码 —— 2025Q4 有 27 页、页页都有数字,靠页码必错。
    """
    best_i, best_n = 0, -1
    for i, page in enumerate(doc):
        n = len(SCORE.findall(page.get_text()))
        if n > best_n:            # 用 > 不用 >=:同分时保留下标最小的那页
            best_i, best_n = i, n
    return best_i


def _check(names, scores, stated_avg, pdf_path, page_i):
    """三道自检。任何一道不过就报错 —— 绝不返回可疑结果。"""
    where = f"{os.path.basename(pdf_path)} 第{page_i + 1}页"

    if not scores:
        raise ValueError(f"{where}:一个分数都没找到")

    if len(names) != len(scores):
        raise ValueError(
            f"{where}:数量对不上 —— 分数 {len(scores)} 个,机场名 {len(names)} 个\n"
            f"    机场名: {names}"
        )

    if scores != sorted(scores, reverse=True):
        raise ValueError(f"{where}:分数不是降序,可能配错位了\n    {scores}")

    if stated_avg is not None:
        calc = round(sum(map(float, scores)) / len(scores), 2)
        if abs(calc - stated_avg) >= 0.005:
            raise ValueError(
                f"{where}:实算平均 {calc} ≠ 报告自报平均 {stated_avg} —— 分数取错了"
            )


def extract(pdf_path):
    """返回 (页号, [(机场名, 分数), ...], 报告自报平均)。

    顺序 = 报告原文顺序(得分从高到低),未做任何重排。
    """
    doc = fitz.open(pdf_path)
    page_i = find_score_page(doc)
    raw = doc[page_i].get_text()
    doc.close()

    m = AVG.search(raw)
    stated_avg = float(m.group(1)) if m else None

    # 归一化两步:① 抹掉"平均：X.XX"(否则它会被当成第43个分数)
    #             ② 合并竖排汉字
    text = AVG.sub(' ', raw)
    text = DEWRAP.sub('', text)

    scores = SCORE.findall(text)
    names = [a for a in AIRPORT.findall(text) if a not in NOISE]

    _check(names, scores, stated_avg, pdf_path, page_i)
    return page_i, list(zip(names, scores)), stated_avg


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    files = sorted(glob.glob(os.path.join(DATA, "CAPSE*.pdf")))
    print(f"共 {len(files)} 份报告\n")
    print(f"{'报告':<26}{'页':>3}{'家数':>5}{'自报均分':>9}{'实算':>7}   第1名 / 最后1名")
    print("-" * 92)

    ok_count = 0
    for f in files:
        try:
            page_i, rows, stated = extract(f)
        except Exception as e:
            print(f"❌ {os.path.basename(f)[:22]:<24} {e}")
            continue
        ok_count += 1
        calc = round(sum(float(s) for _, s in rows) / len(rows), 2)
        print(f"✅ {os.path.basename(f)[:22]:<24}{page_i+1:>3}{len(rows):>5}"
              f"{stated:>9}{calc:>7}   {rows[0][0]}({rows[0][1]}) … {rows[-1][0]}({rows[-1][1]})")

    print("-" * 92)
    print(f"成功 {ok_count} / {len(files)} 份")
