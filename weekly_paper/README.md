# weekly_paper

> 自动化的 **AI research weekly**：扫描 frontier lab blog、HuggingFace 周精选 paper、`dair_ai` 周刊，按 7 个研究主题整理出一份周日晚上能 30 分钟读完的 markdown 报告。

姊妹模块 [`weekly_report`](../weekly_report/README.md) 覆盖**新闻 / 访谈 / 产业**内容。两者共享 ingest / storage / LLM 基础设施，但用各自的 prompt 和 data 目录跑独立 pipeline。

## 输出长这样

最近三周（W16/W17/W18）报告均已生成在 `data/reports/`，覆盖 50+ 条精选 / 周，跨 7 个主题，
本周一句话 + 长读建议 + 编辑视角观察。

## 这周跑一份

```bash
cd info_system
export DEEPSEEK_API_KEY=sk-xxx       # 已在 .env

.venv/bin/python -m weekly_paper.run report     # ingest 已跑过；只 filter+synth
# 或一次跑全
.venv/bin/python -m weekly_paper.run ingest && .venv/bin/python -m weekly_paper.run report
```

输出：`weekly_paper/data/reports/<week>-paper.md`，每周 ~10-15 min · ~$0.04-0.05。

## 7 个研究主题

`paths.py` 的 `TOPICS` 常量定义：

| topic_id | 覆盖范围 |
| --- | --- |
| `agent-harness` | Coding agent (Cursor/Claude Code/Devin/Aider/Cline/OpenHands)、agent infra (MCP)、SWE-bench |
| `agent-rl` | RL 训练框架 (veRL/OpenRLHF/NeMo-RL/TRL)、reasoning RL recipe (R1/GRPO/RLVR)、tool-use RL |
| `image-generation` | DiT/SiT/REPA/Flux 系，T2I、图像编辑、可控生成 |
| `video-generation` | Sora/Wan/Veo 系视频扩散、长视频、音视频联合 |
| `vla-embodied` | π0/GR00T/OpenVLA/RDT 等 VLA、人形机器人 policy、操控 |
| `vlm-llm-posttrain` | 多模态 LLM、SFT/DPO/RLHF/RLAIF/Tülu/Nemotron post-training |
| `world-model` | Genie/Cosmos/V-JEPA/GAIA 系、神经物理仿真、Dreamer 风格 RL |
| `noise` | 兜底分类，被丢弃 |

LLM filter 按这 7 + noise 给每条 item 分类（详见 `prompts/filter.md`）。

## 源（v1：9 active）

`sources_loader.py` 把两类源拼起来：

```
   ┌── topics/research-agi/sources.json    (3 aggregator)
   │     ├ hf-papers-weekly        (aggregator) ✓ /papers/week/<id> 周精选页
   │     ├ dair-ai-newsletter      (aggregator) ✓ Substack RSS
   │     └ alphaxiv-trending       (aggregator) ✓ Next.js RSC scrape，7-day trending
   │
   └── topics/{7 topics}/orgs.json    (按 blog_rss URL 去重 → 6 个唯一 lab blog)
        ├ blog-openai                       (cross) ✓ openai.com/news/rss.xml
        ├ blog-google-deepmind              (cross) ✓ deepmind.google/blog/rss.xml
        ├ blog-huggingface-trl              (cross) ✓ huggingface.co/blog/feed.xml
        ├ blog-allen-institute-for-ai-tülu  (cross) ✓ medium.com/feed/ai2-blog
        ├ blog-github-copilot               (agent-harness) ✓
        └ blog-aider-paul-gauthier          (agent-harness) ✓
```

跨多个 topic 的 lab blog（OpenAI、DeepMind、HuggingFace、Allen AI）只 fetch **一次**，topic
字段标 `cross`，由 LLM 在 filter 阶段把每条 item 归到合适的研究主题。

> Anthropic news 已转 Next.js SPA，无 RSS，目前在 7 个 `orgs.json` 里都是 `disabled: true`，
> 等自定义 HTML scraper 上线再启用。

### Aggregator 源

| id | 类型 | 说明 |
| --- | --- | --- |
| `hf-papers-weekly` | `hf-papers` | 抓 `https://huggingface.co/papers/week/<id>`，按 upvotes 取 top 50。**自定义 scraper**（`ingest/hf_papers.py`），解析 SvelteKit SSR 内嵌的 `DailyPapers` JSON。|
| `dair-ai-newsletter` | `newsletter` | Elvis Saravia 的 [NLP Newsletter](https://nlp.elvissaravia.com/feed) Substack RSS，每周覆盖 NLP/LLM/agent paper 摘要。|
| `alphaxiv-trending` | `alphaxiv` | 抓 `https://www.alphaxiv.org/`，按 `visits_count.last_7_days` 降序取 top 30。**自定义 scraper**（`ingest/alphaxiv.py`），解析 Next.js RSC stream 内嵌的 `trendingPapers` JS 字面量；带 `paper_summary.summary`（人/AI 总结）+ topics + 多个 org + visits/votes + github_url。早于本周一的 trending 论文会 clamp 到周一。|

## 添加新源

### A. 添加 lab blog（推荐路径）

直接编辑对应 topic 的 `topics/<X>/orgs.json`：找到对应 org（或新增），把 `blog_rss` 字段填上**直接 RSS URL**（不要 RSSHub）。`sources_loader` 会自动包含进来。

跨多 topic 共享的 blog（如 OpenAI 在 4 个 topic 都有）只需要在任意一个 orgs.json 里有就行——重复定义会在 sources_loader 里按 URL 去重，但记得保持各处 URL 完全一致。

```json
{
  "name": "Cohere",
  "group_id": "POSTTRAIN1",
  "blog_rss": "https://cohere.com/blog/rss.xml",
  "homepage": "https://cohere.com/blog",
  "github_org": "cohere-ai",
  "verified": true
}
```

### B. 添加 aggregator 源（papers/newsletter）

编辑 `topics/research-agi/sources.json`，加一条 source 条目：

```json
{
  "id": "import-ai-substack",
  "name": "Import AI · Jack Clark",
  "group_id": "AGGREGATOR_NEWSLETTER",
  "type": "newsletter",
  "tier": "S",
  "lang": "en",
  "rss_url": "https://importai.substack.com/feed",
  "homepage": "https://jack-clark.net/"
}
```

如果是非 RSS 的特殊源（HTML scrape）：
1. 在 `weekly_paper/ingest/` 加一个适配器（仿 `hf_papers.py`）
2. 在 `run.py::_ingest_one` 加路由：`if s.type == "your-type": return your_ingest(...)`
3. 把 `"your-type"` 加到 `weekly_report/sources.py::VALID_TYPES`

### C. 标 disabled（暂不抓但保留记录）

```json
{ "id": "alphaxiv-trending", "type": "alphaxiv", ..., "disabled": true }
```

ingest 阶段会跳过，并在日志打印 `[ingest] skipping N disabled source(s)`。

## Pipeline 三阶段

```
                 ┌─────────────────────────────────────────────────────┐
                 │ Stage 1: ingest (数十 RSS / Atom + HF scrape)        │
                 │   - filter_in_week() 取本周（ISO Monday-Sunday）     │
                 │   - SeenIndex 跨周去重（hash url，保留 query 参数）  │
                 │ → data/items/<week>.jsonl                           │
                 └─────────────────────────────────────────────────────┘
                                       │
                                       ▼
                 ┌─────────────────────────────────────────────────────┐
                 │ Stage 2: filter (LLM 7-topic classifier + score)    │
                 │   - heuristic 预剔（YouTube shorts、空标题等）        │
                 │   - 每 batch 25 条，LLM 给 {topic, score, oneliner} │
                 │   - kept = (topic != noise) AND (score ≥ threshold)  │
                 │ → data/filtered/<week>.jsonl                        │
                 └─────────────────────────────────────────────────────┘
                                       │
                                       ▼
                 ┌─────────────────────────────────────────────────────┐
                 │ Stage 3: synth (LLM 1 call → 完整 markdown)          │
                 │   - 按 paths.TOPICS 顺序排区块；空 topic 跳过        │
                 │   - 每 topic 一段「本周一句话」+ 3-7 条目             │
                 │   - TL;DR / 长读 / 编辑观察三个跨 topic 区块         │
                 │ → data/reports/<week>-paper.md                      │
                 └─────────────────────────────────────────────────────┘
```

## CLI

```bash
python -m weekly_paper.run ingest           # 抓所有源（除 disabled）
python -m weekly_paper.run ingest --topic research-agi    # 只抓 aggregator
python -m weekly_paper.run ingest --source hf-papers-weekly --week 2026-W18  # debug 单源
python -m weekly_paper.run filter --threshold 0.5         # 调阈值（默认 0.5）
python -m weekly_paper.run synth                          # filtered → markdown
python -m weekly_paper.run report                         # filter+synth 一气呵成
python -m weekly_paper.run status                         # 各源运行健康度
```

## 实测成本（DeepSeek V4 Pro · W16/W17/W18）

| 周 | in-week | kept | filter (calls · tokens · time · $) | synth (tokens · time · $) | **总计** |
| --- | --- | --- | --- | --- | --- |
| 2026-W18 | 74 | 44 (59%) | 3 · 27767/15282 · 7.3min · $0.0254 | 19555/8289 · 4.2min · $0.0157 | **11.5min · $0.0411** |
| 2026-W17 | 79 | 54 (68%) | 4 · 33909/18127 · 9.2min · $0.0305 | 24075/13290 · 5.5min · $0.0220 | **14.7min · $0.0526** |
| 2026-W16 | 68 | 50 (74%) | 3 · 30039/17693 · 9.9min · $0.0285 | 23342/8905 · 4.4min · $0.0179 | **14.3min · $0.0464** |

均值：**~13 min · ~$0.047 / 周**。年成本 ≈ RMB 12 元。

> v4-pro filter 比 v3 chat 慢 ~5×，但 oneliner 明显更具体（benchmark 名字、覆盖范围、
> 模型对比关键数字都能写出来）。想省时间把 `.env` 的 `DEEPSEEK_MODEL_FILTER=deepseek-v4-flash`，
> synth 留 v4-pro 抓质量。

## 待办（v2）

- [x] alphaxiv 7-day trending scraper — 从 Next.js RSC stream 抽 `trendingPapers`，带 visits/votes/topics/github 元信号
- [ ] Anthropic news scraper（Next.js SPA，无 RSS）
- [ ] HF community blog scraper（补 SenseNova-U1 这类只发 huggingface.co/blog/<org> 不进 daily papers 的）
- [ ] arxiv 类目 RSS（cs.LG / cs.CV / cs.RO / cs.CL）作为兜底
- [ ] GitHub `releases.atom` for 关键 repo（DeepSeek、Qwen、Mistral……）
- [ ] HF org papers feed（需 self-hosted RSSHub，公共实例 403）
- [ ] 中文论文/技术 blog 源（机器之心 paper 解读、CSDN 等）
- [ ] image-generation 60 个 scholar 的 Google Scholar feed（公共 RSSHub 不稳）
- [ ] 把 weekly_report / weekly_paper 的共享代码抽到 `core/`（目前 weekly_paper 直接 import weekly_report）
- [ ] DeepSeek API timeout/降级链：v4-pro 偶有 30+ min hang，需在 `weekly_report/llm.py` 加自动 fallback 到 v4-flash
