# -*- coding: utf-8 -*-
r"""
第 20 课的另一半尺子 —— 量「用户说的话 → 库里的机场名」这一层。

═══ 为什么这一组【比"平均"那一组好量】 ═══
    ★ "平均"那一组没有真值 —— "这句话到底想问什么"是个【判断】,只有人能定。
    ★★ 这一组有真值:「这个说法在这一期里对得上几家机场」——
        ★ 拿库一算就有,不用问大模型,也不用问人。
    ★★★ 所以这一组能【自动判对错】,而那一组不能。

═══ 期望动作不是"认出来",是三种 ═══
    1 家  → 该答它
    ≥2 家 → ★ 该反问"是哪一个"（用户 2026-09-23 定的判据）
    0 家  → 该说找不到，【不许猜】

═══ ★★ 而"几家"必须【按期次算】 ═══
    珠海金湾国际机场  只在 2023Q3
    珠海金湾机场      2024Q1 起 —— 期次【零重叠】
    → 全库看是 2 个名字,而【每一期里只有 1 家】→ 不该反问。
    ★ 这就是"往下推一步":同一期里对不上多个,就不该反问。

═══ 怎么用 ═══
    python tools/机场名字测试.py
    python tools/机场名字测试.py --含认错     # 只列有问题的
"""
import sys, io, sqlite3, argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from paths import DB, DOCS

叫法表 = DOCS / "机场叫法表.md"


def 读叫法():
    """从 md 的表里读说法。★ 表就是输入 —— 改说法不用改代码。"""
    行 = []
    for ln in 叫法表.read_text(encoding="utf-8").splitlines():
        if not ln.startswith("|"):
            continue
        c = [x.strip().strip("`").strip() for x in ln.strip("|").split("|")]
        if len(c) < 2 or not c[0].isdigit():
            continue
        行.append({"号": int(c[0]), "说法": c[1]})
    return 行


def 各家(con):
    """每期有哪些机场 —— ★ 用【表里的】,不另建一份。"""
    out = {}
    for 期, 场 in con.execute("SELECT DISTINCT 期次, 机场 FROM 综合得分"):
        out.setdefault(期, set()).add(场)
    return out


def 真值(期场, 说法):
    """★ 这一句是这一层的【候选实现】:名字里含这个说法 = 对得上。

    ⚠ 这只是【一个候选】,不是定论。要量的是它够不够用 ——
      不够用才轮到向量。★★ 能算的地方,别问大模型。
    返回 {期次: 对得上的机场集合}
    """
    return {期: {a for a in 场 if 说法 in a} for 期, 场 in 期场.items()}


def 期望(各家数):
    """给各期"对得上几家"的取值,判该干什么。

    ⚠ 第一版这里写错了:先判 `len(有)==1` 就返回"该答",
      于是 {0,1}(有的期有、有的期没有)被吞成了"该答"。
      ★ 实测第 24、25、26 行(地窝堡/天山/硕放)就是这么标错的 ——
        它们在 2025Q4 【一家都没有】,而尺子说"该答"。
      ★★ 又一处:量具自己也会静默地判错 —— 所以要拿"取值长得对不对"去对一眼。
    """
    取值 = set(各家数.values())
    if not 取值 - {0}:
        return "找不到"
    if max(取值) >= 2:
        return "该反问"
    if 0 in 取值:
        return "★ 有的期有、有的期没有"
    return "该答"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--含认错", action="store_true", help="只列有问题的")
    a = ap.parse_args()
    con = sqlite3.connect(DB)
    from route import find_airport

    期场 = 各家(con)
    期们 = sorted(期场)
    行 = 读叫法()

    print("=" * 82)
    print("  第 20 课 · 尺子:用户说的话 → 库里的机场名")
    print("  真值算法:某一期里、名字含这个说法的机场有几家")
    print("=" * 82)
    print(f"  {'#':>2} {'说法':<12} {'全库':>4} {'各期家数':<22} {'该干什么':<10} 现有实现认出了什么")
    print("  " + "-" * 78)

    统计 = {"该答": [0, 0], "该反问": [0, 0], "找不到": [0, 0], "★ 有的期有、有的期没有": [0, 0]}
    问题 = []

    for r in 行:
        s = r["说法"]
        对 = 真值(期场, s)
        各 = {p: len(对[p]) for p in 期们}
        全 = len({x for v in 对.values() for x in v})
        该 = 期望(各)
        取值 = sorted({v for v in 各.values()})
        取值显示 = "/".join(str(v) for v in 取值)

        try:
            got = find_airport(con, s)
            gv = got.get("值") if isinstance(got, dict) else got
            把握 = got.get("把握", "?") if isinstance(got, dict) else "?"
            认出 = f"{把握}: {gv}"
        except Exception as e:
            认出 = f"X {type(e).__name__}"

        if 该 in 统计:
            统计[该][1] += 1
        好坏 = ""
        if 该 == "该答":
            好 = isinstance(gv, list) and len(gv) == 1
            统计["该答"][0] += 好
            好坏 = "✅" if 好 else "❌"
        elif 该 == "该反问":
            #  ★ 现有实现【没有反问这个动作】——所以这一格现在【必然不通过】。
            #    要看的不是"通不通过",是"它【有没有硬挑一个】"。
            if isinstance(gv, list) and len(gv) >= 1:
                好坏 = "❌★ 硬挑了一个"
            else:
                好坏 = "✅ 没硬挑"
                统计["该反问"][0] += 1
        elif 该 in ("找不到", "★ 有的期有、有的期没有"):
            if isinstance(gv, list) and len(gv) == 0:
                统计[该][0] += 1
                好坏 = "✅"
            else:
                好坏 = "❌★ 猜了一个"

        if a.含认错 and 好坏.startswith("✅"):
            continue
        print(f"  {r['号']:>2} {s:<12} {全:>4} {取值显示:<22} {该:<10} {好坏} {认出}")

    print("\n" + "=" * 82)
    for k, (对, 总) in 统计.items():
        if 总:
            print(f"  {k:<22} {对}/{总}")
    print("=" * 82)
    print("""
  ★ 三行要分开看,因为代价不一样:
     该答而认不出   → 拒答（看得见，难看但不骗人）
     ★ 该反问而硬挑  → 【静默失败】用户看不出来 ← 这一行最要命
     找不到而猜了   → 同上
  ★★ 而"该几家"是【库能算的】—— 所以这一组有真值，能自动判对错。""")


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    main()
