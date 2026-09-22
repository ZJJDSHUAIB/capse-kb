# -*- coding: utf-8 -*-
r"""
第 10 课 · 答案页排在【第几位】,大模型才看得见?

═══ 它是从哪来的 ═══
    题 45 上撞出来的:
        答案页排第 1 → 10/10
        答案页排第 2 →  0/10
    ★ 一次换位,100% ↔ 0%。

    然后试了几个修法,发现规律像是"两头好、中间差"。
    ★★ 但那只有【一道题】。这个脚本是【主动把答案页放到每个位置】,
       看那条曲线在别的题上是不是也长这样。

═══ 为什么要主动放 ═══
    之前的数据都是【碰巧】—— 检索给出的顺序恰好把答案页放在哪,就量到哪。
    ★ 那种数据能看出苗头,不能定形状。
    ★★ 定形状要【控制住位置这一个变量】,其他全不动。

═══ ⚠ 这条结论的条件 ═══
    · 这 3 道题 + 当前库 + 当前提示词 + 当前模型
    · 每格只跑 REPS 次 —— 小样本,看形状可以,别抠小数点
"""
import sys, io, sqlite3, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

DB = Path(r"D:\capse-kb\data\processed\capse.db")
OUT = Path(r"D:\capse-kb\docs\第10课_位置测试.txt")
REPS = 6

#  题号 → (问题, 答案页, 材料池(不含答案页的部分), 判对的关键词)
CASES = {
    45: ("2025Q3的CAPSE简介里，CAPSE创立了哪些指标或系统", "2025Q3-P11",
         ["2025Q3-P07", "2025Q3-P13", "2025Q3-P14", "2025Q3-P12"],
         ["净推荐值", "出行意愿"]),
    46: ("2025Q4分吞吐量级服务测评里，4000万级以上机场综合得分前两名是谁", "2025Q4-P18",
         ["2025Q4-P19", "2025Q4-P20", "2025Q4-P07", "2025Q4-P21"],
         ["北京大兴", "深圳宝安", "4.28", "4.27"]),
    50: ("2024Q3报告里“旅客最佳”的定义是什么", "2024Q3-P12",
         ["2024Q3-P05", "2024Q3-P07", "2024Q3-P13", "2024Q3-P11"],
         ["物有所值"]),
}


def main():
    from ask import gen_answer

    con = sqlite3.connect(DB)
    cache = {}

    def mk(cid):
        if cid not in cache:
            r = con.execute("SELECT 期次,页码,文本 FROM chunk WHERE chunk_id=?",
                            (cid,)).fetchone()
            cache[cid] = {"chunk_id": cid, "期次": r[0], "页码": r[1], "文本": r[2]}
        return cache[cid]

    L = ["=" * 88,
         "  第 10 课 · 答案页排第几位,大模型才看得见?",
         "=" * 88,
         f"  每格跑 {REPS} 次;3 道题 × 5 个位置",
         "  ★ 位置是【主动控制】的 —— 其他变量全不动", ""]

    for no, (q, ans_cid, others, keys) in CASES.items():
        L.append(f"  题 {no}  答案页 {ans_cid}   池子 {others}")
        line = []
        for pos in range(1, 6):                       # 插到第 1~5 位
            order = list(others)
            order.insert(pos - 1, ans_cid)
            hits = [mk(c) for c in order]
            ok = 0
            for _ in range(REPS):
                try:
                    a = gen_answer(q, hits)
                except Exception as e:
                    a = f"(出错 {e})"
                if all(k in a for k in keys):
                    ok += 1
                time.sleep(0.15)
            line.append((pos, ok))
            L.append(f"      第 {pos} 位   {ok}/{REPS}   {'█' * (ok * 4)}")
        L.append("")

    L.append("=" * 88)
    L.append("  ★ 怎么读:看那条柱子的形状 —— 两头高、中间低?还是平的?")
    L.append("  ★★ 如果 3 道题的形状【一致】,那条形状才是规律;")
    L.append("      如果不一致,那「位置」这个解释就只对某几道题成立。")
    text = "\n".join(L)
    print(text)
    OUT.write_text(text, encoding="utf-8")
    print(f"\n  ✅ 存到 {OUT}")


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    main()
