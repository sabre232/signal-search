# 贡献指南

感谢你考虑为 Signal-Search 做贡献。

## 开发环境

```bash
git clone <your-fork>
cd signal-search
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## 跑测试

测试套件默认**离线**（使用 fixtures，不触发真网抓取），可本地复现：

```bash
pytest -q
# 强制离线（CI 同款门禁）
SIGNAL_SEARCH_OFFLINE=1 pytest -q
```

- 新增源 / 行为请补对应 `tests/`；金标准档位命中见 `references/eval-golden-set.md`。
- 代码风格要求 `pyflakes` 零告警（隔离 venv 复验）。

## 配置与源注册表

- 引擎参数 / 全部可调默认值：**`signal_search/config.json`**（单真相源）。
- 65 个预灌干净源注册表：**`signal_search/clean_sources.py`** 的 `CLEAN_SOURCES`（数据，非配置）。
- 两者边界请不要混用：参数走 config，源清单走 clean_sources。

## 提交

- 保持 PR 聚焦、描述清楚「为什么」。
- 涉及默认开关政策的改动，请同步 `SKILL.md` 与 `README.md` 的「默认开关政策」段。
- 本协议为 MIT，提交即默认你以 MIT 授权你的贡献。
