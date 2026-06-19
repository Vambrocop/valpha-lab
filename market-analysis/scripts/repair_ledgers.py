"""repair_ledgers.py — git union 合并后修复 append-only 账本（去重 + 排序 + 重封链）。

背景：.gitattributes 让 paper_ledger / prediction_log 用 merge=union——CI 与本地各 append
今天的行后并存 → 重复键 + hash 链断，verify_output 拒绝发布（已踩坑 3 次）。
本工具按各账本主键去重(keep=last) + 排序 + 重新封链，与各自 load_ledger/load_log 同口径。

用法：**rebase / merge 之后、提交之前**跑一次：
    py market-analysis/scripts/repair_ledgers.py
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from ledger_hash import seal_hash_chain, HASH_COLS

PROC = Path(__file__).parent.parent / "data" / "processed"

# (文件名, 封链字段[须与 paper_trading/track_predictions 的 HASH_FIELDS 一致], 去重主键)
JOBS = [
    ("paper_ledger.csv",
     ["date", "strategy", "action", "holdings", "cash", "equity", "note", "logged_at"],
     ["date", "strategy"]),
    ("prediction_log.csv",
     ["logged_at", "signal_date", "index", "model_version", "prob", "tier", "ret_1d", "ret_5d", "ret_20d"],
     ["signal_date", "index", "model_version"]),
]


def repair_frame(df, hash_fields, keys):
    """纯逻辑：去重(keep=last) + 排序 + 重封链。与 load_ledger/load_log 同口径。

    把原 repair_all 循环体里的核心数据变换抽成无 I/O 的纯函数，便于单测；
    行为与抽取前逐字一致。
    """
    df = (df.reindex(columns=hash_fields + HASH_COLS)
            .drop_duplicates(subset=keys, keep="last")
            .sort_values(keys)
            .reset_index(drop=True))
    return seal_hash_chain(df, hash_fields)


def repair_all():
    for fname, hash_fields, keys in JOBS:
        path = PROC / fname
        if not path.exists():
            continue
        df = pd.read_csv(path)
        before = len(df)
        df = repair_frame(df, hash_fields, keys)
        df.to_csv(path, index=False)
        dropped = before - len(df)
        print(f"  {fname}: {before} -> {len(df)} 行" +
              (f"（去重 {dropped} + 重封链）" if dropped else "（已干净，重封链）"))


if __name__ == "__main__":
    repair_all()
