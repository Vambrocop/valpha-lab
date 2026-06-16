"""
overreaction.py — R3 行为金融:短期反转(过度反应)检验(置换 + 分段,描述非建议)

诚实问题:**极端下跌日之后,次日是否系统性反弹?**(De Bondt-Thaler 过度反应假说的最简形式)
方法:把"今天是否极端下跌日(收益≤历史 q 分位)"当二元标签,看【次日】收益的条件均值差
(反弹组均值 − 其余),置换检验显著性;再分"全样本 vs 现代(2000后)"看是否已被套利。
复用 placebo 的 perm_test / make_dir_diff_stat(已审)。

🔴 红线:测"历史上有没有这种反弹模式、现在还在不在",**绝不是"大跌就抄底"的建议、不预测明天**。
即便历史显著,也受交易成本/滑点/样本影响,不可交易。三态:real(持续)/faded(历史有现代无)/
rejected/inconclusive。SEED 固定可复现。依赖 numpy/pandas。输出 overreaction.json(三处)。
"""
import datetime
import json
import numpy as np
import pandas as pd
from pathlib import Path

from placebo_test import perm_test, make_dir_diff_stat, ALPHA

SCRIPTS  = Path(__file__).parent
RAW_DIR  = SCRIPTS.parent / "data" / "raw"
PROC_DIR = SCRIPTS.parent / "data" / "processed"
WEB_DIR  = SCRIPTS.parent / "web"
DOCS_DIR = SCRIPTS.parent.parent / "docs"
PROC_DIR.mkdir(parents=True, exist_ok=True)

SEED = 20260613
Q = 5.0                  # 极端下跌日 = 日收益 ≤ 第 5 百分位
RECENT_CUT = pd.Timestamp("2000-01-01")


def _sp_returns():
    f = RAW_DIR / "SP500_long.csv"
    if not f.exists():
        return None
    s = pd.read_csv(f, index_col=0, parse_dates=True).iloc[:, 0]
    s = pd.to_numeric(s, errors="coerce").dropna().sort_index()
    return s.pct_change().dropna() if len(s) > 500 else None


def _test_segment(ret, q, rng):
    """一段收益上的反转检验:label=今天极端下跌, value=次日收益, 条件均值差(单边置换)。"""
    nxt = ret.shift(-1)
    df = pd.concat([ret.rename("today"), nxt.rename("next")], axis=1).dropna()
    if len(df) < 500:
        return None
    thr = float(np.percentile(df["today"].values, q))
    labels = (df["today"].values <= thr).astype(int)
    values = df["next"].values
    if labels.sum() < 30:               # 反弹组(label=1)非空;q<50 ⇒ 其余组(label=0)占~95%也非空,满足 dir_diff 前提
        return None
    r = perm_test(values, labels, make_dir_diff_stat(), rng)
    bounce = float(values[labels == 1].mean())
    other = float(values[labels == 0].mean())
    return {"p_value": r["p_value"], "n_down": int(labels.sum()), "n": int(len(df)),
            "bounce_next_pct": round(bounce * 100, 3), "other_next_pct": round(other * 100, 3),
            "diff_pct": round((bounce - other) * 100, 3)}


def compute_overreaction(ret, q=Q):
    if ret is None or len(ret) < 1000:
        return {"status": "insufficient"}
    full = _test_segment(ret, q, np.random.default_rng([SEED, 1]))
    if full is None:
        return {"status": "insufficient"}
    recent = _test_segment(ret[ret.index >= RECENT_CUT], q, np.random.default_rng([SEED, 2]))
    full_sig = full["p_value"] < ALPHA
    rec_sig = recent is not None and recent["p_value"] < ALPHA
    if full_sig and recent is not None and rec_sig:
        verdict, note = "real", "极端下跌次日反弹:全样本+现代均显著(描述性历史规律,非可交易、非预测)"
    elif full_sig and recent is not None and not rec_sig:
        verdict, note = "faded", "历史显著但现代(2000后)已测不到——很可能已被套利/成本吃掉"
    elif full_sig:
        verdict, note = "real_recent_untested", "全样本显著、现代段样本不足未验证"
    else:
        verdict, note = "rejected", "未检出系统性次日反弹"
    return {"status": "ok", "q": q, "full": full, "recent": recent,
            "verdict": verdict, "note": note}


def run_all():
    print("=== R3 短期反转(过度反应)检验(描述非建议)===")
    ret = _sp_returns()
    res = compute_overreaction(ret)
    if res.get("status") != "ok":
        print("⚠ 数据不足,跳过")
        return None
    f, rc = res["full"], res["recent"]
    print(f"  全样本: 大跌次日 {f['bounce_next_pct']}% vs 其余 {f['other_next_pct']}% "
          f"(差 {f['diff_pct']}pp, p={f['p_value']}, n_down={f['n_down']})")
    if rc:
        print(f"  现代(2000后): 差 {rc['diff_pct']}pp, p={rc['p_value']}")
    print(f"  裁决: {res['verdict']} —— {res['note']}")

    out = {
        "generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "method": "极端下跌日(收益≤第5百分位)次日收益条件均值差(单边置换检验,N=1000) + 全样本vs现代(2000后)分段。",
        "caveat": "测【历史上极端下跌日之后次日是否系统性反弹】+ 现代是否还在——**绝不是'大跌抄底'建议、不预测明天**。"
                  "即便历史显著也受交易成本/滑点影响、不可交易;现代消失=很可能被套利。基于 S&P500。",
        "source": "S&P 500 (^GSPC)", "seed": SEED,
        **res,
    }
    payload = json.dumps(out, ensure_ascii=False, indent=2, allow_nan=False)
    for d in (PROC_DIR, WEB_DIR, DOCS_DIR):
        if d.exists():
            (d / "overreaction.json").write_text(payload, encoding="utf-8")
    print("[OK] overreaction.json")
    return out


if __name__ == "__main__":
    run_all()
