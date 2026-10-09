"""「池子多久没人维护」这个指标不许在浅克隆上撒谎（2026-10-09）。

## 它从建成起就一直在撒谎

`build_ndx._pool_curation_age` 用 `git log -1 --format=%cs -- valpha150.csv`
算池子距上次人工维护多少天。而 CI 的 `actions/checkout@v4` 默认 `fetch-depth: 1`
→ 仓库里只有一个提交、**没有父提交** → git 把它当成"引入了整棵树"
→ `git log -1 -- 任意路径` 恒等于**那个 tip 提交的日期**。

线上实测（2026-10-09 发现）：
  · origin 的产物：`pool_last_curated: 2026-10-07` / `pool_age_days: 1`
  · 完整克隆算出来：**2026-09-20 / 19 天**
  · 自 2026-10-06 起没有任何提交碰过 `valpha150.csv`

后果：页面上「池子距上次人工维护 N 天」**每天都显示 0~1 天**，
`>60 天` 的红字警告**永远不可能触发** —— 这个指标的全部目的就是让"悄悄老化"
看得见，结果它反过来一直在给人安心。`ffacdea`（2026-09-07）建成以来一直如此。

**与 `fe8af0a` 是同一个失败模式**（浅克隆 + 无父提交 → git 把整棵树当成改动），
换个地方又咬了一次 —— 所以这次钉成测试。

hermatic：真建一个 `--depth=1` 克隆来验行为，不联网（clone 自本地仓库）。
"""
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
sys.path.insert(0, str(ROOT / "scripts"))


def _git(cwd, *args):
    return subprocess.run(["git", *args], cwd=str(cwd),
                          capture_output=True, text=True, timeout=60)


def test_full_clone_reports_the_real_curation_date():
    """反退化：完整克隆下必须照常给出真实维护日（别为了修 bug 把功能也关掉）。"""
    import build_ndx as b
    if _git(REPO, "rev-parse", "--is-shallow-repository").stdout.strip() == "true":
        pytest.skip("当前仓库本身是浅克隆，这条测不了")
    last, age = b._pool_curation_age("2026-10-09")
    assert last is not None and age is not None, "完整克隆下不该留空"
    assert age >= 0


def test_shallow_clone_returns_nothing_rather_than_the_tip_commit_date(tmp_path):
    """命门：浅克隆下必须返回 None —— 宁可页面显示"—"，也绝不报假的"刚维护过"。"""
    dst = tmp_path / "shallow"
    r = _git(tmp_path, "clone", "--depth=1", "--quiet", REPO.as_uri(), str(dst))
    if r.returncode != 0:
        pytest.skip(f"建浅克隆失败（环境限制）: {r.stderr[:200]}")
    assert _git(dst, "rev-parse", "--is-shallow-repository").stdout.strip() == "true"
    # 克隆拿到的是**已提交**的版本；要验的是**工作树里当前这份**代码 → 覆盖进去。
    # （不这么做的话，build_ndx 改了但还没提交时这条测试会报假红。）
    import shutil
    shutil.copy2(ROOT / "scripts" / "build_ndx.py",
                 dst / "market-analysis" / "scripts" / "build_ndx.py")

    # 先证明**裸 git 确实会撒谎** —— 这条是"门为什么存在"的理由
    raw = _git(dst, "log", "-1", "--format=%cs", "--",
               "market-analysis/data/valpha150.csv").stdout.strip()
    tip = _git(dst, "log", "-1", "--format=%cs").stdout.strip()
    assert raw == tip, (
        f"浅克隆下裸 git 不再把 tip 日期当成池子修改日（raw={raw} tip={tip}）—— "
        "机制变了，这道门的依据要重新评估")

    # 再证明我们的函数拒绝了它
    out = subprocess.run(
        [sys.executable, "-c",
         "import sys;sys.path.insert(0,'market-analysis/scripts');"
         "import build_ndx as b;print(repr(b._pool_curation_age('2026-10-09')))"],
        cwd=str(dst), capture_output=True, text=True, timeout=120)
    assert "(None, None)" in out.stdout, (
        f"浅克隆下没有留空 —— 它会把 tip 提交日期当成维护日发布出去。"
        f"stdout={out.stdout[-400:]} stderr={out.stderr[-400:]}")


def test_ci_unshallows_before_building_ndx():
    """CI 侧：跑 build_ndx 之前必须 unshallow，否则指标永远留空、功能等于没了。

    两层缺一不可：代码层拒绝撒谎（上一条），CI 层让它**有真话可说**（这一条）。
    """
    wf = (REPO / ".github" / "workflows" / "refresh-data.yml").read_text(encoding="utf-8")
    i_un = wf.find("fetch --unshallow")
    i_ndx = wf.find("build_ndx.py")
    assert i_un != -1, "CI 没有 unshallow → pool_age 会永远留空"
    assert i_un < i_ndx, "unshallow 必须排在 build_ndx 之前"
