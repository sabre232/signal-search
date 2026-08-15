---
name: Signal-Search
description: 答案质量层搜索/增强检索 skill：搜信息、做调研、对比、查资料、信源比对、事实核查时启用。不做链接列表——返回带加权打分(SBA)、事实级来源锚定(M51)、分层深度(L0–L3)与 token 预算封顶的干净答案；无广告、零 key、可嵌入，被其它 skill 当检索原语调用（由调用方注入 LLM 与抓取能力）。
version: 1.0.0
---

# Signal-Search

一款"搜索 + 增强搜索"工具产品：对外暴露干净检索原语 `retrieve(query, constraints, budget)`，按需求复杂度在 L0–L3 自动路由、动态选源、控 token 预算、对信源自动比对打分、证据足够即自动停止。被其它类别工具当"检索能力"消费——**不是用来编排其它搜索 skill**。

**答案质量层定位**：答案质量 > 链接数；无广告、直接给答案；引用真实可溯（M51 事实级锚定，可导出 BibTeX/Markdown/RIS/CSL/NoteExpress）；分层深度（`depth="quick|standard|deep"`）；更轻——库而非产品，不绑 LLM、不 spawn agent、无多模态/前端，LLM 与抓取由调用方注入。真·子 agent 派发由调用方注入 `agent_fn`（库不 spawn agent）；HITL 大纲确认交互见 `signal_search/research_cli.py`；参考模板见 `examples/agent_dispatch.py`。

## 何时用
用户要搜信息、做调研、对比、查资料，或别的 skill 需要检索时。

## 标准调用契约
`retrieve(query, constraints={language,domain,freshness,max_sources,required_tier,source_prefs}, budget=token软上限)`
→ `{findings, sources[], scores[], confidence, token_used, exhausted, tier_used, trace}`
（详见 `references/` 各规范与 `signal_search/` 实现；`signal_search/config.json` 为参数单真相源，`signal_search/clean_sources.py` 的 `CLEAN_SOURCES` 为预灌 65 源注册表（数据，非配置）。）

## 档位路由 L0–L3
- **L0 速查**（日期/语法/命令/定义，唯一可验证）→ 预算 2k，1 源，禁思维链。
- **L1 单点**（谁/多少/是什么）→ 预算 8k，1–3 源。
- **L2 诊断/方案**（对比/为什么/怎么选/风险）→ 预算 30k，3–8 源，多源对比+验证。
- **L3 研究**（调研/前沿/学术）→ 预算 100k，≤20 源，planner→并行 crawler→publisher。
- 默认 **L1**；用户可 `/signal L3 调研 X`、`/signal L2 对比 A B` 显式覆盖。详细规则见 `references/tier-policy.md`。

## 意图与查询规划
先判意图（`fact/compare/howto/why/research/latest/verify`），`confidence<0.6` 向用户澄清（最多 1 轮）。再按四范式拆解：成分型 fan-out 并行 / 多跳串行 / 实体锚定 / 迭代重写。宽度上限 L2≤8、L3≤20。方法论见 `references/intent-decomposition.md`。

## 信源打分原则（SBA）
每源五维（credibility/relevance/recency/authority/bias），综合 `weighted=0.35·cred+0.30·rel+0.15·rec+0.15·auth+0.05·(1−bias)`。**按 weighted 加权合成，不按数量投票**；冲突：高 weighted 优先，低 weighted 显式标"存在相反观点"。内置可信度表见 config.json。

## 自适应停止原则
- L0/L1（缩范围）：预算即停，标 `exhausted=False`；1–2 源一致即停。
- L2/L3（保覆盖）：覆盖饱和度即停（子问题全答/引用收敛/单源饱和/缺口闭合）；预算仅兜底，先到未饱和须标 `exhausted=True` 且不静默标完整。
- "决定不检索"是一等能力。每次停止必写 `trace.stop_reason`。详见 `references/tier-policy.md` §4。

## token 预算原则
软上限 + 早停；到顶停并标注 `exhausted`。省 token 七法（prompt 裁剪/上下文剪枝/预检索过滤/工具输出压缩/prompt caching/输出长度控制/模型路由）见 `references/token-optimization.md`。每多花一批 token 前问"会改变结论/动作吗"，答否即停。

## 验证护栏
- 只引 `sources` 中**实际抓取**的 URL；未抓取标"待核实"。
- **事实级核验（M51）**：findings 拆原子事实 → 逐条与 source 片段做蕴含判定 → TRUE/FALSE/UNCERTAIN；UNCERTAIN 显式标"待核实"，不计入已支持，faithfulness 按原子事实计。
- L2/L3 强制**反面检索**（`criticism/limitations/失败/无效`）。
- 结论依赖代码必须实际执行验证（"读过即跑"）。
- 合规护栏（默认开）：尊重 robots.txt、PII 脱敏不落库原文、限速 ~1req/14s、登录墙/付费墙源跳过。见 `references/anti-scraping.md` §6。

## 被其它类别工具调用（辅助补齐检索短板）
作为检索原语被 ChatGPT、Claude、Perplexity、Kimi、Gemini 等 AI 助手，以及各类投研、调研、深度分析工具消费——它们各自在自身领域强、但做检索差。Signal-Search **只返回带打分与置信度的干净结果，不替调用方决策**。

**接入 LLM 的默认行为 = 调用方 LLM 自动接管**：当调用方（上层 agent / 调用本 skill 的 LLM）需要接入 LLM 时，**默认激活的就是该调用方 LLM** 来充当 `agent_fn` / `tier_classify_fn` / `conflict_check_fn`——哪个 LLM 调用就用哪个，无需用户注入、无需额外配置。M51 语义冲突检测同理：`conflict_check_fn` 由调用方把其 LLM 包成回调注入（参考实现见 `examples/conflict_llm.py` 的 `make_llm_conflict(llm_fn)` 适配器），**库内不持有任何 LLM key、不 spawn 第二条连接**。学术源 DOI 回填同理：`doi_resolver` 由调用方注入其书目源（S2/Crossref/自有库），**库内不内置任何书目源、不读环境变量**。未接 LLM 时库内启发式降级（内部按维度 `retrieve()` + 规则分档 + M51 零检测），零依赖可跑。

## 渐进式披露
`signal_search/config.json` 激活时读（参数单真相源）；`references/*.md` 与 `signal_search/*.py` 按需读（反爬/意图/档位/省 token/金标准集等详版）。预灌源注册表见 `signal_search/clean_sources.py`。
