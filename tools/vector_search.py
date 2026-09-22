# -*- coding: utf-8 -*-
r"""
第 9 课 · 最小的向量检索 —— **不用框架,只装那个不能自己写的东西。**

═══ "最小"是什么意思 ═══
    向量检索需要三样:
        ① 把文字变成数字的模型        ← ★ 只有这个必须装
        ② 一个存放数字的地方           ← 自己写(存文件)
        ③ 一个算"两串数字像不像"的方法   ← 自己写(余弦相似度)

    **所以这里只有 ① 是外来的,② ③ 都在你看得见的这几行里。**

    ★ 对比一下"不最小"的做法:
        装 LangChain + Chroma + 一个 embedding 库
        → 上面三样全被包起来,你不知道中间发生了什么,
          也不知道出了问题该去哪找。

═══ 为什么必须用模型,不能自己写 ═══
    能自己写:  存数字、算距离、排序、取前 k        ← 那是【逻辑】
    不能自己写:把「著作权声明」和「法律声明」变成"很接近的两串数字"
               ← 那需要一个【见过几亿句话的模型】才知道这两个词意思有多近

    实测(装完立刻验的):
        「著作权声明」vs「法律声明」 → 0.722
        「著作权声明」vs「机场安检」 → 0.197
    **如果这两个数拉不开,那模型就白装了 —— 所以先验这个,再谈别的。**

═══ ⚠ 它和关键词检索的分工(这才是本课要回答的)═══
    关键词检索  按【字面】找 —— 那五个字得连在一起
    向量检索    按【意思】找 —— 不管字,只管意思像不像

    ★ 所以它治的是:「两句话意思一样,但一个字都不重合」
      —— 比如你问"计算机",书上写"电脑"。

    ★★ 而 #51 那种(「著作权声明」vs「法律声明」)—— 字重合一半,意思也近。
       两种办法【都可能】治得了。而哪一种更值 —— 【要量,不许推】。
"""
import sys, io, json, sqlite3
from pathlib import Path

import numpy as np
from paths import ROOT, DATA, PROCESSED, DOCS, DB, OUTPUT

DB = PROCESSED / "capse.db"
VEC_FILE = PROCESSED / "capse_vectors.npz"      # ② 存放数字的地方 —— 就是一个文件
MODEL = "BAAI/bge-small-zh-v1.5"

_MODEL = None


def model():
    """模型只加载一次 —— 它跑起来慢,反复加载是浪费。"""
    global _MODEL
    if _MODEL is None:
        #  ⚠⚠ 必须先设这个,再 import sentence_transformers。
        #
        #  实测踩过(2026-09-22):没设它的时候,huggingface_hub 每次加载模型
        #  都会【联网检查更新】。而网络一不通,它就卡在重试上 ——
        #  跑一个几秒钟的脚本,几分钟才报出
        #      RuntimeError: Cannot send a request, as the client has been closed.
        #  ★ 而那个报错【指向 httpx,不指向"模型加载"】——
        #    看起来像网络库的 bug,不像"它在联网检查"。
        #
        #  ★★ 模型早就下过了(第一次装的时候花了 83 秒),本地有缓存。
        #     这次联网【毫无必要】—— 只是默认行为。
        #  ★★★ 所以强制离线。**依赖本地已缓存的东西,就别让它去网上找。**
        import os
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
        from sentence_transformers import SentenceTransformer
        _MODEL = SentenceTransformer(MODEL)
    return _MODEL


def build(con):
    """把库里每一块编码成向量,存起来。**一次性** —— 以后查就快了。

    ★ 为什么存文件而不是每次重算:
       54 块要跑 10 秒左右。而检索是【每次问都要做】的。
       算一次、存下来,以后只算问句那一条 —— 那是几十毫秒的事。
    """
    ids = [r[0] for r in con.execute("SELECT chunk_id FROM chunk ORDER BY chunk_id")]
    texts = [r[0] for r in con.execute("SELECT 文本 FROM chunk ORDER BY chunk_id")]
    print(f"  编码 {len(ids)} 块…")
    vecs = model().encode(texts, normalize_embeddings=True, show_progress_bar=False)
    np.savez(VEC_FILE, ids=np.array(ids), vecs=vecs)
    print(f"  ✅ 存到 {VEC_FILE.name}  ({vecs.shape[0]} 块 × {vecs.shape[1]} 个数字)")
    return ids, vecs


def load(con):
    """读向量。没有就先建。"""
    if not VEC_FILE.exists():
        return build(con)
    d = np.load(VEC_FILE, allow_pickle=True)
    ids = list(d["ids"])
    have = [r[0] for r in con.execute("SELECT chunk_id FROM chunk ORDER BY chunk_id")]
    if ids != have:                      # ★ 库变了 → 向量过期 → 重建
        #  ※ 为什么要查这个:向量是【派生数据】,它会漂移。
        #    改了库不重建,它就会拿旧向量去配新文本 —— 而且不报错。
        print("  ⚠ 库变了,向量过期 —— 重建")
        return build(con)
    return ids, d["vecs"]


def search_vec(con, query, k=5, periods=None):
    """用意思找。返回和 search() 一样的结构 —— 那样上层不用改。"""
    ids, vecs = load(con)
    qv = model().encode([query], normalize_embeddings=True)[0]
    sims = vecs @ qv                     # ③ 余弦相似度:归一化之后就是点积
    order = np.argsort(-sims)            # 越大越像
    out = []
    for i in order:
        cid = ids[i]
        row = con.execute("SELECT 期次, 页码, 文本 FROM chunk WHERE chunk_id=?",
                          (cid,)).fetchone()
        if periods and row[0] not in periods:
            continue                     # ★ 期次过滤照样管用 —— 它和检索方式无关
        out.append({"chunk_id": cid, "期次": row[0], "页码": row[1],
                    "得分": round(float(sims[i]), 3), "文本": row[2]})
        if len(out) >= k:
            break
    return out


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    con = sqlite3.connect(DB)
    print("① 建向量")
    build(con)
