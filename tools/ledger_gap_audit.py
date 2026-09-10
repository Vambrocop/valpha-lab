# -*- coding: utf-8 -*-
# 刻意不写 `#!/usr/bin/env python3` shebang:Windows 的 py 启动器会遵循它、转交给 `python3`,
# 而本机 python3 指向 Microsoft Store 占位程序 → 静默退出 49(2026-09-06 踩过)。
"""ledger_gap_audit.py — 扫全部 append-only 账本:**git 历史里出现过的日期,现在不许消失**。

## 为什么需要它

2026-09-10 发现 `autodiscovery_log.csv` 少了两整天:
  · 2026-07-06(104 行)被 bot 提交 `73ffe3c` 删掉(`+0/-104`);
  · 2026-07-11(148 行)被 bot 提交 `8760d43` 删掉(`148/148` —— **删 148 又加 148,净额为零**)。
根因是缓存回灌 + `git add -A`(同 08-27 抹掉用户自选组合、06-22 删掉 Valpha150 四只票),
2026-09-04 `c97b35d` 已修根因。但**已经丢的没人知道**——现有防线全都抓不住:

  · `ci_ledger_guard` 比的是「工作树 vs origin」:坏版本一旦推上 origin,两边都缺,它看不见;
  · 哈希链记了 `n_rows`,但 07-11 那次删 148 加 148 净额不变,单调性查不出;
  · 跨账本交叉验证也不行(composite_log 那天同样没记录)。

**唯一可靠的参照是 git 历史本身**:某个日期只要在任何历史版本里出现过,它就该一直在。

## 为什么是工具而不是单测

全量扫 19 个账本 ≈ 100 秒(每个账本要逐版本 `git show`),放进 pytest 会显著拖慢门禁。
所以:**单测只守 `autodiscovery_log.csv`**(唯一出过事、版本最多的那个,见
`test_autodiscovery_log.py::test_no_silently_lost_day_recorded_in_git_history`),
全量扫做成本工具,怀疑时手动跑。

2026-09-10 首次全量扫结果:**14 个带日期列的账本里只有 autodiscovery 一个受害**(已恢复),
其余全部完好;4 个无日期列的跳过。

用法:$env:PYTHONUTF8='1'; py tools/ledger_gap_audit.py
退出码:发现丢失 → 1;干净 → 0。
"""
import csv, io, subprocess, sys
sys.path.insert(0, "market-analysis/scripts")
sys.stdout.reconfigure(encoding="utf-8")
from ledger_sidecar import SPECS

def dates_of(text, col):
    try:
        return {r[col] for r in csv.DictReader(io.StringIO(text)) if r.get(col)}
    except Exception:
        return set()

total_lost = {}
for fname, _ in SPECS:
    rel = f"market-analysis/data/{fname}"
    cur_txt = subprocess.run(["git", "show", f"HEAD:{rel}"], capture_output=True,
                             text=True, encoding="utf-8").stdout
    if not cur_txt:
        continue
    header = cur_txt.splitlines()[0].split(",")
    col = next((c for c in ("date", "pred_date", "filed_date", "pick_date", "date_utc") if c in header), None)
    if not col:
        print(f"  {fname:44} (无日期列,跳过)")
        continue
    shas = subprocess.run(["git", "log", "--format=%H", "--", rel],
                          capture_output=True, text=True, encoding="utf-8").stdout.split()
    ever = set()
    for sha in shas:
        t = subprocess.run(["git", "show", f"{sha}:{rel}"], capture_output=True,
                           text=True, encoding="utf-8").stdout
        if t:
            ever |= dates_of(t, col)
    now = dates_of(cur_txt, col)
    lost = sorted(ever - now)
    flag = f"❌ 丢 {len(lost)} 天: {lost[:6]}" if lost else "✅"
    print(f"  {fname:44} {len(shas):>3} 版本  {flag}")
    if lost:
        total_lost[fname] = lost
print()
print("受害账本:", f"{len(total_lost)} 个" if total_lost else "—— 全部干净")
if total_lost:
    print()
    print("恢复方法:从历史版本取出那几天的行,**追加到文件末尾**(不是插到中间)——")
    print("防缩水门要求 origin 的身份序列是本地的前缀,插中间会被判违规。")
raise SystemExit(1 if total_lost else 0)
