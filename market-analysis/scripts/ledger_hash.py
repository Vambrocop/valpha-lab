"""Hash-chain helpers for append-only CSV ledgers.

诚实说明这条链能买到什么、买不到什么：
- 已封存的链让"事后对已提交账本的越界改动"可被 verify_hash_chain 检出
  ——前提是验证时没有先重新封存。它是「相对上一次封存的篡改证据」，
  不是不可变历史。
- 流水线每次运行都会重新封存（seal -> ... -> verify），所以同一次运行内
  这道门抓不到篡改：重封会"祝福"当前内容。它的真正价值是独立审计
  （在任何重封之前，对已提交文件单独跑 verify_output）。
  详见 OPTIMIZATION_LOG「verify-before-seal」。
"""
import hashlib
import json

import pandas as pd

HASH_COLS = ["prev_hash", "row_hash"]
GENESIS = "GENESIS"


def _canon(v):
    if pd.isna(v):
        return ""
    return str(v)


def row_hash(row, fields, prev_hash):
    payload = {"prev_hash": prev_hash}
    payload.update({f: _canon(row.get(f, "")) for f in fields})
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def seal_hash_chain(df, fields):
    out = df.copy()
    for col in HASH_COLS:
        if col not in out.columns:
            out[col] = ""
        out[col] = out[col].fillna("").astype("string")
    prev = GENESIS
    for idx, row in out.iterrows():
        h = row_hash(row, fields, prev)
        out.at[idx, "prev_hash"] = prev
        out.at[idx, "row_hash"] = h
        prev = h
    return out


def verify_hash_chain(df, fields):
    if df.empty:
        return []
    missing = [c for c in HASH_COLS if c not in df.columns]
    if missing:
        return [f"missing hash columns: {missing}"]
    errors = []
    prev = GENESIS
    for pos, (_, row) in enumerate(df.iterrows(), start=1):
        if str(row.get("prev_hash", "")) != prev:
            errors.append(f"row {pos}: prev_hash mismatch")
            break
        expected = row_hash(row, fields, prev)
        if str(row.get("row_hash", "")) != expected:
            errors.append(f"row {pos}: row_hash mismatch")
            break
        prev = expected
    return errors
