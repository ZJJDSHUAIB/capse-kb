# -*- coding: utf-8 -*-
r"""
反解 2025Q4 的【指标权重】。

═══ 为什么这件事能做 ═══
    报告从不公布权重。但 2025Q4 同时给了两样东西:
        capse_indicators.csv —— 42 家机场 × 7 个一级指标的分
        capse_scores.csv     —— 42 家机场 × 1 个综合得分
    如果综合得分 = Σ w_i × 一级指标_i,那就是 42 个方程解 7 个未知数 —— 可解。
    【这就是"用自己的表,反推报告的隐含参数"】:
      报告没说的事,可以用报告自己给的数据逼出来。

═══ 数学处理 ═══
    约束 Σw_i = 1(加权平均的定义),把 w_7 用 1-Σw_1..6 代掉:
        综合 = Σ_{1..6} w_i·x_i + (1-Σ w_i)·x_7
        → 综合 - x_7 = Σ_{1..6} w_i·(x_i - x_7)
    变成 6 元【无截距】线性回归,普通最小二乘即可。

═══ 必须验的质疑:拟合好 ≠ 参数可信 ═══
    7 个一级指标都是同一批机场的分数,天然高度相关。
    相关性强的时候,回归能拟合得很漂亮,但权重可以任意漂移 —— 那是假象。
    所以必须查三样:
        ① cond(D)      设计矩阵条件数。几十~一百多属正常;上千就要警惕。
        ② 权重标准误    权重本身的不确定度。若区间横跨 0,这个权重就没意义。
        ③ 残差量级      分数只保留两位小数,残差若 ≲0.01 就是四舍五入噪声,不是模型误差。

═══ 结果(capse_indicators.csv / capse_scores.csv 实测) ═══
    机场服务与设施 0.357 ± 0.022     机场安检       0.124 ± 0.020
    机场交通       0.143 ± 0.016     出港服务       0.109 ± 0.024
    航班不正常保障 0.097 ± 0.008     进港服务       0.097 ± 0.024
    机场商贸       0.073 ± 0.014
    cond(D)=82,残差最大 0.0072(低于两位小数的舍入下限)

═══ ⚠ 三条边界,不许越界使用 ═══
    ① 【这是我反解出来的,不是 CAPSE 公布的】。可以当"高度可信的推断",
        不能在报告里写成"CAPSE 官方权重"。
    ② 【只对 2025Q4 成立】。其余 8 期指标集不同(6+30 / 6+31),权重的分母都不一样,
        不能把这套权重套到别的期次上。
    ③ 两位小数的舍入噪声还在,±0.02 量级的差异不要当回事。
        但 0.357 与 0.073 之间的差距,远超噪声。
"""
import sys, io, csv
from pathlib import Path
import numpy as np
from paths import ROOT, DATA, PROCESSED, DOCS, DB, OUTPUT

INDICATORS = ['机场交通', '机场服务与设施', '机场商贸', '机场安检',
              '出港服务', '进港服务', '航班不正常保障']
PERIOD = "2025Q4"


def load():
    rows = list(csv.DictReader(open(PROCESSED / "capse_indicators.csv", encoding='utf-8-sig')))
    overall = {r['机场']: float(r['得分'])
               for r in csv.DictReader(open(PROCESSED / "capse_scores.csv", encoding='utf-8-sig'))
               if r['期次'] == PERIOD}
    per = {}
    for r in rows:
        per.setdefault(r['机场'], {})[r['指标']] = float(r['得分'])
    airports = sorted(per)
    X = np.array([[per[a][i] for i in INDICATORS] for a in airports])
    y = np.array([overall[a] for a in airports])
    return X, y


def fit(X, y):
    D = X[:, :-1] - X[:, [-1]]                      # 用 x_7 做基准,消掉求和约束
    w6, *_ = np.linalg.lstsq(D, y - X[:, -1], rcond=None)
    w = np.append(w6, 1 - w6.sum())

    n, p = D.shape
    resid = y - X @ w
    sigma2 = float(resid @ resid) / (n - p)
    cov = sigma2 * np.linalg.inv(D.T @ D)
    se = np.append(np.sqrt(np.diag(cov)),
                   np.sqrt(np.ones(p) @ cov @ np.ones(p)))   # w_7 = 1 - Σw_1..6
    return w, se, resid, D


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    X, y = load()
    w, se, resid, D = fit(X, y)

    print(f"样本 {len(y)} 家 × {X.shape[1]} 个指标")
    print(f"综合得分标准差 {y.std():.4f}   残差最大 {np.abs(resid).max():.4f}   "
          f"条件数 cond(D)={np.linalg.cond(D):,.0f}\n")

    print("=== 反解出的权重 ===")
    for name, wi, s in zip(INDICATORS, w, se):
        bar = "█" * max(0, round(wi * 60))
        print(f"  {name:<12}{wi:>7.3f} ± {1.96*s:.3f}  {bar}")
    print(f"  {'合计':<12}{w.sum():>7.3f}")
