"""提交门禁的 CI 同构守门(2026-09-06,事故驱动)。

## 为什么需要这个文件

2026-09-04 我写的一条守门测试把数据刷新干红了两天。它在 CI 的浅克隆下误判
(单个无父提交的 commit 被当成根提交,`git show --name-only` 列出整个仓库 556 个文件)。
**而当时的提交门禁完全没拦住** —— 因为它只 `git archive` 索引树到临时目录,
那里**连 .git 都没有**,读 git 历史的测试走的是完全另一条分支,一路放行。

实测对比(同一份坏代码):
  · 旧门禁(无 .git)  → 10 passed, 2 skipped → **放行**
  · 新门禁(复刻形状) → 1 failed            → **拦截**

所以门禁必须同时满足两件事,少一件这类 bug 就漏过去:
  ① **内容** = 即将提交的**索引树**(不是 HEAD)—— 否则测的是上一个提交,门禁形同虚设;
  ② **git 形状** = 单提交、无父提交、HEAD 作者是 github-actions[bot]
     —— 这正是 CI(`actions/checkout@v4` 默认 `--depth=1`)在 schedule 跑上的样子。

本文件只读源码文本断言这两条不被改掉,不真跑门禁(跑一次要几十秒,不适合放进单测)。
"""
import re
from pathlib import Path

GATE = Path(__file__).resolve().parents[2] / "tools" / "pre_commit_gate.py"


def _src():
    return GATE.read_text(encoding="utf-8")


def test_gate_tests_the_staged_tree_not_head():
    """必须归档**索引树**(git write-tree → git archive),不能改成克隆 HEAD。

    换成 `git clone` 看着更像 CI,但那测的是**上一个提交**,而 pre-commit 门禁的全部意义
    就是测「即将提交的内容」。这条防的是"为了同构把内容测错了"。
    """
    s = _src()
    assert "write-tree" in s and '"archive"' in s, \
        "门禁不再归档索引树 —— 它可能测成了 HEAD,那样即将提交的坏代码根本进不了检查"


def test_gate_builds_a_shallow_like_repo_with_git_dir():
    """临时目录必须**有 .git**,且是单提交(init + 一次 commit)。

    没有 .git 的话,任何读 git 历史的测试在门禁里的行为都与 CI 不同 —— 09-04 事故的直接原因。
    """
    s = _src()
    assert "_make_shallow_like_repo" in s, "复刻 CI 形状的步骤不见了"
    assert '"init"' in s and '"commit"' in s, "临时仓库不再 init/commit,.git 形状没了"
    assert "_clean_checkout_pytest" in s and "_make_shallow_like_repo(tmp)" in s, \
        "干净检出没有调用形状复刻 —— 建了也没用上"


def test_gate_head_author_is_the_ci_bot():
    """HEAD 作者必须是 github-actions[bot]。

    那条 bug **只在 HEAD 作者是 bot 时**触发(测试按 --author=github-actions 筛)。
    我手动跑 CI 时 HEAD 都是自己的提交,恰好绕开 → 假绿。门禁要复刻的是**最坏情况**。
    """
    s = _src()
    assert "github-actions[bot]" in s, "门禁没把 HEAD 作者设成 CI bot,复刻不出触发条件"
    assert re.search(r"user\.name=", s) and re.search(r"user\.email=", s), \
        "身份没通过 -c user.name/user.email 显式指定(会依赖机器的全局配置)"


def test_gate_does_not_depend_on_local_git_config():
    """临时仓库的提交不能被本机全局配置搞挂(签名/hooks),否则门禁在别人机器上直接崩。"""
    s = _src()
    assert "commit.gpgsign=false" in s, "没关签名 —— 全局开了 GPG 签名的机器上门禁会挂/卡住"
    assert "--no-verify" in s or "core.hooksPath" in s, \
        "没隔离 hooks —— 临时仓库的提交可能触发别的钩子"


def test_gate_stays_fail_open_on_infra_errors():
    """基础设施出错必须**放行**并留言,不能把人的提交卡死。

    门禁的失败模式要软:07-28 防缩水门就是因为"以阻断方式失败"把全站停更四天。
    """
    s = _src()
    assert "降级" in s and "已放行" in s, "fail-open 的降级/放行路径不见了"
    assert s.count("allow()") >= 3, "放行分支变少了,门禁可能变成硬阻断"
