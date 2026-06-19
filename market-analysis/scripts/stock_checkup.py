"""
stock_checkup.py — 个股诚实体检（块0 脊柱：基础风险画像）

诚实定位：描述一只股票**是什么样**（风险/规律真伪），**绝不预测涨跌、绝不荐股/给买卖点**。
本块只产出基础风险：年化波动、历史最深回撤、对纳指的 β（OLS 斜率）+ 数据可行性探针。
数据不足的票如实标 insufficient，绝不编造。后续块（EVT/依赖度/规律真伪/区间/异动）见 STOCK_CHECKUP_SPEC.md。

复用已缓存的 data/raw/stocks_prices.csv（个股全量日线）+ combined_prices.csv 的 NASDAQ 列（β 基准）；
清单里若有未缓存的票（如 KO 首次），回退 yfinance 直接抓。依赖 numpy/pandas（yfinance 仅缺数据时用）。
输出 stock_checkup.json（PROC + WEB + DOCS 三处，allow_nan=False）。
"""
import datetime
import json
import zlib
import numpy as np
import pandas as pd
from pathlib import Path

from risk_dashboard import evt_tail   # 块1：复用已审的 EVT/GPD 尾部风险
from placebo_test import perm_test, make_ssb_stat, _group_means, MIN_GROUP_N, ALPHA   # 块3：复用 placebo 置换机器
from stats_util import benjamini_hochberg   # 块3：跨全部票×效应统一 FDR 校正
from conformal import nonoverlap_fwd_returns, split_conformal   # 块4：复用已审的 split-conformal 区间
from overreaction import _fwd_distribution   # 块#4个股版：复用 R3 的大跌后前瞻分布

SCRIPTS  = Path(__file__).parent
RAW_DIR  = SCRIPTS.parent / "data" / "raw"
PROC_DIR = SCRIPTS.parent / "data" / "processed"
WEB_DIR  = SCRIPTS.parent / "web"
DOCS_DIR = SCRIPTS.parent.parent / "docs"
PROC_DIR.mkdir(parents=True, exist_ok=True)

# 精选清单（大盘流动龙头 + KO）；与 STOCK_CHECKUP_SPEC.md 一致
TICKER_NAMES = {
    "AAPL": "苹果", "MSFT": "微软", "GOOGL": "谷歌", "AMZN": "亚马逊", "NVDA": "英伟达",
    "META": "Meta", "TSLA": "特斯拉", "AVGO": "博通", "TSM": "台积电", "COST": "好市多",
    "LLY": "礼来", "BRK-B": "伯克希尔", "KO": "可口可乐", "SNDK": "闪迪", "MU": "美光",
    "AMD": "超微", "INTC": "英特尔", "NFLX": "网飞", "HOOD": "罗宾汉",
}
MIN_DAYS = 250          # 基础风险至少需 ~1 年日线，否则判 insufficient
SEED = 20260613         # 固定种子 → 置换检验可复现（已发布统计结论的硬要求）


# ── 纯函数（可单测，不碰网络）──────────────────────────────────────
def annualized_vol(returns, periods=252):
    """日收益序列 → 年化波动率（小数）。"""
    r = np.asarray(returns, float)
    if len(r) < 2:
        return None
    return float(np.std(r, ddof=1) * np.sqrt(periods))


def max_drawdown(prices):
    """价格序列 → 历史最深回撤（峰到谷，返回最负的小数，如 -0.82）。"""
    p = np.asarray(prices, float)
    if len(p) < 2:
        return None
    peak = np.maximum.accumulate(p)
    return float((p / peak - 1.0).min())


def beta(stock_ret, mkt_ret):
    """对齐后的日收益数组 → 对基准的 β（OLS 斜率 = cov/var）。"""
    s = np.asarray(stock_ret, float)
    m = np.asarray(mkt_ret, float)
    if len(s) < 2 or len(m) != len(s):
        return None
    vm = float(np.var(m, ddof=1))
    if vm == 0:
        return None
    return float(np.cov(s, m, ddof=1)[0, 1] / vm)


def compute_evt(px):
    """块1：单票日损失的 EVT/GPD 尾部（ξ + 日 VaR/ES）。复用 risk_dashboard.evt_tail（需 ~1000+ 天）。
    返回紧凑子集；样本不足 → insufficient。只测尾部严重度/稀有度，不预测时点/方向。"""
    px = pd.to_numeric(px, errors="coerce").dropna().sort_index()
    ret = px.pct_change().dropna()
    r = evt_tail(ret)
    if r.get("status") != "ok":
        return {"status": r.get("status", "insufficient")}
    return {"status": "ok", "xi": r["xi"], "tail": r["tail"],
            "extremal_index": r["extremal_index"], "n_exceed": r["n_exceed"],
            "var_es": r["var_es"]}


def market_dependence(stock_ret, mkt_ret):
    """对齐后的日收益数组 → 单因子(市场)依赖度：相关、R²(市场解释的方差占比)、特质风险占比(1−R²)。"""
    s = np.asarray(stock_ret, float)
    m = np.asarray(mkt_ret, float)
    if len(s) < 2 or len(m) != len(s):
        return None
    if np.std(s, ddof=1) == 0 or np.std(m, ddof=1) == 0:
        return None
    corr = float(np.corrcoef(s, m)[0, 1])
    r2 = corr ** 2
    return {"corr": round(corr, 2), "r2_pct": round(r2 * 100, 1),
            "idiosyncratic_pct": round((1.0 - r2) * 100, 1)}


def compute_market_dependence(px, nasdaq):
    """块2：单票对纳指的依赖度——R²=多大比例的波动被大盘解释，特质=自己的部分(1−R²)。描述非预测。"""
    px = pd.to_numeric(px, errors="coerce").dropna().sort_index()
    ret = px.pct_change().dropna()
    nas = pd.to_numeric(nasdaq, errors="coerce").dropna().sort_index().pct_change().dropna()
    common = ret.index.intersection(nas.index)
    if len(common) < 100:
        return {"status": "insufficient"}
    s = ret.reindex(common).to_numpy(float)
    m = nas.reindex(common).to_numpy(float)
    ok = ~np.isnan(s) & ~np.isnan(m)
    md = market_dependence(s[ok], m[ok])
    if md is None:
        return {"status": "insufficient"}
    md["status"] = "ok"
    md["n_obs"] = int(ok.sum())
    return md


def _effect_test(values, labels, k, rng, recent_mask):
    """单效应稳健性三关：全样本 SSB 置换 p + 分半稳健(两半都显著且主导组一致) + 近期持续性(末段~5年仍显著)。
    异象常被套利:历史稳健但近年消失 → faded,非真规律。"""
    full = perm_test(values, labels, make_ssb_stat(k), rng)
    _, cnt = _group_means(values, labels, k)
    half = len(values) // 2

    def _p_dom(v, l):
        r = perm_test(v, l, make_ssb_stat(k), rng)
        g, c = _group_means(v, l, k)
        gm = np.where(c > 0, g, np.nan)
        return r["p_value"], (int(np.nanargmax(gm)) if np.isfinite(gm).any() else -1)

    p1, d1 = _p_dom(values[:half], labels[:half])
    p2, d2 = _p_dom(values[half:], labels[half:])
    stable = bool(p1 < ALPHA and p2 < ALPHA and d1 == d2 and d1 >= 0)   # 两半都显著且主导组一致
    rp = None
    if int(recent_mask.sum()) >= 100:                                  # 近期持续性：末段~5年够样本才测
        rp = round(perm_test(values[recent_mask], labels[recent_mask], make_ssb_stat(k), rng)["p_value"], 4)
    return {"p_value": full["p_value"], "min_group_n": int(cnt[cnt > 0].min()),
            "split_half_p": [round(p1, 4), round(p2, 4)], "split_half_stable": stable,
            "recent_p": rp, "recent_testable": bool(rp is not None),    # 区分"近期没测"与"近期测了没效应"
            "recent_significant": bool(rp is not None and rp < ALPHA)}


def _eff_rng(tk, effect):
    """每个(票×效应)独立确定性种子 → 置换结果与执行顺序无关、加新检验不扰动旧结果(可复现硬要求)。"""
    key = zlib.crc32(f"{tk}|{effect}".encode()) & 0xffffffff
    return np.random.default_rng([SEED, key])


def compute_anomaly(px, nasdaq, win=60):
    """块6：描述性"当前风险状态"——当前 win 日滚动波动落在该票历史哪个分位 + 是否与纳指异常脱钩。
    🔴 红线:异动 = 风险升高、请重审你的仓位风险,【不是交易信号/机会】;被动展示、非择时非预测。
    用分位(自校准:~5%的日子本就在95分位上)而非显著性检验,故不涉多重比较 FDR——
    【此免 FDR 前提=保持被动、per-stock,绝不跨票排名/筛选'谁在异动';若改成扫描器则该前提失效】。
    分位用严格 `<`(当前值不计入自身参照分布,N≥500 时差异~1/N 可忽略,刻意如此勿改成 off-by-one)。"""
    px = pd.to_numeric(px, errors="coerce").dropna().sort_index()
    ret = px.pct_change().dropna()
    if len(ret) < 500:
        return {"status": "insufficient"}
    rv = (ret.rolling(win).std() * np.sqrt(252)).dropna()
    vol_now = float(rv.iloc[-1])
    vol_pct = round(float((rv < vol_now).mean()) * 100, 1)
    res = {"status": "ok", "win": int(win), "asof": str(ret.index[-1].date()),
           "vol_now_pct": round(vol_now * 100, 1), "vol_percentile": vol_pct,
           "high_vol": bool(vol_pct >= 95)}
    nas = pd.to_numeric(nasdaq, errors="coerce").dropna().sort_index().pct_change()
    common = ret.index.intersection(nas.index)
    if len(common) >= 500:
        rc = ret.reindex(common).rolling(win).corr(nas.reindex(common)).dropna()
        if len(rc) >= 100:
            corr_now = float(rc.iloc[-1])
            cp = float((rc < corr_now).mean()) * 100          # 同一原始分位派生显示值+脱钩判定,避免四舍五入边界分歧
            res.update({"corr_now": round(corr_now, 2),
                        "corr_percentile": round(cp, 1), "decoupled": bool(cp <= 5)})
    return res


def compute_patterns(px, tk):
    """块3：单票日历规律真伪——星期几(日频5组)+月份(月频12组) SSB 置换 + 分半稳健。
    FDR 跨【全部票×效应】统一(防数据窥探);单股 in-sample 显著但【分半不稳】→ 判数据窥探(诚实揭穿)。
    每效应独立种子(与顺序无关)。🔴 红线:测规律真伪、不预测方向。预期单股几乎都 rejected/inconclusive。"""
    px = pd.to_numeric(px, errors="coerce").dropna().sort_index()
    ret = px.pct_change().dropna()
    if len(ret) < 500:
        return {"status": "insufficient"}
    cutoff = ret.index.max() - pd.Timedelta(days=365 * 5)             # 近期 = 末 5 年
    tests = []
    td = _effect_test(ret.values, ret.index.dayofweek.values, 5,
                      _eff_rng(tk, "dow"), np.asarray(ret.index >= cutoff))
    td["effect"] = "星期几"
    tests.append(td)
    monthly = (1 + ret).resample("ME").prod(min_count=1).dropna() - 1
    if len(monthly) >= 60:
        tm = _effect_test(monthly.values, (monthly.index.month - 1).values, 12,
                          _eff_rng(tk, "month"), np.asarray(monthly.index >= cutoff))
        tm["effect"] = "月份"
        tests.append(tm)
    return {"status": "ok", "tests": tests}


def _fdr_annotate_patterns(out_tickers):
    """跨【全部票×效应】统一 BH FDR；回填 q 值 + 三态裁决 + 每票总判。返回是否有 FDR 后仍显著者(STOP 信号)。"""
    flat = [(tk, i) for tk, v in out_tickers.items()
            if v.get("patterns", {}).get("status") == "ok"
            for i in range(len(v["patterns"]["tests"]))]
    pvals = [out_tickers[tk]["patterns"]["tests"][i]["p_value"] for tk, i in flat]
    if not pvals:
        return False
    qvals = benjamini_hochberg(pvals)
    any_real = False
    for (tk, i), q in zip(flat, qvals):
        t = out_tickers[tk]["patterns"]["tests"][i]
        t["q_value"] = round(float(q), 4)
        if q < 0.05 and t.get("split_half_stable"):                   # 过 FDR + 分半稳
            if not t.get("recent_testable"):
                t["verdict"] = "hist_robust"                          # 历史稳健,但近期样本不足无法验证(不声称消失)
            elif t.get("recent_significant"):
                t["verdict"] = "real"; any_real = True                # 三关全过=持续真规律(罕见,停下人工审视)
            else:
                t["verdict"] = "faded"                                # 近期【确实测了】仍消失=被套利(诚实揭穿)
        elif q < 0.05:                                                # in-sample 显著但分半就不稳 = 数据窥探
            t["verdict"] = "data_snoop"
        elif t["min_group_n"] < MIN_GROUP_N:
            t["verdict"] = "inconclusive"
        else:
            t["verdict"] = "rejected"
    for tk, v in out_tickers.items():
        p = v.get("patterns")
        if p and p.get("status") == "ok":
            vs = [t["verdict"] for t in p["tests"]]
            p["overall"] = ("has_real" if "real" in vs else
                            "faded" if "faded" in vs else
                            "hist_robust" if "hist_robust" in vs else
                            "data_snoop" if "data_snoop" in vs else
                            "no_pattern" if all(x == "rejected" for x in vs) else
                            "inconclusive")
    return any_real


def compute_dip_distribution(px, q=5):
    """这只票【极端下跌日(收益≤第q百分位)后】次日/5日/20日前瞻收益的【完整分布】(含下行尾部)。
    复用 R3 的 _fwd_distribution。🔴 红线:描述大跌后历史全貌(含灾难路径)、非抄底建议、不预测。"""
    px = pd.to_numeric(px, errors="coerce").dropna().sort_index()
    ret = px.pct_change().dropna()
    if len(ret) < 600:
        return {"status": "insufficient"}
    dist = [d for d in (_fwd_distribution(ret, q, h) for h in (1, 5, 20)) if d]
    return {"status": "ok", "q": q, "distribution": dist} if dist else {"status": "insufficient"}


def compute_conformal(px, horizon=20, level=0.90):
    """块4：单票 N 日收益的 split-conformal 双边区间 + 出样本外实测覆盖(复用 conformal.py)。
    🔴 红线:这是【不确定性区间】,给范围、不给方向、不预测涨跌;区间略偏正只反映历史无条件分布。"""
    px = pd.to_numeric(px, errors="coerce").dropna().sort_index()
    rets = nonoverlap_fwd_returns(px.to_numpy(float), horizon)
    if len(rets) < 50:
        return {"status": "insufficient"}
    band = split_conformal(rets, levels=(level,))[0]
    return {"status": "ok", "horizon": int(horizon), "level": level,
            "lower_pct": band["lower_pct"], "upper_pct": band["upper_pct"],
            "width_pct": round(band["upper_pct"] - band["lower_pct"], 2),
            "empirical_coverage": band["empirical_coverage"], "n_test": band["n_test"],
            "n_windows": int(len(rets))}


def compute_basic_risk(px, nasdaq):
    """单票价格序列 px + 纳指价格序列 nasdaq（皆 pd.Series，索引=日期）→ 基础风险字典。"""
    px = pd.to_numeric(px, errors="coerce").dropna().sort_index()
    if len(px) < MIN_DAYS:
        return {"status": "insufficient", "n_days": int(len(px))}
    ret = px.pct_change().dropna()
    nas_ret = pd.to_numeric(nasdaq, errors="coerce").dropna().sort_index().pct_change().dropna()
    common = ret.index.intersection(nas_ret.index)
    b = None
    if len(common) >= 100:
        s = ret.reindex(common).to_numpy(float)
        m = nas_ret.reindex(common).to_numpy(float)
        ok = ~np.isnan(s) & ~np.isnan(m)
        b = beta(s[ok], m[ok])
    return {
        "status": "ok",
        "n_days": int(len(px)),
        "start": str(px.index[0].date()), "end": str(px.index[-1].date()),
        "ann_vol_pct": round(annualized_vol(ret.to_numpy()) * 100, 1),
        "max_drawdown_pct": round(max_drawdown(px.to_numpy()) * 100, 1),
        "beta_nasdaq": round(b, 2) if b is not None else None,
    }


# ── 取数（缓存优先，缺失回退 yfinance）────────────────────────────────
def _load_cached_stocks():
    f = RAW_DIR / "stocks_prices.csv"
    if f.exists():
        return pd.read_csv(f, index_col=0, parse_dates=True)
    return pd.DataFrame()


def _load_nasdaq():
    f = RAW_DIR / "combined_prices.csv"
    if f.exists():
        df = pd.read_csv(f, index_col=0, parse_dates=True)
        if "NASDAQ" in df.columns:
            return pd.to_numeric(df["NASDAQ"], errors="coerce").dropna()
    f2 = RAW_DIR / "NASDAQ_COMP_long.csv"
    if f2.exists():
        return pd.read_csv(f2, index_col=0, parse_dates=True).iloc[:, 0]
    return None


def _fetch_ticker(ticker):
    try:
        import yfinance as yf
        df = yf.download(ticker, start="2000-01-01",
                         end=(pd.Timestamp.today() + pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
                         auto_adjust=True, progress=False)
        c = df["Close"]
        return (c.iloc[:, 0] if isinstance(c, pd.DataFrame) else c).dropna().sort_index()
    except Exception as e:
        print(f"  ⚠ {ticker} 抓取失败：{e}")
        return None


def run_all():
    print("=== 个股诚实体检（块0：基础风险画像，非荐股非预测）===")
    nasdaq = _load_nasdaq()
    if nasdaq is None:
        print("⚠ 无纳指基准，β 将为空")
        nasdaq = pd.Series(dtype=float)
    cached = _load_cached_stocks()

    out_tickers = {}
    for tk in TICKER_NAMES:
        if tk in cached.columns:
            px = cached[tk]
        else:
            print(f"  {tk} 不在缓存，回退 yfinance…")
            px = _fetch_ticker(tk)
        if px is None or len(pd.to_numeric(px, errors="coerce").dropna()) == 0:
            out_tickers[tk] = {"name": TICKER_NAMES[tk], "status": "unavailable"}
            print(f"  {tk:<6} 数据不可得")
            continue
        risk = compute_basic_risk(px, nasdaq)
        risk["name"] = TICKER_NAMES[tk]
        if risk["status"] == "ok":
            risk["evt"] = compute_evt(px)                       # 块1：EVT 尾部
            risk["market_dep"] = compute_market_dependence(px, nasdaq)   # 块2：市场依赖度
            risk["patterns"] = compute_patterns(px, tk)         # 块3：规律真伪(每效应独立种子;FDR 在后统一)
            risk["conformal"] = compute_conformal(px)           # 块4：保形区间(范围非方向)
            risk["dip_distribution"] = compute_dip_distribution(px)   # 块#4个股版:大跌后完整分布(含灾难路径,非抄底)
            risk["anomaly"] = compute_anomaly(px, nasdaq)        # 块6：当前风险状态(描述性,非信号)
        out_tickers[tk] = risk
        if risk["status"] == "ok":
            ev = risk.get("evt", {})
            evtxt = (f" · EVT ξ={ev['xi']}" if ev.get("status") == "ok" else "")
            print(f"  {tk:<6} 波动 {risk['ann_vol_pct']}% · 最深回撤 {risk['max_drawdown_pct']}% · β={risk['beta_nasdaq']}{evtxt}")
        else:
            print(f"  {tk:<6} {risk['status']}（n={risk.get('n_days')}）")

    pattern_real = _fdr_annotate_patterns(out_tickers)            # 块3：跨【全部票×效应】统一 FDR + 分半稳健门
    cnt_v = lambda x: sum(1 for v in out_tickers.values() if v.get("patterns", {}).get("overall") == x)
    print(f"  规律真伪(三关后)：真规律 {cnt_v('has_real')} / 历史有近年消失faded {cnt_v('faded')} / "
          f"数据窥探 {cnt_v('data_snoop')} / 其余无规律或无定论"
          + ("  ⚠️ 触发块3停下(持续真规律候选需人工审视)" if pattern_real else ""))

    summary = {                                                   # 块5：登记簿一行用的聚合
        "n_tickers": len(out_tickers),
        "n_ok": sum(1 for v in out_tickers.values() if v.get("status") == "ok"),
        "pattern_real": cnt_v("has_real"), "pattern_faded": cnt_v("faded"),
        "pattern_hist_robust": cnt_v("hist_robust"), "pattern_data_snoop": cnt_v("data_snoop"),
    }

    out = {
        "generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "caveat": "这是个股的**风险画像**，描述它历史上是什么样——**不预测涨跌、不荐股、不给买卖点**。"
                  "年化波动=历史日收益波动；最深回撤=历史峰到谷最大跌幅（可能极深，提示风险非机会）；"
                  "β=对纳指的敏感度（>1 比大盘更颠，<1 更稳），是风险特征不是收益承诺。数据不足的票如实标注。",
        "benchmark": "NASDAQ", "min_days": MIN_DAYS,
        "patterns_fdr_real": bool(pattern_real),
        "summary": summary,
        "tickers": out_tickers,
    }
    payload = json.dumps(out, ensure_ascii=False, indent=2, allow_nan=False)
    for d in (PROC_DIR, WEB_DIR, DOCS_DIR):
        if d.exists():
            (d / "stock_checkup.json").write_text(payload, encoding="utf-8")
    print(f"[OK] stock_checkup.json（{len(out_tickers)} 票）")
    return out


if __name__ == "__main__":
    run_all()
