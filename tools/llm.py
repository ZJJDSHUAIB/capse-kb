# -*- coding: utf-8 -*-
r"""
接大模型 —— 但它在第 5 课这条链里的位置是【判】,不是【答】。

═══ 它只干三件事,一件数据都不产出 ═══
    ① 判意图   这题问的是【一个数】还是【一段话】?(第②步,张君杰 4/10 两题的答案)
    ② 改查询   把"报告的测评指标为什么调整过"变成能搜的词
    ③ 找同义   用户说"调整",原文写的是"变更"

    数据全部来自:SQL 查表 / 检索查原文。
    → 所以"答案必须带来源"才成立 —— 来源是现成的,不是模型编的。
    → 如果让模型自己答题,它就没有来源可给,这一条规则立刻塌掉。

═══ 温度 = 0 ═══
    这是【判断】任务,不是创作任务。同一个问题问两遍,必须给同一个答案。
    温度调高 = 同一句话两次问出两个结果,那验证层就没法验了 ——
    你没法为一次"碰巧对了"的判断背书。

═══ 用标准库,不引第三方包 ═══
    urllib 就够。项目里少一个依赖,别人 clone 下来就少一步装包。
    代价:要自己拼 JSON、自己设超时、自己认错误码。都写在下面了。

═══ 密钥不进代码 ═══
    从 .env 读,.env 被 .gitignore 排除。
    这个仓库是要给面试官看的 —— key 一旦进过 git 历史,删不干净,只能作废。
"""
import os, json, urllib.request, urllib.error
from pathlib import Path

ENV = Path(__file__).resolve().parent.parent / ".env"
TIMEOUT = 60


def _load_env(path=ENV):
    """读 .env 到环境变量。四行,不需要 python-dotenv。"""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


class LLMError(RuntimeError):
    """调用失败了。故意单独一个异常类型 —— 上层能区分
    【模型说不知道】和【模型没连上】,这两件事要说给用户不同的话。"""


#  ═══ ★★★ 2026-09-23 加:调用计数(给 Agent 过程指标用) ═══
#  【为什么 —— 用户给的那份建议里最同意的一条】
#     「证明 Agent 不仅能回答,还【能正确执行任务】」——
#     而"执行"是有代价的:几次调用、多少 token、几秒。
#     ★ 而这三样【原来一个都没记】。
#
#  【★★ 而 Token 这件事有意思:它【本来就在响应里】,只是被扔了】
#     原来的代码:`return data["choices"][0]["message"]["content"]`
#     ★★ 而 data 里还有 `usage: {prompt_tokens, completion_tokens}` ——
#        一个字没取。
#     ★★★ 所以不是"拿不到",是"没接"。而"没接"的东西,
#         量的时候才会发现它不在了。
#
#  ⚠ 用模块级累加器,而不是让 chat() 多返回一个值 ——
#    因为 chat() 的调用点【遍布全项目】,改返回值会动一圈。
#    而累加器【零侵入】:调用方一个字不用改。
统计 = {"调用次数": 0, "输入token": 0, "输出token": 0, "总秒数": 0.0}


def 清零():
    """★ 量之前先清零 —— 不然上一轮的账会混进来。"""
    for k in 统计:
        统计[k] = 0 if k != "总秒数" else 0.0


def chat(prompt, system=None, max_tokens=300, temperature=0):
    """发一次对话请求,返回模型回复的纯文本。"""
    _load_env()
    key = os.environ.get("CAPSE_LLM_KEY")
    if not key:
        raise LLMError("没读到 CAPSE_LLM_KEY —— 检查 .env 在不在,或 .env.example 有没有被复制成 .env")
    #  ═══ ★★★ 2026-09-22 加这道守卫 —— 实测踩到,而且报错完全误导 ═══
    #  张君杰 clone 之后照 README 做:`cp .env.example .env`(还没填 key),
    #  然后跑 make_report.py —— 崩了,而报错是:
    #      UnicodeEncodeError: 'latin-1' codec can't encode characters in position 10-15
    #
    #  ★ 那个错【一个字都没提 key】。因为失败发生在 urllib 编 HTTP header 的时候 ——
    #    header 只能用 latin-1,而当时 .env.example 的占位符是中文(「sk-换成你自己的」),
    #    中文过不了那道编码。
    #
    #  ★★ 而上面那道"没读到 KEY"的守卫【没拦住】——
    #     因为 key 不是空的,它是「sk-换成你自己的」。
    #     **守卫判的是【在不在】,而问题出在【填得对不对】。**
    #  ★★★ 又是"量具只覆盖它覆盖的地方":它覆盖了"没填",没覆盖"填了个假的"。
    #
    #  → 所以补一道:key 必须是 ASCII。不是 ASCII,就一定不是真 key。
    if not key.isascii():
        raise LLMError(
            "CAPSE_LLM_KEY 里有非 ASCII 字符 —— 多半是 .env.example 里那个占位符"
            "没换成真 key。\n"
            f"      现在读到的是:{key[:16]}…\n"
            "      → 打开 .env,把这一行换成你自己的 API key。\n"
            "      (★ 顺带说:如果不加这道检查,你会收到的报错是"
            "『latin-1 codec can't encode…』—— 那个错完全看不出和 key 有关。)")

    msgs = ([{"role": "system", "content": system}] if system else []) + \
           [{"role": "user", "content": prompt}]
    body = json.dumps({
        "model": os.environ.get("CAPSE_LLM_MODEL", "deepseek-chat"),
        "messages": msgs,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }).encode("utf-8")

    req = urllib.request.Request(
        os.environ.get("CAPSE_LLM_BASE", "https://api.deepseek.com") + "/chat/completions",
        data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
    )
    import time as _t
    _t0 = _t.time()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            data = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        raise LLMError(f"接口返回 {e.code}:{detail}") from e
    except Exception as e:
        raise LLMError(f"连不上:{e}") from e

    #  ★★★ 记账 —— 而它【不吞掉任何东西】:usage 有就记,没有就记 0
    #    ⚠ 而"没有 usage"这件事【要说出来】,不能让 token 悄悄是 0:
    #      那样算出来的成本会偏低,而你【看不出来】。
    统计["调用次数"] += 1
    统计["总秒数"] += _t.time() - _t0
    _u = data.get("usage") or {}
    if not _u:
        统计["★ 这次没有 usage"] = 统计.get("★ 这次没有 usage", 0) + 1
    统计["输入token"] += _u.get("prompt_tokens", 0)
    统计["输出token"] += _u.get("completion_tokens", 0)

    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError) as e:
        raise LLMError(f"返回体不是预期结构:{str(data)[:300]}") from e


if __name__ == "__main__":
    import sys, io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    print("--- 冒烟测试:能不能连上 ---")
    try:
        print("回复:", chat("只回三个字:连上了"))
    except LLMError as e:
        print("★ 失败:", e)
