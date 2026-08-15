"""signal_search/search.py - 引擎抓取层（§5.3 / D11）。拼 URL + 调 scrape；不裸发 HTTP。"""
import json
import urllib.parse
from typing import List, Dict, Any

from .common import load_config as _load_config


def _all_engines(cfg: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out = {}
    for grp in ("cn", "global", "academic"):
        for e in cfg["engines"].get(grp, []):
            out[e["id"]] = e
    for dom, lst in cfg["engines"].get("vertical", {}).items():
        for e in lst:
            out[e["id"]] = e
    return out


# 学术源白名单：即便挂在 .gov / 通用域下，也应判为 academic（先专后泛，避免被裸 "gov" 误吞）。
# 匹配针对 URL 的 host（netloc）做精确子串判定，降低路径误命中。
ACADEMIC_HOSTS = (
    "arxiv", "scholar.google.", "cnki", "wanfang", "pubmed",
    "ncbi.nlm.nih.gov", "nlm.nih.gov", "doi.org", "crossref.org",
    "semanticscholar.org", "researchgate.net", "ieee.org", "acm.org",
    "springer.com", "wiley.com", "sciencedirect.com", "nature.com",
    "biorxiv.org", "medrxiv.org", "ssrn.com", "jstor.org",
)


def _host_of(url: str) -> str:
    try:
        return (urllib.parse.urlparse(url).netloc or url).lower()
    except Exception:
        return url.lower()


def _map_type(url: str) -> str:
    host = _host_of(url)
    low = url.lower()
    # 先专：已知学术库（含挂在 .gov 下的 NCBI / NLM / PubMed）按 host 精确白名单优先判 academic
    if any(h in host for h in ACADEMIC_HOSTS):
        return "academic"
    # 泛化 gov / 官媒：学术白名单已先判定，故不会吞掉学术 .gov 站
    if "gov" in low or "people.com" in low or "news.cn" in low:
        return "gov"
    if "weibo" in low or "zhihu" in low or "toutiao" in low or "mp.weixin" in low:
        return "selfmedia"
    if "stackoverflow" in low or "tieba" in low or "forum" in low:
        return "forum"
    return "unknown"


def classify_source_type(url: str) -> str:
    """公开封装：落地页域名 → source_type（供 deepfetch 复算 credibility）。"""
    return _map_type(url)


def fetch(engine_id: str, query: str, freshness: str = "中", cfg: Dict[str, Any] = None) -> List[Dict[str, Any]]:
    """拼引擎 URL 并委托 scrape.scrape 拉取；失败返回 [] 不抛（B5）。"""
    cfg = cfg or _load_config()
    engines = _all_engines(cfg)
    e = engines.get(engine_id)
    if not e:
        return []
    url = e["search_url"].format(q=urllib.parse.quote(query))
    try:
        from .scrape import scrape
        html, meta = scrape(url, {"engine": engine_id, "freshness": freshness, "cfg": cfg})
    except Exception:
        return []
    if html is None:
        return []
    src_type = _map_type(url)
    return [{
        "url": url, "raw_html": html, "title": "",
        "fetched_at": "", "engine": engine_id, "source_type": src_type,
    }]

def _searxng_classify(url: str) -> str:
    try:
        return classify_source_type(url)
    except Exception:
        return "unknown"


def fetch_searxng(query: str, cfg: Dict[str, Any] = None, max_results: int = 8,
                  web_fetch: Any = None) -> List[Dict[str, Any]]:
    """向 SearXNG 实例查询并返回 SERP doc 列表（结构与 fetch 一致）。

    传输层走系统 curl 子进程（与 finance/github 一致，绕过 TLS 指纹封禁）；
    SearXNG 主传输失败时若 web_fetch 注入则兜底抓实例 JSON 页。

    原 searxng_client.py，合并入本模块（同属检索后端 fetch）。
    """
    cfg = cfg or _load_config()
    sx = cfg.get("searxng", {})
    base = (sx.get("url") or "").rstrip("/")
    if not base:
        return []
    url = f"{base}/search?q={urllib.parse.quote(query)}&format=json"
    try:
        from . import scrape as _scrape
        status, body, _ = _scrape._fetch_system_curl(url, _scrape._coherent_headers(), None, 15)
        if status != 200 or not body:
            raise RuntimeError("searxng non-200/empty")
        data = json.loads(body)
    except Exception:
        if web_fetch:
            try:
                html = web_fetch(url)
                if html:
                    return [{
                        "url": url, "title": query, "snippet": str(html)[:200],
                        "raw_html": None, "engine": "SearXNG", "source_type": "searxng-web",
                    }]
            except Exception:
                pass
        return []
    docs: List[Dict[str, Any]] = []
    for item in (data.get("results") or [])[:max_results]:
        link = (item.get("url") or item.get("link") or "").strip()
        if not link.startswith("http"):
            continue
        docs.append({
            "url": link,
            "title": item.get("title", "") or "",
            "snippet": item.get("content") or item.get("snippet") or "",
            "raw_html": None,
            "engine": "SearXNG",
            "source_type": _searxng_classify(link),
        })
    return docs
