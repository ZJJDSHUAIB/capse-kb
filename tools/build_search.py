# -*- coding: utf-8 -*-
r"""
第 3 课:把 54 个 chunk 装进一个能【搜】的结构 —— 检索基线版。

═══ 为什么先做关键词检索,不直接上向量 ═══
    不是为了省事,是因为【它是向量检索的对照组】。

        关键词检索: 找【精确的词】        —— "口径"这种专有名词,它更准
        向量检索  : 找【意思最像的】      —— 换个说法也搜得到,但可能跑偏

    第 7 课要做"按页切 / 按段切 / 固定字数"的对照实验。
    要做对照,就得先有基线。没有基线,"向量检索更好"这句话你永远说不出口 ——
    更好?比谁好?好多少?
    → 这个文件就是那个基线。它现在是【未来实验的对照组】,不是"临时凑合"。

═══ 坑一:中文全文检索,SQLite 的默认分词器是坏的 ═══
    FTS5 默认分词器 unicode61 按"非字母数字"切词。
    中文没有空格,所以 —— 【一整句中文被当成一个词】。

        实测:插入 "2025Q4内地机场综合得分包含测评项目机场交通"
              unicode61  搜 '机场交通' → 命中 0   ← 静默失败,不报错
              trigram    搜 '机场交通' → 命中 1

    所以必须显式指定 tokenize='trigram'(按三字滑窗切)。
    ※ 代价:trigram 只能做【子串匹配】,查询词至少要 3 个字。
      "口径"这种 2 字查询它不认 —— 见 search() 里的兜底。

    —— 教训:默认配置不等于正确配置,而且它【不报错】。
      你不主动拿一个已知答案去试,会一直以为它在正常工作。

═══ 坑二:索引不是真相源 ═══
    这个设计里有两样东西:
        chunk      表      ← 【真相源】,存文本
        chunk_fts  索引    ← 【派生结构】,自己不存文本(content='chunk')

    用 external content 的写法(不复制文本)是为了守住"单一真相源"——
    但代价是:【改了 chunk 表,索引不会自动跟着变,它会静默变旧】。
    所以建完之后必须 'rebuild',而且自检里要专门验"索引和真相源一致"。

    —— 这正是上一课说的「副本会漂移」。这次漂移发生在库里,不在文件里。

═══ 检索要返回什么(这个决定将来能不能溯源) ═══
    只返回文本是不够的。必须带上:
        chunk_id / 期次 / 页码 / 匹配得分 / 原文
    因为将来大模型基于这段话说了一句话,你得能【指回原文的哪一页】。
    没有出处 = 无法判断它是不是在编。这是防幻觉的地基,不是可选项。

═══ 自检 ═══
    ① 索引里的 chunk 数 == 真相源里的 chunk 数
    ② 索引没漂移:从索引查到的文本,和 chunk 表里的逐字相同
    ③ 【已知答案检索】:拿一个答案已知的问句去搜,看正确那块排第几
       —— 这一条才是真的在验"能搜到",前两条只验"装进去了"
"""
import sys, io, re, json, sqlite3
from pathlib import Path

PROCESSED = Path(r"D:\capse-kb\data\processed")
DB        = PROCESSED / "capse.db"
CHUNKS    = PROCESSED / "capse_chunks.jsonl"

DEFAULT_K = 5

SCHEMA = """
-- 真相源:文本只有这一份
CREATE TABLE chunk (
    chunk_id TEXT PRIMARY KEY,
    期次     TEXT NOT NULL,
    页码     INTEGER NOT NULL,
    字符数   INTEGER NOT NULL,
    页类型   TEXT NOT NULL,
    文本     TEXT NOT NULL
);

-- 派生结构:外部内容索引,自己不存文本(content='chunk')
-- tokenize='trigram' 是中文能搜的前提,默认的 unicode61 会静默失效
CREATE VIRTUAL TABLE chunk_fts USING fts5(
    文本,
    content='chunk',
    content_rowid='rowid',
    tokenize='trigram'
);
"""

# FTS5 的 MATCH 有自己的语法(AND/OR/NOT/引号/星号)。
# 用户随手打的标点会把它当运算符,轻则搜不到,重则报错。
# 所以查询词先净化:只留中文字、字母、数字 —— 其余一律去掉。
SAFE = re.compile(r'[^\u4e00-\u9fff\w]')
MIN_TRIGRAM = 3          # trigram 索引的最小查询长度


def build():
    if DB.exists():
        DB.unlink()
    sys.path.insert(0, str(Path(__file__).parent))
    from build_db import build as build_core          # 先建结构化那三张表
    con, source = build_core()

    con.executescript(SCHEMA)
    rows = []
    with open(CHUNKS, encoding='utf-8') as f:
        for line in f:
            c = json.loads(line)
            rows.append((c["chunk_id"], c["期次"], c["页码"],
                         c["字符数"], c["页类型"], c["文本"]))
    con.executemany("INSERT INTO chunk VALUES (?,?,?,?,?,?)", rows)

    # 外部内容索引必须显式 rebuild,否则索引是空的
    con.execute("INSERT INTO chunk_fts(chunk_fts) VALUES('rebuild')")
    con.commit()
    return con, source, rows


def searchable(query):
    """这个查询够不够长,能被 trigram 索引处理?

    【为什么不把这个判断塞进 search() 里】
      因为"查不了"和"查了没有"必须能分开。
      两者都返回空列表的话,调用方(第 5 课的路由)就会把
      "查询太短"误判成"库里没有这个知识" ——
      然后回一句"知识库中没有相关内容",把工具的限制说成了知识的缺失。
      → 分开表达,是让上层能说出正确的话。
    """
    return len(SAFE.sub('', query)) >= MIN_TRIGRAM


def search(con, query, k=DEFAULT_K):
    """检索入口。返回按相关度排序的 chunk 列表。

    第 5 课的路由会直接调这个函数 —— 所以它必须是个函数,不是一个脚本。
    注意:调用前先用 searchable() 判断,否则无法区分"太短"和"没命中"。
    """
    q = SAFE.sub('', query)
    if len(q) < MIN_TRIGRAM:
        return []
    sql = """
        SELECT c.chunk_id, c.期次, c.页码, bm25(chunk_fts) AS 得分, c.文本
        FROM chunk_fts JOIN chunk c ON c.rowid = chunk_fts.rowid
        WHERE chunk_fts MATCH ?
        ORDER BY 得分
        LIMIT ?
    """
    return [{"chunk_id": r[0], "期次": r[1], "页码": r[2],
             "得分": round(r[3], 3), "文本": r[4]}
            for r in con.execute(sql, (f'"{q}"', k))]


def search_multi(con, query, k=DEFAULT_K):
    """多关键词检索。按空格拆开,每个词各搜一遍,按最相关合并。

    ═══ 为什么不能直接把整串丢进 search() ═══
        第 5 课把大模型接进"检索前改写问句"那一步,它把
            "报告的测评指标为什么调整过"
        改写成
            "测评指标 调整 变更 修订"
        如果直接丢给 search(),SAFE 会把空格去掉变成
            "测评指标调整变更修订"
        而 trigram 是【短语匹配】—— 它要求这几个字在原文里【挨着出现】。
        原文里没有这个串 → 命中 0。

        → 关键词之间是【或】的关系,不是【与】。
          用户列了四个词,只要命中【任意一个】就应该算命中。
          这是"改写了但没接对线"的典型:两种东西都对,接在一起就不对。

    ═══ 合并规则 ═══
        每个词各返回一批,同一个 chunk 可能被多个词命中 —— 算它的最好成绩
        (bm25 是负数,越小越相关,所以取 min)。
        这样"被多个词同时命中"的块会浮上来,这是对的:它更相关。
    """
    best = {}
    for term in query.split():
        if not searchable(term):
            continue                      # 单个词太短,trigram 处理不了,跳过它
        for h in search(con, term, k=k):
            cid = h["chunk_id"]
            if cid not in best or h["得分"] < best[cid]["得分"]:
                best[cid] = h
    return sorted(best.values(), key=lambda h: h["得分"])[:k]


def check(con, source, chunks):
    """① 数量一致  ② 索引没漂移  ③ 已知答案检索"""
    n_chunk = con.execute("SELECT COUNT(*) FROM chunk").fetchone()[0]
    n_fts   = con.execute("SELECT COUNT(*) FROM chunk_fts").fetchone()[0]
    if n_chunk != len(chunks) or n_fts != len(chunks):
        raise ValueError(f"数量对不上: 真相源 {n_chunk}, 索引 {n_fts}, 源文件 {len(chunks)}")
    print(f"  ① 真相源 {n_chunk} 块,索引 {n_fts} 块  ✅")

    # ② 索引漂移检查:逐块比对索引查到的文本 vs 真相源里的文本
    drift = []
    for cid, text in con.execute("SELECT c.chunk_id, c.文本 FROM chunk c"):
        got = con.execute("""SELECT c.文本 FROM chunk_fts JOIN chunk c
                             ON c.rowid = chunk_fts.rowid
                             WHERE chunk_fts MATCH ? AND c.chunk_id = ?""",
                          (f'"{text[:12]}"', cid)).fetchone()
        if got is None or got[0] != text:
            drift.append(cid)
    if drift:
        raise ValueError(f"索引漂移了: {drift[:5]} —— 索引和真相源不一致")
    print(f"  ② 索引与真相源逐字一致  ✅")

    # ③ 已知答案检索 —— 前两条只验"装进去了",这一条才验"搜得到"
    #    ※ 这是【冒烟测试】:3 条,用来证明工具本身没坏。
    #      真正的评估集(几十道题、答案从原文逐条核对)是第 6 课的事,不由我代笔。
    SMOKE = [
        ("出发机场特色",   "2023Q3-P05", "2023年删掉的一个二级指标"),
        ("行李服务",       "2023Q3-P07", "2023Q3 的一级指标之一(后来被换掉)"),
        ("航班不正常保障", "2025Q4-P07", "2025Q4 的一级指标之一"),
    ]
    for q, expect, why in SMOKE:
        got = [h["chunk_id"] for h in search(con, q, k=5)]
        status = "✅" if expect in got else "★"
        if expect not in got:
            raise ValueError(f"检索断了: 查 {q!r} 该命中 {expect},实际 top5 = {got}")
        print(f"  ③ 查 {q!r:<16} → {got[0]:<12} (期望含 {expect})  {status}  {why}")

    return n_chunk


def demo(con):
    print("\n=== 检索演示 ===")
    for q in ["口径", "口径是什么", "样本量", "有效样本量", "航班不正常保障"]:
        if not searchable(q):
            print(f'\n  "{q}"  ({len(SAFE.sub("", q))} 字)  → 【没搜】:少于 {MIN_TRIGRAM} 字,trigram 索引不支持')
            continue
        hits = search(con, q)
        if not hits:
            print(f'\n  "{q}"  → 【搜了,但没命中】:库里确实没有这段话')
            continue
        print(f'\n  "{q}"')
        for h in hits[:3]:
            head = h["文本"][:46].replace("\n", " ")
            print(f'      {h["得分"]:>8}  {h["chunk_id"]:<12} {head}…')


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    con, source, chunks = build()
    print(f"写出 {DB}(重建:三张结构化表 + chunk + chunk_fts)\n")
    print("=== 自检 ===")
    check(con, source, chunks)
    demo(con)
    con.close()
