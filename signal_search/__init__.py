"""Signal-Search — 答案质量层检索库（检索原语）。

一行定位
--------
    from signal_search import retrieve, research

    retrieve(query, constraints=None, budget=8000, depth="auto", **kwargs)
        -> {findings, sources, scores, confidence, token_used,
            exhausted, tier_used, trace}

    research(query, tier="auto", **kwargs)
        -> 论文 / 调研级编排结果

设计边界（详见 SKILL.md）
------------------------
- 库，不是产品：不绑 LLM、不 spawn agent、无多模态 / 前端。
- 零密钥自持：LLM、抓取、书目源都由调用方注入；库内不持有任何 key。
- 被其它工具当检索原语消费——只返回带打分与置信度的干净结果，不替调用方决策。

`load_config` 读取与包同级的 config.json（引擎参数 + 全部可调默认值单真相源）；
65 个预灌干净源注册表见 `signal_search.clean_sources.CLEAN_SOURCES`。
"""
from .orchestrate import retrieve
from .research import research
from .common import load_config

__version__ = "1.0.0"

__all__ = ["retrieve", "research", "load_config", "__version__"]
