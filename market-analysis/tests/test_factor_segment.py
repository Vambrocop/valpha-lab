"""test_factor_segment.py — #5 因子「现代段透镜」三态判定（_segment_lens 纯逻辑）。

合成二值因子 + 二值 fwd_up_20d，控制「全段有边际/现代段是否还在」，断言三态：
  现代已淡(全段显著、现代测不到) / 现代仍有效(两段都显著) / 现代检验力不足(现代触发<30) /
  两段均无显著边际(本就没原始边际)。
block_bootstrap_diff seed=42 固定 → p 值可复现，测试不 flaky。无网络/yfinance。
"""
import numpy as np
import pandas as pd

from factor_pruning import _segment_lens


def _seg_df(specs):
    """specs: 按时间拼接的 [(n_days, fire_mod, r_fire, r_non), ...]。
    fire_mod=每隔几天触发一次(越小越频繁)；r_fire/r_non=触发/非触发日的 up 比例(确定性铺设)。
    返回 df(date 连续日, f 二值因子, fwd_up_20d 二值)；并返回现代段 cutoff(第二段起点)。"""
    rows, day, kf, kn = [], pd.Timestamp("2000-01-01"), 0, 0
    cutoff = None
    for si, (n, fire_mod, r_fire, r_non) in enumerate(specs):
        if si == 1:
            cutoff = day
        for i in range(n):
            fire = (i % fire_mod == 0)
            if fire:
                y = 1 if (kf % 100) < int(round(r_fire * 100)) else 0; kf += 1
            else:
                y = 1 if (kn % 100) < int(round(r_non * 100)) else 0; kn += 1
            rows.append({"date": day, "f": int(fire), "fwd_up_20d": y})
            day += pd.Timedelta(days=1)
    return pd.DataFrame(rows), cutoff


def test_faded_full_sig_recent_gone():
    """全段有强边际、现代段消失 → 现代已淡(疑被套利)。"""
    df, cutoff = _seg_df([(6000, 3, 0.75, 0.45),    # 早段：触发日 75% 涨 vs 45%，强边际
                          (3000, 3, 0.50, 0.50)])   # 现代段：无差别
    seg = _segment_lens(df, "f", assumed=+1, cutoff=cutoff)
    assert seg is not None
    assert seg["status"] == "现代已淡", seg
    assert seg["full_p"] < 0.10 and seg["recent_p"] >= 0.10


def test_alive_both_segments_sig():
    """全段与现代段都有边际 → 现代仍有效。"""
    df, cutoff = _seg_df([(6000, 3, 0.75, 0.45),
                          (3000, 3, 0.75, 0.45)])   # 现代段仍 75% vs 45%
    seg = _segment_lens(df, "f", assumed=+1, cutoff=cutoff)
    assert seg is not None
    assert seg["status"] == "现代仍有效", seg
    assert seg["recent_p"] < 0.10


def test_underpowered_recent_too_few_fires():
    """现代段触发次数 <30 → 现代检验力不足(不下结论)。"""
    df, cutoff = _seg_df([(6000, 3, 0.75, 0.45),    # 早段大量触发(满足整体 sel>=30)
                          (300, 1000, 0.50, 0.50)])  # 现代段 300 天里几乎不触发
    seg = _segment_lens(df, "f", assumed=+1, cutoff=cutoff)
    assert seg is not None
    assert seg["status"] == "现代检验力不足", seg
    assert seg["recent_diff_pp"] is None          # 不足时不报现代差值
    assert seg["recent_n_fires"] < 30


def test_no_edge_both_segments():
    """两段都没有原始边际 → 两段均无显著边际。"""
    df, cutoff = _seg_df([(6000, 3, 0.50, 0.50),
                          (3000, 3, 0.50, 0.50)])
    seg = _segment_lens(df, "f", assumed=+1, cutoff=cutoff)
    assert seg is not None
    assert seg["status"] == "两段均无显著边际", seg


def test_returns_none_when_too_few_total_fires():
    """整体触发 <30 → 透镜不适用，返回 None(交由上游忽略)。"""
    df, cutoff = _seg_df([(400, 1000, 0.75, 0.45),
                          (400, 1000, 0.75, 0.45)])
    seg = _segment_lens(df, "f", assumed=+1, cutoff=cutoff)
    assert seg is None
