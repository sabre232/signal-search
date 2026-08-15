"""signal_search/rank.py - 相关性/质量排序（原 score + dedup 合并）。

- score：SBA 加权打分 + 可选 rerank(B2) + source_prefs(B8)（§5.9 / §7）。
- dedup：近似去重（M25/M26）。simhash 近似 + URL 精确去重。

两模块原仅被 orchestrate 引用，合并后减少包内文件数、冷启动更轻。
"""
import re
import hashlib
from typing import Dict, Any, List

from .common import load_config

_TOKEN_RE = re.compile(r"[\w\u4e00-\u9fa5]{2,}")   # 预编译：逐 source / 逐 doc 调用，避免反复编译

DEFAULT_CRED = {"gov": 0.95, "media": 0.85, "academic": 0.9, "vendor": 0.7,
               "forum": 0.4, "selfmedia": 0.35, "unknown": 0.5}
DEFAULT_BIAS = {"gov": 0.1, "media": 0.2, "academic": 0.1, "vendor": 0.3,
                "forum": 0.6, "selfmedia": 0.7, "unknown": 0.5}


def _load_cred() -> Dict[str, float]:
    cfg = load_config()
    return cfg.get("credibility_table", DEFAULT_CRED)


def _lexical_overlap(snippet: str, q: str) -> float:
    sw = set(_TOKEN_RE.findall((snippet or "").lower()))
    qw = set(_TOKEN_RE.findall((q or "").lower()))
    if not qw:
        return 0.5
    return len(sw & qw) / len(qw)


def _recency(published: str, freshness: str = None) -> float:
    if not published:
        return 0.5
    return 0.7  # 有日期即给中高；真实实现可按年份衰减


def _authority(source_type: str, credibility_table: Dict[str, float] = None) -> float:
    # 与 SBA 的 credibility 共用同一份权威度数值（统一真相源，消除 _authority 硬编码与 DEFAULT_CRED 分叉，S3）
    tbl = credibility_table or DEFAULT_CRED
    return tbl.get(source_type, 0.5)


def score_source(s: Dict[str, Any], q: str, credibility_table: Dict[str, float] = None) -> Dict[str, Any]:
    cred_tbl = credibility_table or _load_cred()
    st = s.get("source_type", "unknown")
    cred = cred_tbl.get(st, 0.5)
    rel = _lexical_overlap(s.get("snippet", ""), q)
    rec = _recency(s.get("published"))
    auth = _authority(st, cred_tbl)
    bias = DEFAULT_BIAS.get(st, 0.5)
    weighted = 0.35 * cred + 0.30 * rel + 0.15 * rec + 0.15 * auth + 0.05 * (1 - bias)
    return {"url": s.get("url"), "credibility": cred, "relevance": rel,
            "recency": rec, "authority": auth, "bias": bias, "weighted": round(weighted, 4)}


# ---------------------------------------------------------------- 近似去重

BITS = 64
_BLOCKS = 4          # 64-bit 分 4 块，每块 16-bit（鸽巢：hamming<=3 必共享至少一块）
_BLOCK_BITS = BITS // _BLOCKS


def _tokens(text: str):
    return set(_TOKEN_RE.findall(text or ""))


def _simhash(text: str, bits: int = BITS) -> int:
    toks = _tokens(text)
    if not toks:
        return 0
    v = [0] * bits
    for t in toks:
        h = int(hashlib.md5(t.encode("utf-8")).hexdigest(), 16)
        for i in range(bits):
            v[i] += 1 if (h >> i) & 1 else -1
    return sum(1 << i for i in range(bits) if v[i] > 0)


def _hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def _blocks(h: int):
    """把 64-bit simhash 切成 4 个 16-bit 块索引，用于 LSH 分桶。"""
    mask = (1 << _BLOCK_BITS) - 1
    return [(h >> (i * _BLOCK_BITS)) & mask for i in range(_BLOCKS)]


def near_dup(docs: List[Dict[str, Any]], threshold: int = 3) -> List[Dict[str, Any]]:
    """URL 精确去重 + simhash 近似去重（阈值内视为重复）。返回去重后列表（保序）。

    D8 性能：原实现 O(n^2) 两两 hamming 比较；改为分块 LSH —— 每个哈希按 4 个 16-bit 块
    入桶，比较时只与该哈希共享任一桶的全哈希比对（鸽巢保证 hamming<=3 必同桶，零漏检），
    整体降到近似 O(n)，大规模语料下有感。
    """
    out: List[Dict[str, Any]] = []
    seen_urls = set()
    buckets: Dict[tuple, List[int]] = {}     # (block_idx, block_val) -> [full_hash,...]
    for d in docs:
        url = d.get("url")
        if url and url in seen_urls:
            continue
        h = _simhash((d.get("snippet", "") or "") + (d.get("title", "") or ""))
        # 只取与 h 共享任一 16-bit 块的全哈希作为候选，缩小比对范围
        candidates = set()
        for bi, bv in enumerate(_blocks(h)):
            for ch in buckets.get((bi, bv), ()):
                candidates.add(ch)
        if any(_hamming(h, ch) <= threshold for ch in candidates):
            continue
        if url:
            seen_urls.add(url)
        for bi, bv in enumerate(_blocks(h)):
            buckets.setdefault((bi, bv), []).append(h)
        out.append(d)
    return out
