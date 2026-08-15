import os
import sys

# 确保仓库根目录在 sys.path 上，使 `import signal_search` 在 pytest 下可用
# （pip install -e . 后也可直接 import；此处仅作离线/未安装时的兜底）。
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pytest

# keyed opt-in 源（Tavily/Exa/Perplexity/BraveAPI）契约上默认关、注入 key 才活。
# 测试不可依赖运行环境是否恰好设置了这些 key，否则「default-off」「通用保底集」
# 等不变量会被 ambient key 污染。统一在每次测试前清除，保证用例自洽。
_KEYED_ENV_VARS = (
    "TAVILY_API_KEY",
    "EXA_API_KEY",
    "PERPLEXITY_API_KEY",
    "BRAVE_API_KEY",
)


@pytest.fixture(autouse=True)
def _clear_keyed_env(monkeypatch):
    for _v in _KEYED_ENV_VARS:
        monkeypatch.delenv(_v, raising=False)
    yield
