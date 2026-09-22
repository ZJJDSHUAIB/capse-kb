# -*- coding: utf-8 -*-
r"""
第 14 课 · 验收:「一个陌生人 clone 下来,能不能真的跑起来?」

═══ 为什么不能靠"我在自己机器上跑一遍" ═══
    我这儿【什么都有】:capse.db、PDF、向量文件、.env ——
    所以"能跑"这件事在我这儿【永远不会失败】。
    ★ 一把永远给满分的量具,测不出任何东西。
    → 所以要造一个【干净的副本】:只放【仓库里会有的那些文件】。

═══ 它做四件事 ═══
    ① 【先记指纹】原目录 capse.db 的 md5 —— 待会儿要查它有没有被动过
       ★ 为什么必须查这个:硬编码路径最坏的形态不是"崩",
         而是【偷偷去改作者机器上那份库】,而且看起来成功了。
    ② 建一个干净副本:按 `git ls-files` 复制(= 别人 clone 到的内容)
    ③ 在副本里【按 README 的顺序】跑一遍
    ④ 检查三样:
         · 副本里有库了吗
         · 原目录的库【动没动】(期望:没动)
         · 副本里问得出答案吗

═══ ⚠ 它不测什么 ═══
    它不测 60 道题的对错 —— 那要花大模型的钱,而且那是 score_eval 的事。
    它只测【能不能跑起来】。两件事,别混。
"""
import sys, io, os, shutil, hashlib, subprocess, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from paths import ROOT, PROCESSED, DB


def md5(p):
    if not Path(p).exists():
        return "(不存在)"
    return hashlib.md5(Path(p).read_bytes()).hexdigest()[:12]


def main():
    print("=" * 78)
    print("  验收:陌生人 clone 下来,能不能跑起来?")
    print("=" * 78)

    #  ① 先记下原目录那份库的指纹 —— 这是防止"偷偷改到作者机器"的探针
    before = md5(DB)
    print(f"\n  ① 原目录的库指纹(改前):{before}")
    print(f"     {DB}")

    #  ② 建干净副本
    tmp = Path(tempfile.mkdtemp(prefix="capse_fresh_"))
    dst = tmp / "capse-kb"
    print(f"\n  ② 建干净副本:{dst}")
    def ls(*args):
        return [x.strip() for x in subprocess.run(
            ["git", "ls-files", *args], cwd=ROOT, capture_output=True,
            text=True, encoding="utf-8").stdout.split("\n") if x.strip()]

    tracked = ls()
    #  ⚠⚠ 2026-09-22:光看 git ls-files 不够 —— 实测踩到。
    #     第一次跑这个验收时,它报"ModuleNotFoundError: No module named 'paths'" ——
    #     ★ 而 paths.py 是【刚写好、还没 git add】的,所以 ls-files 里没有它,
    #       副本里就缺了那个文件,于是【所有】模块都导入失败。
    #     ★★ 那是【验收脚本自己的假警报】,不是项目的问题 ——
    #        而假警报比没警报更坏:它会让我去修一个不存在的问题。
    #  ★★★ 所以补上【未跟踪、但没被 gitignore 的 .py】——
    #      那些是"这份代码的一部分",只是还没来得及提交。
    #      ⚠ 只补 .py:跑分 json 那些是【派生物】,不该混进来。
    fresh = [x for x in ls("--others", "--exclude-standard") if x.endswith(".py")]
    files = tracked + fresh
    n = 0
    for rel in files:
        src, out = ROOT / rel, dst / rel
        if not src.is_file():
            continue
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, out)
        n += 1
    print(f"     复制了 {n} 个文件"
          f"(git 追踪 {len(tracked)} + 还没提交的新 .py {len(fresh)})")
    for x in fresh:
        print(f"       ★ 其中这个是还没提交的:{x}")
    #  ★ 明确报一下【故意不复制】的东西 —— 不静默跳过
    for name, why in (("data/*.pdf", "第三方版权"), ("*.db", "派生物,要重建"),
                      ("*.npz", "派生物,要重建"), (".env", "密钥")):
        print(f"     ✗ 不复制 {name:<12} —— {why}")

    #  ③ 按 README 的顺序跑
    def run(cmd, timeout=300):
        print(f"\n  $ {cmd}")
        r = subprocess.run(cmd, cwd=dst, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout,
                           env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        tail = (r.stdout or "").strip().split("\n")[-6:]
        for l in tail:
            print(f"      {l}")
        if r.returncode != 0:
            err = (r.stderr or "").strip().split("\n")[-4:]
            for l in err:
                print(f"      ⚠ {l}")
        return r.returncode

    rc_db = run(f"{sys.executable} tools/build_db.py")
    #  ═══ ★★★ 2026-09-22 补:重建是【两步】,不是一步 ═══
    #  【为什么补这一步 —— 实测漏掉过】
    #      第一版只跑了 build_db.py,然后问一道 SQL 题,就宣布"全过"。
    #      ★ 而 chunk 表和全文索引是【build_search.py】建的 —— SQL 不用它们,
    #        所以库缺了一大半,那一道题照样答得出来。
    #      ★★ 实测代价:漏掉这步之后,60 道评估从 60/60 掉到 43/60,
    #         而掉的全是「叙述·检索」那 15 道 —— 验收脚本一道都没测到。
    #      ★★★ 所以:验收脚本自己也是"量具只覆盖它覆盖的地方"。
    rc_search = run(f"{sys.executable} tools/build_search.py")
    rc_ask = run(f'{sys.executable} tools/ask.py '
                 f'--ask "2025Q4上海浦东国际机场综合得分是多少"')

    #  ⑤ ★ 直接查库,把【两条路】都点到 —— 不走完整链路,不用大模型
    #     这么测的理由:走完整链路要 key,而"别人刚 clone 下来"恰恰没有 key。
    #     而"库建全了没有"这件事【不需要大模型就能验】。
    import sqlite3
    q = dst / "data" / "processed" / "capse.db"
    db_ok, db_msg = False, ""
    if q.exists():
        try:
            con = sqlite3.connect(q)
            t = {n: con.execute(f"SELECT COUNT(*) FROM {n}").fetchone()[0]
                 for n in ("meta", "综合得分", "指标得分", "机场分档",
                           "chunk", "chunk_fts")}
            #  ★ 真正的判据:全文索引【能搜出东西】(不是"表存在")
            hit = con.execute("SELECT COUNT(*) FROM chunk_fts WHERE chunk_fts MATCH ?",
                              ('"行李服务"',)).fetchone()[0]
            db_ok = t["chunk"] > 0 and hit > 0
            db_msg = (f"四张表 {[t['meta'], t['综合得分'], t['指标得分'], t['机场分档']]} "
                      f"/ chunk {t['chunk']} 块 / 全文索引搜『行李服务』命中 {hit} 条")
            con.close()
        except Exception as e:
            db_msg = f"{type(e).__name__}: {e}"
    print(f"\n  $ 直接查库(不用大模型)")
    print(f"      {db_msg}")

    #  ④ 三项检查
    after = md5(DB)
    got_db = (dst / "data" / "processed" / "capse.db").exists()
    print("\n" + "=" * 78)
    print("  检查结果")
    print("=" * 78)
    print(f"  ① 副本里建出库了吗           {'✅' if got_db else '❌ 没有'}")
    print(f"  ② 原目录的库【动没动】        ", end="")
    if after == before:
        print(f"✅ 没动({after})")
    else:
        print(f"❌ 【被动过!】{before} → {after}")
        print("      → 说明还有写死的路径在指向作者机器。这一条比崩掉更严重。")
    print(f"  ③ 库里【两条路】都在吗        {'✅ 在' if db_ok else '❌ 缺'}"
          f"   ← ★ 加这一条:原来只测了 SQL 那条,而缺索引它照样过")
    print(f"  ④ 副本里问得出答案吗          {'✅ 能' if rc_ask == 0 else '❌ 不能'}")
    ok = got_db and after == before and db_ok and rc_ask == 0
    print()
    if ok:
        print("  ★ 全过:陌生人 clone 下来能跑,而且碰不到作者机器上的东西。")
    else:
        print("  ⚠ 有不过的 —— 那才是要修的地方。")
    print(f"\n  (副本留在 {dst} —— 想再看一眼就去那儿;不要了就整个删掉)")

    #  清理:默认留着,方便出问题时去看
    if ok and "--keep" not in sys.argv:
        shutil.rmtree(tmp, ignore_errors=True)
        print("  (全过了,副本已删掉。想留着看加 --keep)")


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    main()
