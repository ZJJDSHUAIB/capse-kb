# -*- coding: utf-8 -*-
r"""
第 14 课 · 一次性工具:把写死的 D:\capse-kb\... 换成 paths.py 里的常量。

═══ 为什么要写成脚本,而不是手改 64 处 ═══
    手改 64 处必然漏 —— 而漏掉的那一两处【不会报错】,
    它会在一个别人机器上、在一个不常走的路径上才崩。
    ★ 项目一路的规矩:能算的就别手点。
    ★★ 而且脚本改完之后,【"还剩几处"可以再量一遍】—— 手改就没法验。

═══ 怎么保证没改错 ═══
    ① 先 --dry:打印【每一行改前 / 改后】,人看一眼
    ② 再 --apply:真的写
    ③ 改完【再量一遍】还剩几处(期望是 0)
    ④ 最后跑全量评估 —— 分数不变才算真的没改坏
    ★★ 前三步都是"看起来对",第 ④ 步才是验收。

═══ ⚠ 它只处理【能认出来的形态】═══
    认不出来的,它会【打印出来让人看】,绝不静默跳过 ——
    静默跳过就等于"以为改完了"。
"""
import sys, io, re, glob, argparse
from pathlib import Path

HERE = Path(__file__).resolve().parent
LIT = "D:" + chr(92) + "capse-kb"          # 字面量,D:\capse-kb

#  ★ 顺序要紧:长的在前 —— 否则 \data 会把 \data\processed 先吃掉
ROOTS = [
    (LIT + r"\data\processed\capse.db", "DB"),
    (LIT + r"\data\processed", "PROCESSED"),
    (LIT + r"\data", "DATA"),
    (LIT + r"\docs", "DOCS"),
    (LIT + r"\output", "OUTPUT"),
    (LIT, "ROOT"),
]
NEED = ["ROOT", "DATA", "PROCESSED", "DOCS", "DB", "OUTPUT"]

#  匹配 Path(r"...") 或直接 r"..." / "..."
PAT = re.compile(r'Path\(\s*[rR]?["\']([^"\']+)["\']\s*\)|[rR]?["\']([^"\']+)["\']')
#  ★ 自我赋值: `NAME = NAME` —— 这种行要删掉(import 已经给了它)
SELF = re.compile(r'^\s*(\w+)\s*=\s*(\1)\s*$')


def convert(path_str):
    """把一条写死的路径换成【表达式字符串】。认不出来就返回 None。"""
    for pre, name in ROOTS:
        if path_str == pre:
            return name
        if path_str.startswith(pre + "\\"):
            rest = path_str[len(pre) + 1:].replace("\\", "/")
            return f'{name} / "{rest}"'
    return None


def do(paths, apply=False):
    total = unknown = 0
    for f in paths:
        src = f.read_text(encoding="utf-8")
        if LIT not in src:
            continue
        out, hits, miss = [], 0, []
        for n, line in enumerate(src.split("\n"), 1):
            if LIT not in line or line.lstrip().startswith("#"):
                out.append(line)
                continue
            new, ok = line, False
            for m in list(PAT.finditer(line))[::-1]:
                raw = m.group(1) or m.group(2)
                if not raw.startswith(LIT):
                    continue
                expr = convert(raw)
                if expr is None:
                    miss.append((n, raw)); continue
                #  ★ 原来是 Path(...) 的,整体换成常量;原来是裸串的,换成表达式
                whole = m.group(0).startswith("Path")
                new = new[:m.start()] + expr + new[m.end():]
                ok = True
                hits += 1
            if ok:
                total += hits
                if not apply:
                    print(f"  {f.name}:{n}")
                    print(f"      - {line.strip()}")
                    print(f"      + {new.strip()}")
            #  ⚠ 干跑时也必须放进 out —— 原来这里写的是 continue,
            #    于是那些行【不进 out】,后面那道"删自我赋值"的检查
            #    在干跑里【永远不触发】——
            #    ★ 等于那行删除逻辑没被干跑验过就要上路。
            #    ★★ 第二次干跑才发现的:第一遍那条 `DB = DB` 是我肉眼看出来的,
            #       不是脚本报出来的 —— 而"靠肉眼看"正是这次要消灭的东西。
            out.append(new)
        for n, raw in miss:
            unknown += 1
            print(f"  ⚠ 认不出 {f.name}:{n}  →  {raw}")
        #  ═══ ★★★ 删掉【自我赋值】行 ═══
        #  干跑抓到的:原来那行是 `DB = Path(r"D:\...\capse.db")`,
        #  换完之后变成 `DB = DB` —— 因为 import 已经给了它这个名字。
        #  ★ 这个 bug 会【一次毁掉 47 个文件】,而且干跑一眼就看见了。
        #  ★★ 项目一路的教训在这儿又成立一次:改之前先把清单摊开看。
        kept = []
        for l in out:
            if SELF.match(l):
                if not apply:
                    print(f"  {f.name}: 删掉自我赋值行 → {l.strip()}")
                continue
            kept.append(l)
        out = kept
        if apply and hits:
            text = "\n".join(out)
            #  ★ 加 import(没加过才加),放在最后一个 import 之后
            if "from paths import" not in text:
                #  ⚠⚠ 插入点【不能】靠"最后一个以 import 开头的行"来定 ——
                #     实测踩到:score_eval.py 里有一条【跨行的 import】:
                #         from check_eval import (read_rows, ...,
                #                                 explain_missing, EVAL_IN)
                #     续行【不以 import 开头】,于是插入点落在括号中间 →
                #     直接把文件写成语法错误。
                #  ★ 改用 ast:它知道每个 import 语句【到哪一行结束】。
                #    能算的别用正则猜 —— 在这件事上又成立一次。
                import ast
                tree = ast.parse(text)
                last = max((n.end_lineno for n in ast.walk(tree)
                            if isinstance(n, (ast.Import, ast.ImportFrom))),
                           default=0)
                lines = text.split("\n")
                lines.insert(last, f"from paths import {', '.join(NEED)}")
                text = "\n".join(lines)
            f.write_text(text, encoding="utf-8")
    print(f"\n  {'已改写' if apply else '会改写'} {total} 处;认不出 {unknown} 处")
    return unknown


def count():
    """还有几处【会被改写】的写死路径。

    ⚠ 只数【代码行】,不算注释 —— 注释里的路径是【讲这件事的历史】,
      改掉它反而把记录抹了。★ 而"数出来是 0"要能真的到 0,否则这个数没意义。
    """
    n = 0
    for f in glob.glob(str(HERE / "*.py")):
        #  ★ paths.py 不算:它是【定义这些路径的文件】,
        #    它的说明里本来就该出现那条旧写法(讲这件事的历史)。
        #  ★★ 同理 _migrate_paths.py 自己也不算。
        if Path(f).name in ("_migrate_paths.py", "paths.py"):
            continue
        for line in open(f, encoding="utf-8"):
            if LIT in line and not line.lstrip().startswith("#"):
                n += line.count(LIT)
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="真的写;不加就是干跑")
    a = ap.parse_args()
    #  ⚠⚠ 2026-09-22:paths.py 必须【跳过】—— 它是【定义这些常量的文件】,
    #     改写它 = 让它在自己内部 `from paths import ...`(导入自己)。
    #  ★ 实测踩到:第一版只在计数函数里排除了它,【改写函数里没排除】——
    #    于是 paths.py 被加了自我导入。它当时【还能跑通】,
    #    因为 ROOT/DATA 在后面又被重新赋了一次值,把导入来的那份盖掉了。
    #    **能跑,是靠巧合。** 而"靠巧合能跑"正是这一课要消灭的东西。
    #  ★★ 教训:同一个疏漏,只在一半的地方防住,等于没防。
    files = [Path(p) for p in sorted(glob.glob(str(HERE / "*.py")))
             if Path(p).name not in ("_migrate_paths.py", "paths.py")]
    print(f"★ 改之前:还有 {count()} 处写死的路径\n")
    bad = do(files, a.apply)
    print(f"★ 改之后:还有 {count()} 处写死的路径")
    if bad:
        print(f"  ⚠ 有 {bad} 处认不出 —— 那些要人看,【没被静默跳过】")
    if not a.apply:
        print("\n  这是干跑。看过没问题,加 --apply 再跑一次。")


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    main()
