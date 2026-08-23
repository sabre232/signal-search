> English ｜ [中文](README.md)

# Signal-Search

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.9%2B-blue.svg)](https://www.python.org/)
[![Version](https://img.shields.io/badge/version-1.2.0-green.svg)]()
[![Key: none](https://img.shields.io/badge/key-none-brightgreen.svg)]()

> A lot of people research search. Few care about the answer.

[![Star History Chart](https://api.star-history.com/svg?repos=sabre232/signal-search&type=Date)](https://star-history.com/#sabre232/signal-search&Date)

Signal-Search is an **answer-quality layer**. It does not hand you a list of links to sort through — it returns a clean answer that is weighted-scored, fact-anchored, and token-budget-capped. No ads, citations traceable to real fetched URLs, depth adaptive to the question, and embeddable into other tools at zero cost.

One-line positioning — the retrieval primitive:
`retrieve(query, constraints, budget) → {findings, sources, scores, confidence, token_used, exhausted, tier_used, trace}`.

---

## Why not just another search tool

Most search tools do three things: **return a list of links, stuff ads in by commercial ranking, and leave it to you to judge whether the sources are true.**

Signal-Search swaps the starting point — it first figures out exactly what you want, then decides how deep to search, how much to spend, and which sources to trust. This isn't another engine list; it's a layer of **scheduling intelligence** that dynamically matches *retrieval depth / source selection / token budget* to the current task.

At the end of the day we care about a different thing than other search tools. They count "how many more results did we pull back"; we watch "did the one you asked about actually get answered correctly." So the same search does a few more steps for you: think the question through, then search, search until it's enough, and finally hand you only the conclusions that hold up — each one sourced so you can verify it yourself.

---

## Three differences

**1. An answer-quality layer, not a link list**
- Every conclusion is ranked by **SBA (Source-Weighted Scoring)**; conflicting views coexist instead of being swallowed.
- Every fact is anchored to a **real fetched URL (M51 fact-level anchoring)**, exportable as BibTeX / Markdown / RIS / CSL / NoteExpress citations.
- What's uncertain is said plainly as "to be verified" — no pretending to know.

**2. Adaptive depth, and it knows when to stop**
- **L0 quick-lookup → L3 deep research**, the library auto-selects the tier by question complexity; you can also name the depth in one line.
- **Token budget cap**: before spending another batch of tokens it asks "will this change the conclusion/action?" — if no, it stops.
- **"Deciding not to retrieve" is a first-class ability** — needless retrieval actually degrades quality; this is backed by research (TASR 2025: fixed k=5 retrieval reaches 94.8% of the effect with only 62.6% of the calls).

**3. Lighter, embeddable, zero-key**
- **A library, not a product**: no LLM binding, no agent spawning, no multimodal / frontend — drop it in anywhere.
- **Zero self-held keys**: LLM, fetch, and bibliography sources are all injected by the caller; the library holds no key and spawns no second connection.
- **Consumed by other tools as a retrieval primitive** — ChatGPT, Claude, Perplexity, Kimi, Gemini, and various research / investment-analysis tools use it to cover their retrieval gaps, taking only clean results and making no decisions for them.

---

## vs. well-known agent-search / deep-research tools (web roundup 2026-08)

We benchmarked the industry's recognized, high-reputation agent-search and deep-research tools as comparison targets (data from 2025–2026 public evaluations and vendor disclosures: ai-pedias, aiagentrank, aisotools, GeekPark, Jiemian, Toutiao,稀土掘金, CSDN, etc.). What they're strong at, what they're weak at — one table shows which layer Signal-Search fills.

**Overseas (agent search / deep research)**
- **Perplexity**: the most famous AI search, pioneer of "direct answers with citations"; Pro Search deep research, Focus modes (academic / YouTube / Reddit); free limited + Pro $20/mo. NewsGuard measured ~47% repeating misinformation (2025-08).
- **OpenAI ChatGPT Search / Deep Research**: embedded in ChatGPT, conversational web + inline citations; Deep Research autonomously browses and produces 5–30 min citation-dense reports; Plus $20/mo.
- **Google Gemini / AI Mode / Deep Research**: native Google Search + Gemini; Deep Research long-horizon plan-browse-brief; AI Mode free. Gemini's open-web recommendation share tripled in 2026 (BrightEdge).
- **Microsoft Copilot / Bing**: integrated Bing; Microsoft itself writes "for reference only, do not use for important advice" (TechCrunch 2026-04).
- **Brave Search (Leo)**: independent index, no tracking; Leo assistant with citations; free + Premium $3/mo.
- **Kagi**: paid, ad-free, highly customizable; $5–25/mo.
- **You.com / YouPro**: agentic search, multi-step research + citations / code / image modes; $15/mo.
- **Phind**: developer-focused, code-first answers with citations; free + Pro $20/mo.
- **Felo**: cross-language search, auto mind-maps / slides; $14.99/mo, free tier.
- **Genspark**: synthesizes results into structured "Sparkpage" articles, multi-agent Super Agent; free + Plus $19.99/mo, claims ad-free / no SEO manipulation.
- **Manus**: general autonomous agent, cloud plan-browse-code-execute, credit billing, free + ~$20–200/mo.

**Domestic (Chinese AI search mains)**
- **Metaso (秘塔)**: best Chinese reputation, "ad-free direct"; "think-then-search / search-then-expand" until logic closes, Agentic Search 5–15 tool calls per run, academic coverage PubMed / CAS partitions; free + API pay-per-use.
- **Kimi (月之暗面)**: million-level context, web search + file analysis, deep research / agent / PPT; free.
- **360 Nano AI Search (n.cn)**: ad-free, multi-model collaboration, file parsing, mind-map / PPT; free + ¥19.9/mo and up.
- **Tiangong / Zhipu Qingyan / Doubao / Tencent Yuanbao / Wenxin / Baidu AI Deep Search**, etc.: general AI assistants or search bases covering daily and domestic gov / encyclopedia scenarios (CSDN 2026 domestic 15-roundup).

| What you actually care about | Known agent-search tools (Perplexity / Metaso / ChatGPT / Manus…) | Signal-Search |
|---|---|---|
| Who controls source coverage | Vendor-fixed source set; you can't plug in your own private / academic / internal knowledge base | You feed whatever sources you want — pass your academic lib, internal lib, clean API via `web_fetch=`; **source coverage ceiling = the sum of what you wire in** |
| How deep to search | Tiers fixed by the product (Metaso 3 tiers, Perplexity Deep Research 2–4 min, ChatGPT / Gemini Deep Research 5–30 min), unchangeable by you | **L0–L3 adaptive routing by complexity, or name it in one line**, token budget capped |
| Are sources trustworthy | Uneven citation quality, still hallucinates: NewsGuard ~47% misinformation repeat for Perplexity (2025-08); Relum 35% / Gemini 38% hallucination (2025-12); Columbia Tow Center high source-identification error for generative search | **SBA weighted scoring + M51 fact anchoring to real fetched URLs + mandatory counter-retrieval**; uncertain marked "to be verified" |
| Ads / stance | Google AI Overviews already serve ads (2025+); Microsoft writes "reference only" disclaimer (TechCrunch 2026-04) | **No ads, no commercial-stance ranking**; uncertain marked "to be verified" |
| Embeddable in my tool? | Mostly closed complete products / pay-per-use APIs (Perplexity $20, You.com $15, Kagi $5–25/mo, Metaso API pay-per-use) | **Retrieval-primitive contract, runs zero-key**, consumed directly by other skills; inject LLM / fetch when stronger capability needed |
| Cost controllable? | Subscription / pay-per-use, best-effort retrieval with no budget | **Token budget + early stop**, over-budget flagged, never silently truncated |
| Lighter? | Mostly complete products with their own multimodal / frontend / agents (Manus / Genspark even make PPTs, place calls) | Library not product, focused on the quality layer; heavy lifting delegated to the caller |

**One line on positioning**: they are "fixed sources + fixed product" search products; Signal-Search is a "scheduling intelligence + your own sources" quality layer. As long as you wire a URL + key into `web_fetch` / `docs` — Perplexity's clean API, Tavily, Exa, arXiv, Semantic Scholar, your internal knowledge base — **source coverage ceiling = the sum of what you wire in**; what they can't do — "use your sources, at your depth, inside your own tool" — is exactly our home ground.

> Data sources (public disclosures, 2025–2026): Relum *AI Reliability Report* (2025-12, hallucination rate); NewsGuard (2025-08, live-news misinformation repeat rate); Columbia University Tow Center generative-search provenance test (source-identification error); TechCrunch (2026-04-05, Copilot ToS disclaimer); Google official blog (AI Overviews ads launch); Brave / Kagi / Metaso official (pricing & models). Specific numbers per each source's latest disclosure.

---

### Plug in your own knowledge base (private / internal sources)

Other search products eat the vendor's fixed public web; Signal-Search lets you wire in your **own** knowledge base, company internal docs, even an internal API as a first-class source — through the same quality layer (weighted scoring, fact anchoring, dedup, token budget) as those 65 public sources, not a bolt-on.

You wire it in with one config block, no code:

```json
// config.json → clean_sources.custom_sources
[
  {
    "id": "my_kb",
    "name": "公司内部知识库",
    "url_template": "https://kb.internal/api/search?q={q}",
    "json_items": "results",
    "item_map": {"url": "link", "title": "t", "snippet": "s"},
    "quality": "A",
    "source_type": "internal"
  }
]
```

- `{q}` is auto-encoded into the query; returned JSON is mapped into unified docs via `json_items` (result array path) + `item_map` (field mapping).
- Need auth? Put `{token}` in the template, set `"key_env": "KB_API_KEY"`, value read from env — if no key is set it stays inactive (opt-in), leaking nothing and touching no network.
- Want it to appear only on relevant queries? Add `"topics": ["corp"]`; with nothing set it **fires every time by default** (a source you actively wired in should fire).
- Once wired in, it competes **on equal footing** in SBA scoring with the public sources — if your internal docs are high quality, they naturally rank first. That's how "source coverage ceiling = the sum of what you wire in" actually lands, not a slogan.

---

## Clean sources out of the box (incl. domestic authorities)

On by default (`clean_sources.enabled: true`, zero-key, zero-config). The library pre-loads **65 clean sources**, scored by `source_type` (academic / gov / vendor / unknown) in SBA — not another link list, but already sorted clean material by source weight.

**Three switchable tiers (`clean_sources.default_tier`)**

| Tier | Coverage | Sources | When |
|---|---|---|---|
| `lite` | International engines + general references (Wiki / Wikidata / Internet Archive) | 12 | quick lookup, save bandwidth |
| `standard` (default) | `lite` + academic APIs + authority standards + foreign keyless industry + domestic authorities + privacy/independent engines | 61 | general research, investment, academia |
| `full` | same as `standard` (privacy/independent already merged) | 61 | equal-weighted with `standard`, reserved extension slot |

**Sources in eight categories** (`quality` is registry metadata + `describe_clean_sources()` report only; scoring actually runs on `source_type`)
1. International engines ×9 (Google / Google HK / DuckDuckGo / Yahoo / Startpage / Brave / Ecosia / Qwant / WolframAlpha, B-tier, default on)
2. General references ×3 (Wikipedia / Wikidata / Internet Archive, A-tier)
3. Academic APIs ×7 (OpenAlex / Crossref / Semantic Scholar / PubMed / Europe PMC / bioRxiv / arXiv, A-tier, mostly keyless REST)
4. Authority standards ×8 (W3C / IETF RFC / WHATWG / MDN / Unicode / TC39 / OpenAPI / GitHub, A-tier)
5. Foreign keyless industry ×16 (SEC EDGAR / World Bank / ClinicalTrials / openFDA / CourtListener / DataEuropa / NOAA / USGS / NASA / IMF / OECD / WHO / CDC / ECDC / UK data.gov.uk / RePEc·IDEAS, A-tier)
6. Privacy / independent ×3 (Mojeek / MetaGer / SearxNG, B/A-tier)
7. Domestic authorities ×15 (National Standards Full-text / National Laws & Regulations DB / National Enterprise Credit / Chinese Gov / National Bureau of Statistics / NSFC / CAS / CNKI / Wanfang / NSSD / NSTL / NMPA / ChiCTR / National Health Commission / National S&T Infrastructure, A/B-tier)
8. AI-native search APIs ×4 (Tavily / Exa / Perplexity / Brave Search API, **off by default, activated by env injection**)

**Doesn't conflict with "caller injection": three points**
- **`web_fetch=` still highest priority**: if you pass a fetcher, the library uses it and bypasses all built-in sources — that's the established contract; clean sources only fill in when "you didn't pass one." In theory, as long as you wire a URL + key into `web_fetch` / `docs`, **our source coverage ceiling = the sum of what you wire in**.
- **`keyless_meta` sources give only bibliographic data**: CNKI / Wanfang / NSSD / NSTL are `keyless_meta`, by default returning only metadata / abstract-level data; for full text, inject your institution lib / bibliography source via `web_fetch=`.
- **Keyed AI search APIs leave a door**: Tavily / Exa / Perplexity / Brave are inactive by default (no key, no network); set `TAVILY_API_KEY` etc. in config or env to activate, running through the unified quality layer.

**Robustness**: sources unreachable in a CN sandbox (e.g. occasionally blocked gov sites) are silently skipped, not breaking other sources; tests / offline environments don't trigger network by default (force on with `SIGNAL_SEARCH_CLEAN_ON`, force off with `SIGNAL_SEARCH_OFFLINE`), not breaking existing gates.

> For the source list, categories, `source_type`, `quality`, and per-source reachability snapshot, run `from clean_sources import describe_clean_sources; print(describe_clean_sources())` live (with `scripts/` on the path).

### Source routing: select on demand, no more full fan-out

The more sources, the less you should hit them all every time — that would pour PubMed / IMF / national-legal into one query, wasting network & latency and diluting SBA with irrelevant-source noise. This is the classic "database selection / source routing" problem, with ample empirical research behind this design:
- **RAGRoute (arXiv:2502.19280)**: over-selecting dilutes relevance and introduces noise; a light router should pick only the relevant subset;
- **Learning to Route (arXiv:2510.02388)**: rule-based routing beats static full-connect; blind multi-source actually degrades quality;
- **Agent-Level MoE (agentpatternscatalog / programmer.ie)**: the most naive router is a Python keyword rule — **zero-key, zero-latency, deterministic**.

The library enables source routing by default (`clean_sources.routing`); `build_clean_fetch` runs `select_sources(query, sources, cfg)` before concurrency, **downstream dedup / SBA / M51 unchanged**:
- **General floor**: 9 international engines + 3 reference sources are **always included** (recall floor, avoids missing general info); user-injected keyed sources also always included (respects opt-in intent).
- **Topic expert sources**: CN/EN keyword dictionaries detect intent (academic / dev / finance / macro / medical / legal / gov-stats / climate-space / privacy / domestic-authority), added by descending match strength, capped by `max_sources` (default 16). E.g. "latest deep-learning survey" → only OpenAlex / Crossref / SemanticScholar / PubMed; "best coffee machine" → only general engines, **zero noise sources**.
- **Unrecognized topic**: returns only the floor set by default (general queries no longer hit pro sources by mistake); `fallback_to_tier: true` fills the rest for recall.
- **Never empty-fires**: floor set is always non-empty; `mode: "off"` or `enabled: false` → back to full fan-out old behavior, **zero-diff backward compatible**.
- **LLM router = caller injection** (zero-key default): `build_clean_fetch(..., router_fn=callable)` takes `(query, candidates) -> List[source]`, use-as-is, no LLM without it.

| Config | Default | Meaning |
|---|---|---|
| `routing.enabled` | `true` | master switch |
| `routing.mode` | `select` | `select` on-demand; `off` full fan-out (old) |
| `routing.max_sources` | `16` | single-query concurrent source cap (floor ~12 counted) |
| `routing.include_general_floor` | `true` | always include general engines for recall |
| `routing.fallback_to_tier` | `false` | fill whole tier on unrecognized query |
| `routing.router` | `heuristic` | default heuristic; caller injects LLM router via `router_fn=` |

## Benchmarks say it

- **230 passed** (pytest, incl. source routing / private-source wiring / cache & concurrency unit tests) / **golden-set tier hit 24/24** / **pyflakes zero warnings** (isolated venv re-verify, 2026-08-14).
- Real fetch: `retrieve("TCP 和 UDP 的核心区别")` hits baike.baidu.com's real answer page; M51 first anchors every fact to a real URL, no longer an empty shell.
- Research orchestration layer `research()` cyclomatic complexity 53→12, top-level `retrieve()` 52→below-B; heavy work decomposed into single-responsibility, easy to maintain and test.

---

## Honest limitations

We put the limits out because vagueness is the real risk:
- **Default engines converge to Baidu / Sogou** (lightweight-first); the other 9 international engines (Google / DuckDuckGo etc.) are pre-loaded into clean sources and called on-demand by the router; callers can also pass fetched results via `web_fetch`. Not fewer — lighter.
- **Default fact anchoring is a keyword baseline**; semantic verification needs local `sentence-transformers` (~1GB); auto-degrades if missing, no error.
- **Landing-page fetching is slow under compliance rate-limit** (default ≈14s/request); enabling `cache.enabled` significantly speeds up.
- **SearXNG needs a local Docker instance**; code is wired in, unit tests complete, awaiting your activation.
- **Chinese SERP is noisy**: default engines (Baidu / Sogou) landing pages are mostly SEO aggregators / marketing soft-text, hard to produce paper-grade clean answers. To avoid it, hand the "fetch" step to your own clean sources — pass your fetcher to `retrieve()` / `research()` via `web_fetch=`: it can be a de-noised multi-engine `web_fetch`, academic sources (arXiv / Semantic Scholar), or clean APIs like Tavily / Exa / Perplexity. The library switches to your fetcher, bypassing the default Chinese SERP noise.

---

## Getting started

Signal-Search is a plain source tree (no installable package), so point Python at the repo and import from `scripts/`:

```bash
# one-time runtime deps
pip install trafilatura curl_cffi requests lxml markdownify

# then, from anywhere:
import sys; sys.path.insert(0, "/path/to/signal-search/scripts")
from orchestrate import retrieve
```

A fully runnable 3-line example lives in [`examples/quickstart.py`](examples/quickstart.py). Optional: `sentence-transformers` (~1GB) enables semantic fact verification — missing it just auto-degrades to the keyword baseline, no error.

## Architecture & source layout

Signal-Search is cleanly layered; three "sources of truth" keep distinct responsibilities:
- **`config.json`** (repo root) — the **single source of truth for engine parameters and all tunable defaults** (tier budgets, credibility table, compliance guardrails, enhancement switches), read at runtime by `load_config()`.
- **`scripts/clean_sources.py`'s `CLEAN_SOURCES`** — the registry of **65 pre-loaded clean sources (data, not config)**; zero-key, zero-config gets you paper-grade / authority-grade sources, complementary to config.json's `engines` as "parameters vs data" two mechanisms.
- **`scripts/*.py`** — quality-layer implementation: routing(`route`), planning(`plan`), fetching(`scrape`/`deepfetch`), extraction(`extract`), dedup(`dedup`), scoring(`score`), stop/budget(`stop`/`budget`), reporting(`report`), verification(`verify`), orchestration(`research`/`orchestrate`).
- **`SKILL.md`** — WorkBuddy skill entry (when to use, call contract, tier routing).
- **`references/`** — detailed specs (anti-scraping, intent, tiers, token-saving, golden set).

Design red line: **library not product, zero-key, zero-cost out-of-box, no LLM binding, no new process spawned**. LLM / fetch / bibliography are all injected by the caller.

## Usage

```python
import sys; sys.path.insert(0, "scripts")   # or use examples/quickstart.py as-is

# one-line retrieval
from orchestrate import retrieve
r = retrieve("TCP 和 UDP 的核心区别", {"max_sources": 3}, 6000)
print(r["findings"], r["sources"], r["tier_used"], r["confidence"])

# with depth tier
r = retrieve("RAG 与长上下文怎么取舍", {"max_sources": 8}, 30000, depth="deep")

# external docs straight into the quality layer (agent fetched multi-engine results via web_fetch)
r2 = retrieve("TCP 和 UDP 的核心区别",
          docs=[{"url": "https://example.com/a", "text": "TCP 面向连接、可靠传输…"}])
```

Paper / research-grade orchestration:

```python
from research import research
out = research("TCP 和 UDP 的核心区别及原理", tier="L2")  # L2: 5 dimensions, single retrieve()
print(out["tier"], out["schema"], out["findings"], out["uncertainties"])
# tier="L3" multi-round refinement; agent_fn= injects sub-agent dispatch
```

Return structure:

| Field | Meaning |
|------|---------|
| `findings` | synthesized conclusion (answer first, sources after) |
| `sources` | deduped, SBA-weighted-truncated docs |
| `scores` | per-source SBA scoring detail |
| `confidence` | weighted confidence 0–1 |
| `token_used` | rough token estimate |
| `exhausted` | whether stopped early because budget hit first (silent truncation forbidden) |
| `tier_used` | actual tier L0/L1/L2/L3 |
| `uncertainties` | top-level uncertainties `[{fact, reason}]` |

---

## Consumed by other skills (retrieval primitive)

Signal-Search returns only clean results with scores and confidence, making no decisions for the caller. Consumed as a retrieval primitive by ChatGPT, Claude, Perplexity, Kimi, Gemini, and various investment-research / deep-analysis tools — they're strong in their own domains but weak at retrieval.

**Default LLM behavior = caller's LLM auto-takes-over**: when called inside WorkBuddy, the current LLM is activated by default as `agent_fn` / `tier_classify_fn` / `conflict_check_fn` — no manual injection, no extra config; without an LLM, the library degrades heuristically, runs zero-dependency.

All public parameters and minimal injection examples are in the technical appendix / `examples/`.

---

## Technical appendix

### Module map (`scripts/`)

| Module | Responsibility |
|------|------|
| `route.py` | tier routing + `/signal Lx` override |
| `plan.py` | intent classification + query decomposition |
| `connector.py` | engine selection (default Baidu/Sogou) + failure isolation + fallback |
| `search.py` / `deepfetch.py` | build URL / two-hop source fetch (SERP→landing, single thread-pool reuse) |
| `scrape.py` | anti-scrape fetch: curl_cffi→system curl→requests fallback + backoff + challenge detection + layered robots |
| `extract.py` | trafilatura-first content extraction + honeypot link stripping |
| `dedup.py` | simhash block LSH approximate dedup (O(n²)→O(n)) |
| `score.py` | SBA five-dimension weighted scoring |
| `stop.py` / `budget.py` | pattern-aware stopping / token soft budget |
| `report.py` | answer-first-then-source summary + conflict annotation + confidence |
| `verify.py` | citation check + fact-level verification (M51 keyword baseline + optional semantic) |
| `research.py` | research orchestration (CC 53→12): entry tiering→decompose→clarify/dispatch agent |
| `parallel.py` / `cache.py` / `embed.py` / `trace.py` | L3 parallel / cache / vectorize / observability |

### Default switch policy

Core / guardrail classes default on (routing, scoring, stopping, budget, M51 verification, layered robots, compliance); experimental classes (SearXNG, semantic verify, rerank, dynamic profiling, etc.) default off, flip when needed.

`config.json` hard gates (any `true` violates policy): `cache.enabled` / `rerank.enabled` / `searxng.enabled` / `dynamic_profiling.enabled` / `conflict_typing.enabled` / `entity_resolution.enabled` / `observability.trace` / `result_driven_rewrite.enabled` all default `false`; the only default-on is `compliance.enabled`.

### Research orchestration `research()`

On top of `retrieve()`'s quality layer, provides paper / research-grade orchestration, borrowing mechanisms from deep-research that are useful for answer quality and remapping to this tool's shape (not lifting its 5-command workflow wholesale / no yaml / no built-in popups). See `SKILL.md` and `references/`.

### Compliance guardrails (M55)

Respect robots.txt (layered exemption: SERP, strict for landing pages), PII redaction not stored raw, rate-limit, skip login/paywalls. See `references/anti-scraping.md`.

### Running tests

```bash
pytest tests/ -q
python -m scripts.eval         # golden-set tier hit rate (offline)
```

---

## License

[MIT](LICENSE) © 2026 Signal-Search contributors

Find this useful? ⭐ **Star it** so more people can find it.
