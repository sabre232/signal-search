"""signal_search/embed.py - 向量化（默认关，V11 补强）。sentence-transformers 优先，缺失降级关键词向量。

注意：sentence-transformers / transformers 未必安装；本模块永不因缺失而崩溃，缺失时返回
降级向量（关键词哈希），由调用方决定是否用于语义去重/rerank / M51 语义核验。默认关，仅开启后启用。

模型默认 paraphrase-multilingual-MiniLM-L12-v2（中文友好，多语语义）；可在 config.embed.model
覆盖（如英文 all-MiniLM-L6-v2）。懒加载，首次调用才下载/实例化。
"""
import re
import hashlib
import math
import threading
from typing import List, Optional

from .common import load_config

_DEFAULT_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"

_TOKEN_RE = re.compile(r"[\w\u4e00-\u9fa5]{2,}")   # 预编译：降级向量逐 text 调用

# 仅在加载期用 find_spec 探测是否安装（不真正 import 重库）；真正 import 留在 _get_model。
# 保留为模块级属性，供 verify.py 与测试 monkeypatch 判定语义后端是否可用。
try:
    import importlib.util as _ilu

    _TRY_ST = _ilu.find_spec("sentence_transformers") is not None
except Exception:  # pragma: no cover - 极端环境下的兜底
    _TRY_ST = False

_model = None
_model_name = None
_model_lock = threading.Lock()   # D7：模型懒加载加锁，避免并发首调重复实例化/竞态


def _load_model_name() -> str:
    try:
        return (load_config().get("embed", {}) or {}).get("model", _DEFAULT_MODEL)
    except Exception:
        return _DEFAULT_MODEL


def _get_model():
    """懒加载 sentence-transformers（首次调用才 import/实例化），缺失即降级。"""
    global _model, _model_name
    if _model is not None:
        return _model
    with _model_lock:                       # 持锁再判一次（double-checked locking）
        if _model is not None:
            return _model
        if not _TRY_ST:
            _model = None
            return None
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore
        except Exception:
            _model = None
            return None
        _model_name = _load_model_name()
        try:
            _model = SentenceTransformer(_model_name)
        except Exception:
            _model = None
        return _model


def embed(texts: List[str]) -> Optional[List[List[float]]]:
    """返回 list[vector]，无可用后端时返回降级关键词向量（仍可用余弦相似度）。"""
    if not texts:
        return None
    m = _get_model()
    if m is not None:
        return m.encode(texts).tolist()
    out = []
    for t in texts:
        toks = set(_TOKEN_RE.findall(t or ""))
        vec = [0.0] * 64
        for tok in toks:
            h = int(hashlib.md5(tok.encode("utf-8")).hexdigest(), 16)
            vec[h % 64] += 1.0
        out.append(vec)
    return out


def similarity(a: List[float], b: List[float]) -> float:
    try:
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(y * y for y in b))
        return dot / (na * nb) if na and nb else 0.0
    except Exception:
        return 0.0
