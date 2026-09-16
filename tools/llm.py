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


def chat(prompt, system=None, max_tokens=300, temperature=0):
    """发一次对话请求,返回模型回复的纯文本。"""
    _load_env()
    key = os.environ.get("CAPSE_LLM_KEY")
    if not key:
        raise LLMError("没读到 CAPSE_LLM_KEY —— 检查 .env 在不在,或 .env.example 有没有被复制成 .env")

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
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            data = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        raise LLMError(f"接口返回 {e.code}:{detail}") from e
    except Exception as e:
        raise LLMError(f"连不上:{e}") from e

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
