import json
from pathlib import Path

with open(Path(__file__).parent.parent / "market-analysis" / "web" / "signals.json",
          encoding="utf-8") as f:
    d = json.load(f)
opp = d["next_opportunities"]
print("TOP ENTRY (最佳买入):")
for x in opp["top_entry"]:
    print(f"  {x['date']} {x['dow_cn']} prob={x['prob']} tier={x['tier']} reasons={x['reasons']}")
print()
print("TOP EXIT (最弱/减仓):")
for x in opp["top_exit"]:
    print(f"  {x['date']} {x['dow_cn']} prob={x['prob']} tier={x['tier']} reasons={x['reasons']}")
