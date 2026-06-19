"""test_export_radar.py — Valpha 雷达评分（描述性·0-100·反向维度正确）"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from export_stocks import _scale, _radar


def test_scale_forward():
    assert _scale(-40, -40, 120) == 0
    assert _scale(120, -40, 120) == 100
    assert _scale(40, -40, 120) == 50


def test_scale_reverse():
    # lo>hi：原值越大分越低（稳健/独立性/反弹空间用）
    assert _scale(80, 80, 15) == 0
    assert _scale(15, 80, 15) == 100


def test_scale_clip_and_none():
    assert _scale(999, -40, 120) == 100      # 超上界裁剪
    assert _scale(-999, -40, 120) == 0       # 超下界裁剪
    assert _scale(None, 0, 1) is None        # 缺数据透传 None


def test_radar_six_dims_in_range():
    st = {"chg_1y": 50, "dist_ma200": 10, "vol20_ann": 40,
          "ret_vol_1y": 1.0, "r2_nasdaq_1y": 0.5, "range_pctile_52w": 60}
    r = _radar(st)
    assert set(r) == {"动量", "趋势", "稳健", "性价比", "独立性", "反弹空间"}
    assert all(0 <= v <= 100 for v in r.values())


def test_radar_high_vol_means_low_stability():
    low_vol_stock = _radar({"vol20_ann": 18})["稳健"]
    high_vol_stock = _radar({"vol20_ann": 95})["稳健"]
    assert low_vol_stock > high_vol_stock   # 低波动股稳健分应更高


def test_radar_drops_missing_dims():
    # 缺指标的维度不出现（不污染成 None）
    r = _radar({"chg_1y": 30})
    assert "动量" in r
    assert "稳健" not in r
