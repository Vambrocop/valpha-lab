import pandas as pd

from ledger_hash import seal_hash_chain, verify_hash_chain


def test_hash_chain_detects_row_tampering():
    fields = ["date", "strategy", "equity"]
    df = pd.DataFrame([
        {"date": "2026-06-10", "strategy": "buyhold", "equity": "10000.0"},
        {"date": "2026-06-11", "strategy": "buyhold", "equity": "10010.0"},
    ])
    sealed = seal_hash_chain(df, fields)
    assert verify_hash_chain(sealed, fields) == []

    tampered = sealed.copy()
    tampered.loc[1, "equity"] = "99999.0"
    assert verify_hash_chain(tampered, fields)
