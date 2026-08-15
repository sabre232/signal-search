"""signal_search/verify.py - 验证护栏 VERITAS + 事实级核验(M51)（§5.13 / §5.23）。"""
import re
from typing import List, Dict, Any, Optional, Tuple

URL_RE = re.compile(r"https?://[^\s)\"'\uff08\uff09]+")
KW_RE = re.compile(r"[\d]{2,}|[A-Za-z\u4e00-\u9fa5]{2,}")


def _kw(text: str) -> set:
    """抽取关键实体/数字词集（锚定判据的最小单位）。"""
    return set(KW_RE.findall(text or ""))


def _source_ctx(sources: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """每个来源只做一次正文取值与分词，供所有事实复用（避免 fact×source 重复正则扫描）。"""
    ctx = []
    for s in sources or []:
        text = (s.get("text") or s.get("snippet") or "")
        if not text:
            continue
        ctx.append({"url": s.get("url"), "text": text, "kw": _kw(text),
                    "vec": None, "vec_done": False})
    return ctx


def _claim_text(findings: str) -> str:
    """去掉非论断区块(来源/置信度/未确认项)与 synthesize 生成的元数据行(维度标题/占位),
    仅校验答案论断, 避免把引用列表/维度标题当事实核验。"""
    txt = findings or ""
    for marker in ("来源：", "未确认项：", "置信度："):
        idx = txt.find(marker)
        if idx != -1:
            txt = txt[:idx]
    # 剥离 synthesize 生成的元数据行: markdown 标题(## 维度名) 与 占位行
    _META = re.compile(
        r"^\s*#{1,6}\s.*$"
        r"|^（该维度暂无直接来源）$"
        r"|^（无来源）$"
        r"|^（信息不确定）$"
        r"|^（未检索到可用来源，结论待核实）$"
        r"|^（综合来源见首节；本维度按此框架组织结论）$",
        re.M)
    txt = _META.sub("", txt)
    return txt


def verify(sources: List[Dict[str, Any]], findings: str) -> List[Dict[str, Any]]:
    """引文真实：findings 中每个 URL 必须 ∈ sources；未抓取的一律标待核实/剔除。"""
    issues = []
    src_urls = {s.get("url") for s in sources if s.get("url")}
    cited = set(URL_RE.findall(findings or ""))
    for u in cited:
        if u not in src_urls:
            issues.append({"type": "citation_not_fetched", "url": u, "action": "标待核实/剔除"})
    return issues


def fact_level_verify(findings: str, sources: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """拆原子事实 → 逐条锚定到具体来源 → verdict(TRUE/UNCERTAIN)。

    简化蕴含判定：事实关键实体/数字与每个 source 正文（text 优先、snippet 兜底）做词重叠，
    取重叠最高且 ≥1 的来源 URL 作为锚点（M51 真实锚定，不再是 source=None 空壳）；
    无命中=UNCERTAIN（不轻判 FALSE，留待人工/强模型）。UNCERTAIN 不计入已支持（M51）。
    """
    sents = re.split(r"[。！？;；\n]", _claim_text(findings))
    facts = [s.strip() for s in sents if len(s.strip()) > 4]
    src_ctx = _source_ctx(sources)      # 来源分词预计算一次，热路径不再 fact×source 重复扫描
    results = []
    for f in facts:
        fkw = _kw(f)
        if not fkw:
            results.append({"fact": f[:160], "verdict": "UNCERTAIN", "source": None, "reason": "no_overlap_source"})
            continue
        best_url, best_score = None, 0
        for sc in src_ctx:
            ov = len(fkw & sc["kw"])
            if ov > best_score:
                best_score = ov
                best_url = sc["url"]
        if best_score >= 1:
            results.append({"fact": f[:160], "verdict": "TRUE", "source": best_url, "reason": "source_overlap"})
        else:
            results.append({"fact": f[:160], "verdict": "UNCERTAIN", "source": None, "reason": "weak_anchor"})
    return results


def _semantic_backend_available() -> bool:
    """语义后端（sentence-transformers）是否可用；不可用时调用方回退关键词基线。"""
    try:
        from .embed import _TRY_ST  # noqa: F401
        return _TRY_ST
    except Exception:
        return False


def _split_facts(findings: str) -> List[str]:
    """论断文本拆原子事实：去元数据后按句切分，过滤过短片段。"""
    sents = re.split(r"[。！？;；\n]", _claim_text(findings))
    return [s.strip() for s in sents if len(s.strip()) > 4]


def _embed_one(text: str, embed_fn) -> Optional[List[float]]:
    """惰性向量化单段文本；失败返回 None（不抛，交由上层降级）。"""
    try:
        _v = embed_fn([text])
        return _v[0] if _v else None
    except Exception:
        return None


def _score_fact(f: str, fkw: set, src_ctx: List[Dict[str, Any]], threshold: float,
               embed_fn, sim_fn) -> Tuple[str, Optional[str], float, str]:
    """单条事实 × 多来源：关键词预筛 + 语义相似终判。

    返回 (verdict, source, score, reason)。事实向量仅惰性计算一次；来源向量逐源惰性计算并
    缓存于 src_ctx（facts×sources 的向量化降为 facts+sources）。相似度 ≥ 阈值 → TRUE 锚定来源 URL，
    否则 UNCERTAIN（不轻判 FALSE）。
    """
    best_url, best_sim = None, 0.0
    fvec = None
    for sc in src_ctx:
        if not (fkw & sc["kw"]):   # 关键词预筛：无交集跳过语义计算
            continue
        if fvec is None:
            fvec = _embed_one(f, embed_fn)
        if fvec is None:
            break                  # 事实侧向量化失败 → 本事实无法语义判定
        if not sc["vec_done"]:
            sc["vec_done"] = True
            sc["vec"] = _embed_one(sc["text"], embed_fn)
        if sc["vec"] is None:
            continue
        try:
            sim = sim_fn(fvec, sc["vec"])
        except Exception:
            sim = 0.0
        if sim > best_sim:
            best_sim = sim
            best_url = sc["url"]
    if best_sim >= threshold and best_url:
        return "TRUE", best_url, round(best_sim, 3), "source_overlap"
    return "UNCERTAIN", None, round(best_sim, 3), "weak_anchor"


def semantic_fact_verify(findings: str, sources: List[Dict[str, Any]], cfg: Dict[str, Any] = None,
                        threshold: float = None) -> List[Dict[str, Any]]:
    """M51 语义核验（增强版）：关键词预筛 → Bi-Encoder 语义相似终判（中文友好）。

    每条原子事实先与每个 source 做关键词重叠预筛（廉价、省算力）；预筛命中者再经
    embed.embed 向量化 + embed.similarity 余弦相似度终判。相似度 ≥ 阈值 → TRUE 并锚定该来源
    URL；否则 UNCERTAIN（不轻判 FALSE）。无 sentence-transformers 时 embed 降级为关键词向量，
    语义路径退化为弱语义，此时建议回退 fact_level_verify（由调用方按 config 决定）。

    gating：由 config.verify.semantic 控制是否调用本函数；本函数本身不依赖重依赖即可运行
    （缺失时自动回退 fact_level_verify），故可安全置于热路径之外。
    """
    # 无可用语义后端 → 回退关键词基线，避免假"语义"
    if not _semantic_backend_available():
        return fact_level_verify(findings, sources)

    cfg = cfg or {}
    if threshold is None:
        threshold = (cfg.get("verify") or {}).get("semantic_threshold", 0.55)

    facts = _split_facts(findings)
    # 来源正文的分词与向量各只算一次（原实现对每个事实重复向量化同一来源，
    # 向量化次数从 facts×sources 降为 facts+sources；Bi-Encoder 逐句独立编码，等价）
    src_ctx = _source_ctx(sources)
    from .embed import embed, similarity  # 调用时取最新（含 monkeypatch 覆盖）
    results = []
    for f in facts:
        fkw = _kw(f)
        if not fkw:
            results.append({"fact": f[:160], "verdict": "UNCERTAIN", "source": None, "score": 0.0, "reason": "no_overlap_source"})
            continue
        verdict, source, score, reason = _score_fact(f, fkw, src_ctx, threshold, embed, similarity)
        results.append({"fact": f[:160], "verdict": verdict, "source": source, "score": score, "reason": reason})
    return results


def aggregate_uncertainties(verdicts: List[Dict[str, Any]], docs: List[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """聚合 UNCERTAIN 事实为顶层 uncertainties 列表(B)。
    reason: no_overlap_source(无来源命中) / weak_anchor(弱锚定) / cross_source_conflict(跨源冲突)。
    """
    _NEG = re.compile(r"(不|无|非|没有|相反|并非|未|否)")
    by_fact = {}
    for v in verdicts:
        if v.get("verdict") == "UNCERTAIN":
            by_fact[v.get("fact", "")] = v.get("reason", "weak_anchor")
    # 跨源冲突: 同一事实被不同来源以相反极性支撑
    conflict_facts = set()
    if docs:
        url_snip = {d.get("url"): (d.get("snippet") or d.get("text") or "") for d in docs}
        pos, neg = {}, {}
        for v in verdicts:
            if v.get("verdict") == "TRUE" and v.get("source"):
                sn = url_snip.get(v["source"], "")
                (neg if _NEG.search(sn) else pos).setdefault(v.get("fact", ""), []).append(v["source"])
        conflict_facts = set(pos) & set(neg)
    out = []
    seen = set()
    for f, reason in by_fact.items():
        r = "cross_source_conflict" if f in conflict_facts else reason
        out.append({"fact": f[:160], "source": None, "reason": r})
        seen.add(f)
    # 跨源冲突但事实本身被 TRUE 支撑(仍须提示矛盾)
    for f in conflict_facts:
        if f in seen:
            continue
        out.append({"fact": f[:160], "source": None, "reason": "cross_source_conflict"})
    return out
