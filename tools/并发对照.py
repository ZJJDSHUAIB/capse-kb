# -*- coding: utf-8 -*-
r"""
并发对照 —— 量【把阻塞的活儿挪开】到底值多少秒。

═══ 它在量什么 ═══
    同一台机器上跑【两个只差一个词】的服务:
        8801  --不挪线程池     ← 阻塞的活儿【卡住事件循环】
        8802  (默认)          ← 那活儿被 asyncio.to_thread【挪到线程池】

    然后【同时】打同样多的请求,比总耗时。

★★★ 为什么要三个数,不是两个 ═══
    只有"两个版本的耗时"是【比不出东西来的】——
    你没法判断"快"是快在哪。所以还要一个【单次基线】:
        单次 t1    一个请求自己跑要多久
    ★ 有了它,那两个数才有意义:
        4 并发 ≈ 4 × t1  → 【串行】:它们排队了
        4 并发 ≈ 1 × t1  → 【并行】:它们真的同时在跑
    ★★ 而那正是这个项目一路的规矩:一个数要能读,得先知道它该跟谁比。

⚠ 这个脚本【自己起服务、自己收】—— 跑完不留进程。
⚠ 它不判"哪个更好"。★ 它只把三个数摆出来,判断是人的事。

═══ 怎么用 ═══
    python tools/并发对照.py                 # 默认 4 个并发
    python tools/并发对照.py --并发 8
    python tools/并发对照.py --不复用会话    # ★ 让 N 个请求【共用一段会话】
                                            #   (那样会撞上会话锁 —— 另一个故事)
"""
import sys, io, os, time, json, socket, argparse, subprocess
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

问 = "2025Q4上海浦东国际机场综合得分是多少"


def 端口忙着吗(端口):
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", 端口)) == 0


def 等起来(端口, 秒=60):
    """等这个端口能应 —— ★ 不等的话会量到"连不上"的耗时,那不是一个数。"""
    到 = time.time() + 秒
    while time.time() < 到:
        try:
            import httpx
            r = httpx.get(f"http://127.0.0.1:{端口}/api/health", timeout=2)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def 量(端口, 并发数, 复用会话):
    import httpx
    from concurrent.futures import ThreadPoolExecutor

    def 一题(i):
        #  ★ 默认【每个请求一个会话】—— 那样它们才是【互相独立】的请求。
        #    ⚠ 共用会话的话,它们会撞上【同一段会话自己的锁】,量到的是另一件事。
        会 = "共用" if 复用会话 else f"会{i}"
        return httpx.post(f"http://127.0.0.1:{端口}/api/ask",
                          json={"q": 问, "会话id": 会}, timeout=600)

    #  ═══ ⚠⚠ 2026-09-26 修:基线必须【预热过一次】再量 ═══
    #  【为什么 —— 实测踩到】
    #      第一版直接量第一次调用:2.6 秒
    #      而后面 ②③ 都只有 1.8 秒 —— ★ 比"单次基线"还快。
    #    ★★ 根因:第一次调用是【冷的】(模型要加载、连接要建、向量要热身),
    #       而 ②③ 跑的时候已经是热的了。
    #    ★★★ 后果不是"数不准",是【读数的方式就错了】:
    #       2.6 当分母 → ②/单次 = 4 会被压成 2.8 —— 看起来像"只串了一半",
    #       而真相是"串得干干净净"。★ 差一点就把它读成别的机制。
    #  → 修:先空跑一次丢掉,让它是热的,再量。
    #  ★ 而这正是这个项目那条老规矩的重演:【量具自己也要被量】——
    #    判据没错、逻辑没错,错在"你量的是哪一次"。
    一题(0)                                   # ★ 预热一次,丢掉
    t = time.time(); 一题(0); 单次 = time.time() - t

    #  ② N 个同时
    t = time.time()
    with ThreadPoolExecutor(并发数) as ex:
        list(ex.map(一题, range(并发数)))
    总 = time.time() - t
    return 单次, 总


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--并发", type=int, default=4)
    ap.add_argument("--复用会话", action="store_true")
    a = ap.parse_args()

    for p in (8801, 8802):
        if 端口忙着吗(p):
            print(f"⚠ 端口 {p} 被占了 —— 先关掉那个进程,或者换端口。")
            return 1

    这里 = Path(__file__).parent / "serve_api.py"
    服务 = {}
    for 端口, 参 in ((8801, ["--不挪线程池"]), (8802, [])):
        服务[端口] = subprocess.Popen(
            [sys.executable, str(这里), "--port", str(端口), *参],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            cwd=str(这里.parent), env={**os.environ, "PYTHONIOENCODING": "utf-8"})

    try:
        print(f"★ 等两个服务起来……（各打 {a.并发} 个请求，每个约 1~2 秒）")
        for 端口 in 服务:
            if not 等起来(端口):
                print(f"⚠ {端口} 起不来 —— 没量。")
                return 1

        print(f"\n{'='*66}")
        print(f"  并发对照 —— 单次基线 / 卡住 / 挪开")
        print(f"  共用会话={a.复用会话}   并发数={a.并发}")
        print(f"{'='*66}")

        单次, 卡住 = 量(8801, a.并发, a.复用会话)
        _,    挪开 = 量(8802, a.并发, a.复用会话)

        print(f"\n  ① 单次基线（1 个请求自己跑）        {单次:6.1f} 秒")
        print(f"  ② --不挪线程池（{a.并发} 个同时）       {卡住:6.1f} 秒"
              f"   = {卡住/单次:4.2f} × 单次")
        print(f"  ③ 挪到线程池（{a.并发} 个同时）       {挪开:6.1f} 秒"
              f"   = {挪开/单次:4.2f} × 单次")
        print(f"\n  ★ 省了 {卡住-挪开:.1f} 秒（{a.并发} 个请求）")
        print(f"{'='*66}")
        print("""
  ★ 怎么读这三个数:
      ② ≈ N × 单次  → 它们【排队】了 —— 事件循环被卡住
      ③ ≈ 1 × 单次  → 它们【真在同时跑】
    ⚠ ③ 比 ① 大出一截是正常的(线程池要开销、机器核有限)——
      要看的是【② 和 ③ 差多少】,不是 ③ 能不能等于 ①。
    ★★ 而这个脚本【不判哪个更好】。它只把数摆出来。
""")
    finally:
        for p, proc in 服务.items():
            proc.terminate()
        print("  (两个服务已关)")
    return 0


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.exit(main())
