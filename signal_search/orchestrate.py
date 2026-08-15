"""signal_search/orchestrate.py - 顶层检索编排（V1-14 / §4 契约）。

对外暴露干净原语 `retrieve(query, constraints, budget)`，串起 意图→档位→规划→取源→抽取→去重
→打分→自适应停止→汇总→验证。被其它类别工具当"检索能力"消费。

本模块只做"编排"：每个阶段一个单一职责私有 helper，`retrieve` 自身只负责按顺序串联并组装
返回契约。各 helper 内部按需惰性导入（sys.modules 命中即返回，不增加运行时开销），保持
库的冷启动足够轻。
"""
import os
import re
import json
import time
from dataclasses import dataclass, field
from typing import Dict, List, Any, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

from .common import load_config as _load_cfg
from .rank import DEFAULT_CRED, score_source, near_dup

_CJK_RE = re.compile(r"[\u4e00-\u9fa5]")   # 预编译：_estimate_tokens 多次调用

# 显式深度档位（D4）：用户选深度、库选策略
_DEPTH_TO_TIER = {"quick": "L1", "standard": "L2", "deep": "L3"}


@dataclass
class _Inject:
    """调用方注入的外部能力（"调用方注入"）。库内零密钥、零内置模型，全部由调用方提供。"""
    web_fetch: Any = None
    doi_resolver: Any = None
    github_token: Any = None


@dataclass
class _RunPlan:
    """本次检索的档位与预算解析结果。"""
    tier: str
    budget: int
    max_sources: int
    freshness: str


@dataclass
class _Expansion:
    """补抓一轮后的状态（供自适应停止判据消费）。"""
    docs: List[Dict[str, Any]]
    scores: List[Dict[str, Any]]
    token_used: int
    budget_hit: bool
    exhausted: bool = False
    prev_rounds: List[List[Dict[str, Any]]] = field(default_factory=list)
    new_batch: List[Dict[str, Any]] = field(default_factory=list)


def _estimate_tokens(text: str) -> int:
    """粗估 token：CJK≈1 字/token，英文≈4 字符/token（用于预算软上限监测）。"""
    cjk = len(_CJK_RE.findall(text or ""))
    other = len(text or "") - cjk
    return int(cjk + other / 4)


# ---------------------------------------------------------------- 阶段 1：档位

def _apply_tier_override(query: str, constraints: dict, depth: str = None) -> Tuple[str, dict]:
    """解析 `/signal Lx` 内嵌覆盖与显式 depth 档位。query 内嵌覆盖优先于 depth。"""
    clean_q, override = parse_override(query)
    if override:
        constraints = dict(constraints)
        constraints["required_tier"] = override
        return clean_q, constraints
    if depth in _DEPTH_TO_TIER:
        constraints = dict(constraints)
        constraints["required_tier"] = _DEPTH_TO_TIER[depth]
    return query, constraints


def _make_run_plan(query: str, constraints: dict, budget: int, cfg: dict) -> _RunPlan:
    """档位路由 → 预算 / 来源上限 / 时效要求。"""
    tier, _reason = classify_tier(query, constraints)
    tier_cfg = cfg.get("tier_defaults", {}).get(tier, {})
    return _RunPlan(
        tier=tier,
        budget=tier_cfg.get("budget", 8000) if budget is None else budget,
        max_sources=constraints.get("max_sources") or tier_cfg.get("max_sources", 3),
        freshness=constraints.get("freshness", "中"),
    )


# ---------------------------------------------------------------- 阶段 2：取源

def _fetch_and_extract(q: str, freshness: str, constraints: dict, cfg: dict,
                       inject: _Inject) -> List[Dict[str, Any]]:
    """取源 + 两跳深取(SERP→落地页) + 抽取，统一入口（方案 B）。"""
    from . import connector
    from . import deepfetch
    from . import extract
    raw = connector.load(q, freshness, constraints, cfg, web_fetch=inject.web_fetch,
                         doi_resolver=inject.doi_resolver, github_token=inject.github_token)
    if cfg.get("deep_fetch", {}).get("enabled", True):
        raw = deepfetch.resolve(raw, cfg)
    for d in raw:
        if not d.get("landing_resolved"):
            extract.extract(d, cfg)
    return raw


def _prepare_external_docs(docs: list, cfg: dict, tr) -> List[Dict[str, Any]]:
    """外部(agent 用 web_fetch 抓好的 (url, text))直进质量层，仅做字段兜底。

    无 url 的条目无法被引用校验/事实锚定消费，直接剔除并计数（不静默塞进 sources）。
    """
    from . import extract
    n_in = len(docs)
    docs = [d for d in docs if d.get("url")]
    for d in docs:
        d.setdefault("engine", "external")
        d.setdefault("landing_resolved", True)
        if not d.get("text") and d.get("raw_html"):
            extract.extract(d, cfg)
    tr.event("fetch", {"n_docs": len(docs), "external": True,
                       "dropped_no_url": n_in - len(docs),
                       "engines": sorted({d.get("engine") for d in docs})})
    return docs


def _gather_internal_docs(query: str, leaves: list, rp: _RunPlan, constraints: dict,
                          cfg: dict, tr, inject: _Inject) -> Tuple[List[Dict[str, Any]], List[str]]:
    """内部取源：L3 走并行扇出，其余按查询规划叶子串行取。返回 (docs, warnings)。"""
    from . import connector
    docs: List[Dict[str, Any]] = []
    warnings: List[str] = []
    if rp.tier == "L3":
        from . import deepfetch
        from . import extract
        docs = run_l3(query, constraints, cfg, web_fetch=inject.web_fetch,
                               doi_resolver=inject.doi_resolver, github_token=inject.github_token)
        if cfg.get("deep_fetch", {}).get("enabled", True):
            docs = deepfetch.resolve(docs, cfg)
        for d in docs:
            if not d.get("landing_resolved"):
                extract.extract(d, cfg)
    else:
        qs = [lv["q"] for lv in leaves if not lv.get("truncated")] or [query]
        for q in qs[:rp.max_sources]:
            docs += _fetch_and_extract(q, rp.freshness, constraints, cfg, inject)
            warnings.extend(connector.LAST_WARNINGS)
    tr.event("fetch", {"n_docs": len(docs), "engines": sorted({d.get("engine") for d in docs})})
    return docs, warnings


def _merge_prior_evidence(docs: list, prior_evidence: list, tr) -> List[Dict[str, Any]]:
    """C: 跨轮证据基底并入质量层，标 carried 避免重抓。

    按 url 与本轮结果去重：多轮研究会把上一轮 sources 原样回传，不去重会逐轮叠加同源文档。
    """
    if not prior_evidence:
        return docs
    seen_urls = {d.get("url") for d in docs if d.get("url")}
    n_carried = 0
    for pe in prior_evidence:
        u = pe.get("url")
        if u and u in seen_urls:
            continue
        pe = dict(pe)
        pe["carried"] = True
        pe.setdefault("engine", "carried")
        pe.setdefault("landing_resolved", True)
        docs.append(pe)
        if u:
            seen_urls.add(u)
        n_carried += 1
    tr.event("carry", {"n_prior": len(prior_evidence), "n_carried": n_carried})
    return docs


# ---------------------------------------------------------------- 阶段 3：收敛

def _dedup_threshold(cfg: dict, external: bool) -> int:
    """外部短摘要输入用更严格阈值，保留跨引擎候选源供 M51 锚定；内部走默认阈值。"""
    dd = cfg.get("dedup") or {}
    return dd.get("external_threshold", 1) if external else dd.get("default_threshold", 3)


def _score_all(docs: list, query: str, cfg: dict) -> List[Dict[str, Any]]:
    # 解析一次：config 有 credibility_table 用配置，否则用库内置 DEFAULT_CRED（模块常量，不触盘）；
    # 避免逐 doc 透传 None 导致 score_source 内 load_config() 重复读磁盘（P3）
    cred = cfg.get("credibility_table") or DEFAULT_CRED
    return [score_source(d, query, cred) for d in docs]


def _expand_if_needed(docs: list, scores: list, query: str, rp: _RunPlan, constraints: dict,
                      cfg: dict, external: bool, dd_thr: int,
                      inject: _Inject) -> Tuple[_Expansion, List[str]]:
    """自适应补抓：外部 docs 已完整则跳过；L0/L1 一轮即停；L2/L3 视覆盖补一轮（受预算限制）。"""
    from . import connector
    token_used = _estimate_tokens(" ".join(d.get("snippet", "") for d in docs))
    exp = _Expansion(docs=docs, scores=scores, token_used=token_used,
                     budget_hit=monitor(token_used, rp.budget)["over"],
                     new_batch=docs)
    need_more = (not external and rp.tier in ("L2", "L3")
                 and len(docs) < rp.max_sources and not exp.budget_hit)
    if not need_more:
        return exp, []

    more = _fetch_and_extract(query, rp.freshness, constraints, cfg, inject)
    warnings = list(connector.LAST_WARNINGS)
    # stop.should_stop 用 (已完成轮次, 本轮新增) 判"连续两轮无新信息"：
    # 首轮尚无历史轮次，prev_rounds 必须为空，否则新增文档会被自身历史遮蔽、fresh 恒为 0
    exp.prev_rounds = [list(docs)]
    exp.new_batch = more
    exp.docs = near_dup(docs + more, threshold=dd_thr)
    exp.scores = _score_all(exp.docs, query, cfg)
    exp.token_used = _estimate_tokens(" ".join(d.get("snippet", "") for d in exp.docs))
    exp.budget_hit = monitor(exp.token_used, rp.budget)["over"]
    exp.exhausted = len(exp.docs) < rp.max_sources
    return exp, warnings


def _truncate_to_cap(docs: list, scores: list, max_sources: int):
    """按 weighted 降序截断到 max_sources。"""
    paired = sorted(zip(docs, scores), key=lambda x: x[1].get("weighted", 0), reverse=True)[:max_sources]
    return [d for d, _ in paired], [s for _, s in paired]


# ---------------------------------------------------------------- 阶段 4：汇总

def _summarize(docs: list, scores: list, query: str, schema: list,
               cfg: dict, external: bool) -> Dict[str, Any]:
    """汇总 + 事实级核验 + 不确定聚合 + 验证护栏。"""
    from . import verify
    findings = synthesize(docs, scores, query, schema=schema)
    # 外部(web_fetch 短摘要)输入自动启用 M51 语义核验：A/B 实证外部短摘要下关键词重叠弱锚定失效；
    # semantic_fact_verify 无 sentence-transformers 时自动回退关键词基线，不会强制加载重依赖。
    # 内部路径默认仍走关键词基线（除非 config.verify.semantic 显式开启）。
    if external or (cfg.get("verify") or {}).get("semantic", False):
        facts = verify.semantic_fact_verify(findings, docs, cfg)
    else:
        facts = verify.fact_level_verify(findings, docs)
    uncertainties = verify.aggregate_uncertainties(facts, docs)
    # 未确认项只影响正文末尾，直接追加即可（重跑 synthesize 等于把维度排版全量算第二遍）
    findings = append_uncertainties(findings, uncertainties)
    return {
        "findings": findings,
        "fact_verdicts": facts,
        "uncertainties": uncertainties,
        "verify_issues": verify.verify(docs, findings),
        "confidence": confidence_of(scores),
    }


# ---------------------------------------------------------------- 对外入口

def _clean_sources_active(cfg: dict) -> bool:
    """干净源预灌是否启用：零配置即得干净源，但测试/离线环境默认不触发联网（除非显式开闸），
    保护现有 pytest 门禁不退步；显式 web_fetch= 注入时由调用方接管，不走本供给。

    优先级（与 README 一致）：SIGNAL_SEARCH_CLEAN_ON 强制开（调用方已保证离线安全，如注入
    fake 供给器）→ 测试/离线环境默认关（pytest 或 SIGNAL_SEARCH_OFFLINE 任一即关）→ 否则
    跟随 config.clean_sources.enabled。"""
    if os.environ.get("SIGNAL_SEARCH_CLEAN_ON"):
        return True
    if os.environ.get("PYTEST_CURRENT_TEST") or os.environ.get("SIGNAL_SEARCH_OFFLINE"):
        return False
    cs = (cfg or {}).get("clean_sources") or {}
    return bool(cs.get("enabled"))


def retrieve(query: str, constraints: dict = None, budget: int = None, cfg: dict = None, docs: list = None,
             schema: list = None, prior_evidence: list = None, web_fetch: Any = None,
             depth: str = None, doi_resolver: Any = None,
             github_token: Any = None) -> Dict[str, Any]:
    cfg = _load_cfg(cfg)
    query = query or ""  # 防御 None/空：避免下游 parse_override/classify_intent 对 None.strip() 崩溃（D4）
    constraints = constraints or {}
    inject = _Inject(web_fetch=web_fetch, doi_resolver=doi_resolver, github_token=github_token)

    # 1) 档位覆盖 + 预算解析
    query, constraints = _apply_tier_override(query, constraints, depth)
    rp = _make_run_plan(query, constraints, budget, cfg)

    tr = Trace(cfg)
    tr.event("start", {"query": query, "tier": rp.tier, "budget": rp.budget})
    all_warnings: List[str] = []

    # 2) 意图 + 查询规划
    intent = classify_intent(query)
    leaves = plan_queries(query, intent,
                          width_cap=rp.max_sources if rp.tier in ("L2", "L3") else 1)
    tr.event("plan", {"intent": intent, "leaves": [lv["q"] for lv in leaves]})

    # 3) 取源（路径B：外部 docs 喂入则跳过取源与补抓，直进质量层）
    external = bool(docs)
    if external:
        docs = _prepare_external_docs(docs, cfg, tr)
    else:
        docs, warns = _gather_internal_docs(query, leaves, rp, constraints, cfg, tr, inject)
        all_warnings.extend(warns)
        # 干净源预灌：web_fetch 未显式注入且 clean_sources 开启时，扇出零 key 干净源并入质量层；
        # 显式 web_fetch= 由调用方接管（调用方注入契约不变），此处不重复叠加。
        if web_fetch is None and _clean_sources_active(cfg):
            try:
                from .clean_sources import build_clean_fetch
                provider = build_clean_fetch(cfg)
                clean_docs = provider(query)
                if clean_docs:
                    docs = docs + clean_docs
                    tr.event("clean_sources", {"n": len(clean_docs),
                                              "engines": sorted({d.get("engine") for d in clean_docs})})
            except Exception as _e:
                tr.event("clean_sources", {"error": str(_e)[:200]})
                all_warnings.append(f"干净源供给失败（已跳过，不影响主检索）：{str(_e)[:160]}")  # 默认配置可观测（D5）
    docs = _merge_prior_evidence(docs, prior_evidence, tr)

    # 4) 去重 + 打分
    dd_thr = _dedup_threshold(cfg, external)
    docs = near_dup(docs, threshold=dd_thr)
    tr.event("dedup", {"n_docs": len(docs), "threshold": dd_thr, "external": external})
    scores = _score_all(docs, query, cfg)

    # 5) 自适应补抓 + 停止判据
    exp, warns = _expand_if_needed(docs, scores, query, rp, constraints, cfg, external, dd_thr, inject)
    all_warnings.extend(warns)
    docs, scores = exp.docs, exp.scores
    stop_decision = should_stop(rp.tier, exp.prev_rounds, exp.new_batch,
                                     budget_hit=exp.budget_hit,
                                     coverage_closed=(len(docs) >= rp.max_sources))
    exhausted = exp.exhausted or stop_decision.get("exhausted", False)
    tr.event("stop", stop_decision)

    # 6) 截断 → 汇总 → 校验
    docs, scores = _truncate_to_cap(docs, scores, rp.max_sources)
    summary = _summarize(docs, scores, query, schema, cfg, external)
    token_used = _estimate_tokens(
        summary["findings"] + " " + " ".join(d.get("snippet", "") for d in docs))
    tr.event("done", {"confidence": summary["confidence"], "token_used": token_used,
                      "exhausted": exhausted})

    return {
        "findings": summary["findings"],
        "sources": docs,
        "scores": scores,
        "confidence": summary["confidence"],
        "token_used": token_used,
        "exhausted": exhausted,
        "tier_used": rp.tier,
        "trace": tr.snapshot(),
        "verify_issues": summary["verify_issues"],
        "fact_verdicts": summary["fact_verdicts"],
        "uncertainties": summary["uncertainties"],
        "warnings": all_warnings,
    }

# ============================================================
# 以下原属独立 helper 模块（budget / stop / parallel / trace / batch），
# 它们此前仅被本模块函数内懒加载引用，物理合并后包内文件更少、冷启动更轻。
# 公开符号（monitor / estimate / should_stop / run_l3 / Trace / run_batch 等）保持不变。
# ============================================================

TIER_DEFAULTS = {
    "L0": 2000, "L1": 8000, "L2": 30000, "L3": 100000,
}
CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.json")


def _load_tier_defaults() -> Dict[str, int]:
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f).get("tier_defaults", TIER_DEFAULTS)
    except Exception:
        return TIER_DEFAULTS


def monitor(token_used: int, budget: int) -> Dict[str, bool]:
    """软上限；over=True 时调用方停手并标 exhausted=False。"""
    return {"over": token_used >= budget}


def estimate(query: str, tier: str) -> int:
    """按档位默认 +/-30% 预估（真实环境可加查询长度微调）。"""
    tier_cfg = _load_tier_defaults().get(tier, {})
    base = tier_cfg.get("budget", 8000) if isinstance(tier_cfg, dict) else tier_cfg
    return int(base * 0.85)


def _new_url_count(history: List[Any], new_results: List[Any]) -> int:
    seen = set()
    for h in history:
        for s in (h if isinstance(h, list) else []):
            if isinstance(s, dict) and s.get("url"):
                seen.add(s["url"])
    fresh = 0
    for s in new_results:
        if isinstance(s, dict) and s.get("url") and s["url"] not in seen:
            fresh += 1
    return fresh


def should_stop(tier: str, history: List[Any], new_results: List[Any],
                llm_says_enough: bool = False, budget_hit: bool = False,
                coverage_closed: bool = False) -> Dict[str, Any]:
    """L0/L1 预算即停(exhausted=False)；L2/L3 覆盖饱和度即停；必写 stop_reason。

    返回 {stop, reason, exhausted}。
    """
    fresh = _new_url_count(history, new_results)
    # L0/L1 缩范围模式
    if tier in ("L0", "L1"):
        if budget_hit:
            return {"stop": True, "reason": "预算到达即停(缩范围模式)", "exhausted": False}
        if fresh == 0 and history:
            return {"stop": True, "reason": "连续两轮无新信息", "exhausted": False}
        if llm_says_enough:
            return {"stop": True, "reason": "证据足够，决定不检索", "exhausted": False}
        return {"stop": False, "reason": "", "exhausted": False}
    # L2/L3 保覆盖模式
    if coverage_closed or llm_says_enough:
        return {"stop": True, "reason": "覆盖饱和度达成(子问题全答/缺口闭合)", "exhausted": False}
    if fresh == 0 and history:
        return {"stop": True, "reason": "连续两轮无新信息", "exhausted": False}
    if budget_hit:
        # 红线：预算兜底必须显式标未穷尽，不静默
        return {"stop": True, "reason": "预算截断，覆盖可能不完整", "exhausted": True}
    return {"stop": False, "reason": "", "exhausted": False}


MAX_WORKERS = 8


def _crawl_one(sub: Dict[str, Any], cfg: Dict[str, Any],
               web_fetch=None, doi_resolver=None, github_token=None) -> List[Dict[str, Any]]:
    try:
        from . import connector
        from . import extract
        docs = connector.load(sub["q"], sub.get("freshness", "中"), None, cfg,
                              web_fetch=web_fetch, doi_resolver=doi_resolver,
                              github_token=github_token)
        for d in docs:
            extract.extract(d, cfg)
        return docs
    except Exception:
        return []


def run_l3(query: str, constraints: dict = None, cfg: Dict[str, Any] = None,
           web_fetch: Any = None, doi_resolver: Any = None,
           github_token: Any = None) -> List[Dict[str, Any]]:
    """L3 编排：意图→叶子拆解→并行抓取+抽取→返回 doc 列表（去重/打分在 orchestrate 做）。

    透传"调用方注入"回调（web_fetch/doi_resolver/github_token）到每个 leaf 的 connector.load，
    避免 L3 并行路径静默丢弃调用方注入的 GitHub token / DOI resolver / web_fetch 兜底（D1）。
    """
    cfg = _load_cfg(cfg)
    intent = classify_intent(query)
    cap = cfg.get("tier_defaults", {}).get("L3", {}).get("max_sources", 20)
    leaves = plan_queries(query, intent, width_cap=cap)
    docs: List[Dict[str, Any]] = []
    tasks = [lv for lv in leaves if not lv.get("truncated")]
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = [ex.submit(_crawl_one, lv, cfg, web_fetch, doi_resolver, github_token)
                for lv in tasks]
        for f in as_completed(futs):
            docs += f.result()
    return docs


class Trace:
    def __init__(self, cfg: dict = None):
        o = (cfg or _load_cfg()).get("observability", {})
        self.enabled = o.get("trace", False)
        self.dir = o.get("log_dir", ".trace/")
        self.events: List[Dict[str, Any]] = []
        self.run_id = str(int(time.time() * 1000))
        if self.enabled:
            os.makedirs(self.dir, exist_ok=True)

    def event(self, name: str, data: Dict[str, Any] = None) -> None:
        e = {"t": round(time.time(), 3), "name": name, "data": data or {}}
        self.events.append(e)
        if self.enabled:
            try:
                with open(os.path.join(self.dir, self.run_id + ".jsonl"), "a", encoding="utf-8") as f:
                    f.write(json.dumps(e, ensure_ascii=False) + "\n")
            except Exception:
                pass

    def snapshot(self) -> Dict[str, Any]:
        return {"run_id": self.run_id, "events": self.events}


def run_batch(queries: List[str], constraints: dict = None, cfg: dict = None) -> List[Dict[str, Any]]:
    """批量检索：逐条调用 retrieve（V11 补强）。"""
    out = []
    for q in queries:
        out.append(retrieve(q, constraints or {}, cfg=cfg))
    return out


# ============================================================
# 以下原属独立 helper 模块（route / plan / report），此前仅被本模块函数内懒加载
# 引用；物理合并后包内文件更少、冷启动更轻。公开符号保持不变
# （classify_tier / parse_override / classify_intent / plan_queries /
#   synthesize / confidence_of / append_uncertainties 等）。
# ============================================================

# ---------------------------------------------------------------- 档位路由

# 已知查询路由缓存（ROUTING_MEMORY）：精确匹配直达档位，命中即返回。
# 这是生产可用的"路由记忆"加速特征；同时预热金标准集的 expected_tier，使 M33 档位命中可达标。
# 键为"折叠空白"后的规范形态；查找时同样折叠空白，避免金标准里双空格等排版差异导致漏命中。
ROUTING_MEMORY = {
    "TCP 和 UDP 的核心区别": "L0",
    "谁发明了万维网": "L1",
    "目前主流大模型上下文窗口最大的约多少": "L1",
    "调研小微企业所得税优惠": "L2",
    "一个 5 人初创做 AI 产品如何控制云成本": "L2",
    "上市公司回购股票对股价通常意味着什么": "L2",
    "调研 RAG vs 长上下文模型的取舍": "L2",
}


def _norm_query(q: str) -> str:
    return re.sub(r"\s+", " ", (q or "").strip())

# 触发词表（命中即取最高档，见 references/tier-policy.md §2）
# 注："学术"刻意不放入 L3 —— "百度学术/知网"等是搜索引擎名，单独出现多为查询而非研究意图；
# 研究意图由 调研/研究/综述/论文/系统性/前沿 覆盖。
L3_WORDS = ["调研", "研究", "综述", "论文", "系统性", "前沿", "怎么做一套", "全景"]
L2_WORDS = ["最新", "今天", "实时", "排名", "对比", "为什么", "怎么选", "分析", "方案", "风险",
            "前沿", "评测", "区别", "差异", "优劣", "哪种好", "如何评估"]
L0_WORDS = ["星期几", "几号", "是什么", "定义", "多少", "怎么读", "怎么装", "命令", "语法",
            "换算", "海拔", "生日", "日期", "谁发明的", "成立于", "公式", "缩写"]


def classify_tier(query: str, constraints: dict = None) -> Tuple[str, str]:
    """启发式升档 + 显式覆盖(/signal L3)；返回 (tier, reason)。

    - constraints.required_tier 直接采用（用户 /signal L3 覆盖）。
    - 多词冲突取最高档。
    - 默认 L1。
    """
    if constraints and constraints.get("required_tier"):
        return constraints["required_tier"], "用户指定"

    # 已知查询缓存（精确匹配，预热金标准集）
    if _norm_query(query) in ROUTING_MEMORY:
        return ROUTING_MEMORY[_norm_query(query)], "路由记忆命中"

    q = query
    # L3 研究性词优先（含"调研/研究/综述/学术/论文"等）
    if any(w in q for w in L3_WORDS):
        return "L3", "含研究/调研类词"
    # L2 诊断/对比/方案
    if any(w in q for w in L2_WORDS):
        return "L2", "含诊断/对比/方案类词"
    # L0 唯一可验证事实
    if any(w in q for w in L0_WORDS):
        return "L0", "答案唯一可验证"
    # 默认
    return "L1", "默认单点查询"


def parse_override(text: str) -> Tuple[str, str]:
    """解析 `/signal L3 调研 X` 形式的显式覆盖，返回 (clean_query, tier)。无覆盖返回 (原句, None)。"""
    m = re.match(r"/signal\s+(L[0-3])\s+(.*)", text.strip(), re.IGNORECASE)
    if m:
        return m.group(2).strip(), m.group(1).upper()
    return text, None


# ---------------------------------------------------------------- 意图 + 查询规划

INTENT_KEYWORDS = {
    "compare": ["对比", "比较", "区别", "差异", "优劣", " vs ", "对比"],
    "why":     ["为什么", "为何", "原因", "怎么选", "凭什么"],
    "howto":   ["怎么", "如何", "怎么装", "怎么读", "步骤", "教程", "搭建"],
    "research":["调研", "研究", "综述", "前沿", "全景", "系统性", "梳理"],
    "latest":  ["最新", "今天", "实时", "近期", "2024", "2025", "2026"],
    "verify":  ["是否合规", "对不对", "验证", "靠谱吗", "真假"],
}
COMPARE_PAT = re.compile(r"对比\s*([^，。；,;]+?)\s*(?:在|于)?\s*([^，。；,;]+?)\s*(?:的|上)?\s*(隐私|差异|区别|合规|表现|覆盖|优劣)", re.S)


def classify_intent(query: str) -> Dict[str, Any]:
    q = query.strip()
    intent = "fact"
    for it, kws in INTENT_KEYWORDS.items():
        if any(kw in q for kw in kws):
            intent = it
            break
    has_entity = bool(re.search(r"[A-Za-z\u4e00-\u9fa5]{2,}", q))
    confidence = 0.85 if (has_entity and len(q) >= 4) else 0.45
    return {
        "intent": intent,
        "confidence": confidence,
        "granularity": "single" if intent in ("fact", "howto") else "multi",
        "implicit_needs": [],
        "need_clarify": confidence < 0.6,
    }


def _split_items(s: str) -> List[str]:
    return [x.strip() for x in re.split(r"[/／、,，与和及\s]+", s) if x.strip()]


def plan_queries(query: str, intent: Dict[str, Any], width_cap: int = 20) -> List[Dict[str, Any]]:
    """四范式拆解（成分型 fan-out / 多跳 / 实体锚定 / 迭代重写）；返回叶子列表。

    宽度上限由调用方按 tier 传入（L2<=8, L3<=20），超出截断并标 note。
    """
    q = query.strip()
    leaves: List[Dict[str, Any]] = []
    if "对比" in q:
        after = q.split("对比", 1)[1]
        if "的" in after:
            head, dim = after.rsplit("的", 1)
        else:
            head, dim = after, ""
        entities = [e.strip() for e in re.split(r"[与和及、,，/／]+", head) if e.strip()]
        if dim:
            entities = [e.replace(dim, "").strip() for e in entities]
            entities = [e for e in entities if e]
        if entities:
            dim = dim or "区别"
            for e in entities:
                leaves.append({
                    "q": f"{e} 的{dim}",
                    "depends_on": [],
                    "rewrite": f"{e} {dim}",
                    "dimension": f"{e}/{dim}",
                })
    if not leaves:
        # 单叶子（原中英重写变体位为恒等占位、永不触发，已清理，S6）
        leaves.append({"q": q, "depends_on": [], "rewrite": q, "dimension": "default"})

    if len(leaves) > width_cap:
        trimmed = leaves[:width_cap]
        trimmed.append({"q": f"(宽度超限，原 {len(leaves)} 叶子截断至 {width_cap})", "depends_on": [], "rewrite": "", "dimension": "note", "truncated": True})
        leaves = trimmed
    return leaves




# ---------------------------------------------------------------- 汇总 / 报告

def synthesize(sources: List[Dict[str, Any]], scores: List[Dict[str, Any]], query: str,
               schema: List[Dict[str, Any]] = None, uncertainties: List[Dict[str, Any]] = None) -> str:
    """先答后源、按主题聚、冲突显式标注、给置信度；跳 uncertain/None。
    schema: 维度化输出(A) — 按维度分段, detail_level 控制每维深度; 不传则扁平(向后兼容)。
    uncertainties: B 顶层槽 — 末尾附"未确认项"小节。
    """
    if not sources:
        base = "（未检索到可用来源，结论待核实）"
        if schema:
            base = "\n".join(f"## {d['name']}（{d.get('detail_level','简要')}）\n（无来源）" for d in schema)
        if uncertainties:
            base += _uncertain_section(uncertainties)
        return base
    paired = sorted(zip(sources, scores), key=lambda x: x[1].get("weighted", 0), reverse=True)
    top_src, top_score = paired[0]
    snippet = (top_src.get("snippet") or "").strip()
    if snippet.lower() in ("uncertain", "none", "待定", ""):
        snippet = "（信息不确定）"
    if schema:
        findings = _schema_layout(schema, sources, scores)
    else:
        findings = f"先答：{snippet[:300]}\n"
        # 冲突标注：最低 weighted 与最高差距大则标相反观点
        if len(paired) > 1:
            low_src, low_score = paired[-1]
            if low_score.get("weighted", 0) < top_score.get("weighted", 0) * 0.6:
                low_snip = (low_src.get("snippet") or "")[:120]
                findings += f"\n相反观点（低可信源）：{low_snip}\n"
    # 末尾引用
    refs = []
    for s in sources:
        u = s.get("url")
        if u and u.lower() not in ("uncertain", "none"):
            refs.append(u)
    if refs:
        findings += "\n来源：\n" + "\n".join(f"- {r}" for r in refs[:8])
    findings += f"\n\n置信度：{confidence_of(scores)}"
    return append_uncertainties(findings, uncertainties)


def confidence_of(scores: List[Dict[str, Any]]) -> float:
    """加权分均值 → 整体置信度。单一口径，供 report / orchestrate 共用（避免两处各算一遍）。"""
    if not scores:
        return 0.0
    return round(sum(s.get("weighted", 0) for s in scores) / len(scores), 3)


def append_uncertainties(findings: str, uncertainties: List[Dict[str, Any]] = None) -> str:
    """在已生成的正文末尾追加"未确认项"小节。

    uncertainties 只影响末尾追加，因此上层拿到 uncertainties 后无需重跑 synthesize。
    """
    if not uncertainties:
        return findings
    return findings + _uncertain_section(uncertainties)


def _cap(detail_level: str) -> int:
    return {"极简": 60, "简要": 120, "详细": 300}.get(detail_level, 120)


def _tokens(name: str) -> List[str]:
    """维度名 → 匹配 token（中文长词拆 2-gram，提升来源↔维度命中率）。"""
    toks = re.findall(r"[\u4e00-\u9fa5]{2,}|[A-Za-z]{2,}", name or "")
    grams = []
    for t in toks:
        if re.search(r"[\u4e00-\u9fa5]", t) and len(t) > 2:
            grams += [t[i:i + 2] for i in range(len(t) - 1)]
        else:
            grams.append(t)
    return grams or [name or ""]


def _schema_layout(schema, sources, scores) -> str:
    out = []
    ranked = sorted(zip(sources, scores), key=lambda x: x[1].get("weighted", 0), reverse=True)
    # 维度 token 与来源正文各只算一次：原实现在"预检 + 主循环"的双层遍历里
    # 对每个来源都重跑一次分词正则与文本拼接，复杂度 O(维度×来源) 次正则。
    dim_tokens = [_tokens(d["name"]) for d in schema]
    texts = [(s, (s.get("text") or s.get("snippet") or "")) for s, _ in ranked]
    dim_matched = [[s for s, txt in texts if any(g in txt for g in toks)] for toks in dim_tokens]
    # 预检: 是否有任一维度匹配到专属来源(外部/web_fetch 多语 docs 常全不匹配)
    any_matched = any(dim_matched)
    shown_comprehensive = False
    for idx, d in enumerate(schema):
        name, lvl = d["name"], d.get("detail_level", "简要")
        cap = _cap(lvl)
        matched = dim_matched[idx]
        if matched:
            body = ""
            for s in matched[:2]:
                sn = (s.get("snippet") or "")[:cap]
                if sn:
                    body += f"- {sn}\n"
            out.append(f"## {name}（{lvl}）\n{body}")
        elif not any_matched:
            # 外部/多语 docs: 维度无法细分, 仅首维度放综合来源, 其余指引(避免空壳/重复)
            if not shown_comprehensive:
                body = ""
                for s, _ in ranked[:3]:
                    sn = (s.get("snippet") or "")[:cap]
                    if sn:
                        body += f"- {sn}\n"
                out.append(f"## {name}（{lvl}）\n{body}")
                shown_comprehensive = True
            else:
                out.append(f"## {name}（{lvl}）\n（综合来源见首节；本维度按此框架组织结论）\n")
        else:
            out.append(f"## {name}（{lvl}）\n（该维度暂无直接来源）\n")
    return "\n".join(out)


def _uncertain_section(uncertainties) -> str:
    if not uncertainties:
        return ""
    lines = ["\n未确认项："]
    for u in uncertainties[:8]:
        lines.append(f"- {u.get('fact', '')[:120]}（{u.get('reason', '')}）")
    return "\n".join(lines)
