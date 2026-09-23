# -*- coding: utf-8 -*-
r"""
Agent 的【过程指标】—— 第 23 课。

═══ 为什么要有它（用户给的那份建议里,我最同意的一条）═══
    原来的评估量的全是【答案对不对】。
    ★★ 而那个量不出"Agent 能不能正确执行任务"——
       因为一个"每次都把所有工具都调一遍"的系统,也可能答对。

    ★★★ 它自己的话:
       「证明 Agent 不仅【能回答】,还【能正确执行任务】。」

═══ 五个指标,各怎么拿（★ 三样数据本来就在,只是没统计）═══
    · Tool Selection Accuracy   评估集的「期望去向」 vs 它【选了哪个工具】
    · Retry Rate                agent 记录里的 `重做过`
    · Tool Call Count           `选中` 列表的长度
    · Latency                   在 问() 外面包一层计时
    · Token Cost                ★ llm.py 里刚接出来的 usage

═══ ★★ 那条真值是怎么定的（写在最前面,因为它是这一把尺子的地基）═══
    用户 2026-09-23 选的【甲】:用评估集自己的「期望去向」当真值。

        期望 SQL    → 该选【查表】类（查表 / 查逐项）
        期望 检索   → 该选【查原文】
        期望 拒答   → 该【一个干活工具都不选】（拒答是出口,不是工具）

    ⚠⚠ 而它【只覆盖两个工具】—— 牌子上有六张(查表/查原文/查逐项/抽期次/推期次/抽机场)。
       ★ 抽参数那四个【总是跑】,所以它们不参与"选得对不对"。
       ★★ 所以这一把量的是【干活那两个的选择对不对】,不是全部。
          ★★★ 别把它当成"工具选择全对了" —— 量具只覆盖它覆盖的地方。

=== 怎么用 ===
    python tools/agent_指标.py              # 跑评估集,出五个数
    python tools/agent_指标.py --只跑 10     # 先跑 10 道看看
"""
import sys, io, time, json, sqlite3, argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from paths import DB, DOCS

#  ★ 期望去向 → 该选哪个【干活】工具
该选 = {
    "SQL":   {"查表", "查逐项"},
    "检索":  {"查原文"},
    "拒答":  set(),            # ★ 拒答是出口,不是工具 —— 一个干活工具都不该选
}
干活类 = {"查表", "查原文", "查逐项"}


def 跑一道(智能体, con, 题):
    """问一句,收齐这一轮的【过程数据】。"""
    import llm
    llm.清零()
    a = 智能体(con)
    t0 = time.time()
    try:
        r = a.问(题["问题"])
        错 = None
    except Exception as e:
        r = {"结局": "抛异常", "选中": [], "结果": {}}
        错 = f"{type(e).__name__}: {e}"
    秒 = time.time() - t0

    选 = [x for x in (r.get("选中") or []) if x in 干活类]
    return {
        "题号": 题["题号"],
        "期望去向": 题["期望去向"],
        "实际去向": r.get("去向") or r.get("结局"),
        "结局": r.get("结局"),
        "选了": 选,
        "工具调用数": len(选),
        "重做过": bool(r.get("重做过")),
        "秒": round(秒, 2),
        "调用次数": llm.统计["调用次数"],
        "输入token": llm.统计["输入token"],
        "输出token": llm.统计["输出token"],
        "没有usage": llm.统计.get("★ 这次没有 usage", 0),
        "抛异常": 错,
    }


def 判工具选对没(一条):
    """★ 用「期望去向」当 真值 —— 见文件开头那段。"""
    该 = 该选.get(str(一条["期望去向"]))
    if 该 is None:
        return None                    # ★ 这个去向没有真值,不判
    if 一条["实际去向"] == "拒答":
        #  ★ 它拒答了 —— 那"该不该拒"由【答案对不对】那条尺子管,
        #    而这里问的是"工具选对没":拒答的题【不该选任何干活工具】。
        return len(一条["选了"]) == 0
    if not 该:
        return len(一条["选了"]) == 0
    #  ★ 该选的那类里,【选中了任意一个】就算对(比如 SQL 允许查表或查逐项)
    return bool(set(一条["选了"]) & 该)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--只跑", type=int, default=0, help="只跑前 N 道（试手用）")
    a = ap.parse_args()
    con = sqlite3.connect(DB)
    from agent import 智能体
    import score_eval as S

    题们 = S.read_rows(S.EVAL_IN)
    if a.只跑:
        题们 = 题们[:a.只跑]

    print("=" * 78)
    print("  Agent 的过程指标 —— 量的是【它怎么执行的】，不只是【答对没】")
    print("=" * 78)
    print(f"  题数:{len(题们)}   ★ 真值来源:评估集自己的「期望去向」（用户选的甲）")

    出 = []
    for 题 in 题们:
        print(f"    跑 {题['题号']:>2} …", end="", flush=True)
        条 = 跑一道(智能体, con, 题)
        出.append(条)
        print(f" {条['秒']:>5.1f}s  {条['工具调用数']} 次工具  "
              f"{条['调用次数']} 次调用  {条['输入token']}+{条['输出token']} token")

    #  ── 汇总 ──────────────────────────────────────────
    n = len(出)
    判过 = [(x, 判工具选对没(x)) for x in 出]
    有真值 = [(x, v) for x, v in 判过 if v is not None]
    错选 = [x for x, v in 有真值 if v is False]
    总秒 = sum(x["秒"] for x in 出)
    总调用 = sum(x["调用次数"] for x in 出)
    #  ⚠⚠ 2026-09-23 修:这两个【不是一回事】,而我第一版混了:
    #      · 工具调用数 = 它【选了几个干活工具】  → 1,1,1 共 3
    #      · 调用次数   = 它【调了几次大模型】    → 1,3,1 共 5
    #    ★ 症状:"共 5 次 · 平均 1.67 · 最多 1 次" —— 三个数【自相矛盾】
    #      (3 道题各 1 次,怎么可能共 5 次?)
    #    ★★ 又一个「同一个字段有两个身份」:我拿"调用"这一个词指了两件事。
    总工具 = sum(x["工具调用数"] for x in 出)
    入 = sum(x["输入token"] for x in 出)
    出t = sum(x["输出token"] for x in 出)
    没usage = sum(x["没有usage"] for x in 出)

    print("\n" + "=" * 78)
    print("  ★ 五个指标")
    print("=" * 78)
    if 有真值:
        print(f"  1. Tool Selection Accuracy   {len(有真值)-len(错选)}/{len(有真值)} "
              f"= {(len(有真值)-len(错选))/len(有真值):.0%}"
              f"   ⚠ 只覆盖【查表/查原文/查逐项】三张牌子")
    print(f"  2. Retry Rate                {sum(1 for x in 出 if x['重做过'])}/{n} "
          f"= {sum(1 for x in 出 if x['重做过'])/n:.0%}")
    print(f"  3. Tool Call Count           共 {总工具} 次 · 平均 {总工具/n:.2f} 次/题"
          f" · 最多 {max(x['工具调用数'] for x in 出)} 次"
          f"   ★ 全是【干活类】的(查表/查原文/查逐项)")
    print(f"  4. Latency                   总 {总秒:.0f}s · 平均 {总秒/n:.1f}s/题"
          f" · 最慢 {max(x['秒'] for x in 出):.1f}s")
    print(f"  5. Token Cost                输入 {入:,} + 输出 {出t:,} = 共 {入+出t:,} token"
          f" · 平均 {(入+出t)/n:,.0f}/题")
    print(f"                                ★ 大模型调用共 {总调用} 次 · "
          f"平均 {总调用/n:.2f} 次/题")

    if 没usage:
        #  ★ 这一条【必须出声】—— 不然算出来的成本会偏低,而你看不出来
        print(f"\n  ⚠⚠ 有 {没usage} 次调用【没带 usage】—— 那些 token 记成 0 了,"
              f"所以上面的成本【偏低】。")

    if 错选:
        print(f"\n  ★ 工具选错的 {len(错选)} 道:")
        for x in 错选:
            print(f"      题{x['题号']:>2} 期望 {x['期望去向']:<5} "
                  f"实际去向 {x['实际去向']:<8} 选了 {x['选了']}")
    if 有真值 and not 错选:
        print(f"\n  ★ 工具选错的:0 道 ✅")

    print("\n" + "=" * 78)
    print("""
  ★ 这一把量的是【过程】,而不是【结果】—— 两把尺子要一起看:
     · 结果:score_eval / agent_eval  —— 答对没
     · 过程:这一把                    —— 怎么执行的
  ⚠ 而过程好【不等于】结果好:工具选对了,参数可能错;参数对了,话可能说反。
  ★★ 所以别拿这一把替那一把。""")

    if a.只跑:
        return
    out = DOCS / "agent指标.json"
    out.write_text(json.dumps(出, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n  ★ 明细写到 {out.name}")


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    main()
