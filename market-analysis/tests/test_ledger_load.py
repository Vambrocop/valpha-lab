"""账本 load 路径回归。

本次 run_all 崩在 load_log 读到 git 合并搅坏的旧/新 schema 混合 CSV。
这里锁住 load 的三个契约：旧 schema(无 hash 列)→迁移、同键去重、load 后封链自洽。
(结构性损坏[列数不一致]仍会在 read_csv 抛 ParserError；那条由 .gitattributes
 merge=union 在源头预防，见 OPTIMIZATION_LOG「账本×git」。)
"""
import pandas as pd

from ledger_hash import seal_hash_chain, verify_hash_chain


def test_load_log_migrates_old_schema(tmp_path, monkeypatch):
    import track_predictions as tp
    old = tmp_path / "prediction_log.csv"
    old.write_text(
        "logged_at,signal_date,index,model_version,prob,tier,ret_1d,ret_5d,ret_20d\n"
        "2026-06-10 09:00,2026-06-09,NASDAQ,1.0,0.62,4,,,\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(tp, "LOG_PATH", old)
    df = tp.load_log()
    assert df.attrs["needs_hash_migration"] is True            # 旧文件无 hash 列
    assert all(c in df.columns for c in tp.HASH_COLS)           # reindex 后列齐全
    sealed = seal_hash_chain(df, tp.HASH_FIELDS)               # 迁移路径自洽
    assert verify_hash_chain(sealed, tp.HASH_FIELDS) == []


def test_load_log_existing_hash_no_migration(tmp_path, monkeypatch):
    import track_predictions as tp
    df0 = pd.DataFrame([{
        "logged_at": "2026-06-10 09:00", "signal_date": "2026-06-09", "index": "NASDAQ",
        "model_version": "1.0", "prob": 0.62, "tier": 4,
        "ret_1d": "", "ret_5d": "", "ret_20d": "",
    }])
    p = tmp_path / "prediction_log.csv"
    seal_hash_chain(df0, tp.HASH_FIELDS).to_csv(p, index=False)
    monkeypatch.setattr(tp, "LOG_PATH", p)
    assert tp.load_log().attrs["needs_hash_migration"] is False  # 已是新 schema


def test_load_ledger_migrates_and_dedups(tmp_path, monkeypatch):
    import paper_trading as pt
    old = tmp_path / "paper_ledger.csv"
    old.write_text(
        "date,strategy,action,holdings,cash,equity,note,logged_at\n"
        "2026-06-10,buyhold,BUY,{},0.0,10000.0,,2026-06-10 09:00\n"
        "2026-06-10,buyhold,BUY,{},0.0,10001.0,,2026-06-10 09:05\n",  # 同键重复
        encoding="utf-8",
    )
    monkeypatch.setattr(pt, "LEDGER", old)
    df = pt.load_ledger()
    assert df.attrs["needs_hash_migration"] is True
    assert verify_hash_chain(df, pt.HASH_FIELDS) == []          # load 内已封链
    assert len(df) == 1                                          # 同键去重
    assert float(df.iloc[0]["equity"]) == 10001.0               # keep=last
