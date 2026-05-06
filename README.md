# info_system · 个人 AI 信息系统

一套面向 **AGI / 科技产业 / 前沿研究** 的自动化情报系统，把每周散落在 Substack /
YouTube / 播客 / 中文公众号 / Google Scholar / arxiv 的更新，整合成几份**可在碎片
时间阅读**的周报。

系统由三个互补子模块构成：

| 子模块 | 解决什么问题 | 适合谁 |
|---|---|---|
| **`weekly_report/`** | 新闻 / 访谈 / 产业内容 → 双轨周报（**tech** / **industry**） | 周一早会前想用 10 分钟扫完一周科技动态的人 |
| **`weekly_paper/`** ⭐ | Frontier lab blog / HF papers / dair_ai newsletter → 按 7 个研究主题分区的周报 | 想跟前沿 paper、模型技术报告、研究 newsletter 但没时间逐条扫的研究者 |
| `generate_feeds.py` + `topics/*/orgs.json scholars.json` | 把"值得 follow 的研究者 + 机构"批量导出为 OPML，喂给 RSS 阅读器 / 任何 agent | 想自己用 Inoreader / NetNewsWire 跟最新论文的人 |

`weekly_report` 与 `weekly_paper` 共享 ingest / storage / LLM 基础设施，但 prompt
与 data 目录完全独立，可独立调度。

---

## ⭐ Quick Start — 生成本周报告

```bash
# 一次性安装
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 配 DeepSeek key（默认走 deepseek-v4-pro；想省钱可改 .env 里的 MODEL_FILTER）
cp .env.example .env
# 编辑 .env 填 DEEPSEEK_API_KEY=sk-xxx

# 抓所有源 → 生成新闻 / 访谈双轨周报
.venv/bin/python -m weekly_report.run ingest    # ~20s, $0
.venv/bin/python -m weekly_report.run report    # ~10-12min, ~$0.045

# 抓 paper aggregator + lab blog → 生成研究周报
.venv/bin/python -m weekly_paper.run ingest     # ~20s, $0
.venv/bin/python -m weekly_paper.run report     # ~10-15min, ~$0.04-0.05
```

产出：

```
weekly_report/data/reports/
  2026-W18-tech.md          # 一线 builder/researcher 访谈、新模型、新方法、新评测
  2026-W18-industry.md      # 商业大事件、产品发布、资本财报、政策地缘、VC 视角

weekly_paper/data/reports/
  2026-W18-paper.md         # 7 主题分区：agent-harness / agent-rl / image-gen /
                             # video-gen / vla-embodied / vlm-llm-posttrain / world-model
                             # + TL;DR / 长读 / 编辑视角观察
```

三份合计 30-50 KB，**15-20 分钟可全部刷完**，覆盖产业 / 技术 / 研究三个层面。

### 完整 CLI

`weekly_report` 与 `weekly_paper` 共用同一套子命令模式：`ingest → filter → synth`，
或一次跑完的 `report`。

```bash
# ─── weekly_report ──────────────────────────────────────────────
.venv/bin/python -m weekly_report.run ingest                       # 抓 (无 LLM)
.venv/bin/python -m weekly_report.run preview                      # 看 raw 列表 (debug)
.venv/bin/python -m weekly_report.run filter                       # LLM 多轨分类
.venv/bin/python -m weekly_report.run synth                        # LLM 综述
.venv/bin/python -m weekly_report.run report                       # filter+synth (双轨)
.venv/bin/python -m weekly_report.run report --track tech          # 只生成 tech 报告
.venv/bin/python -m weekly_report.run report --track industry      # 只生成 industry 报告
.venv/bin/python -m weekly_report.run status                       # 每源健康度

# ─── weekly_paper ───────────────────────────────────────────────
.venv/bin/python -m weekly_paper.run ingest                        # 抓所有源
.venv/bin/python -m weekly_paper.run ingest --topic agent-rl       # 只抓某 topic 的 lab blog
.venv/bin/python -m weekly_paper.run ingest --topic research-agi   # 只抓 aggregator (HF/dair_ai)
.venv/bin/python -m weekly_paper.run filter                        # LLM 7-topic 分类
.venv/bin/python -m weekly_paper.run synth                         # LLM 综述
.venv/bin/python -m weekly_paper.run report                        # filter+synth
.venv/bin/python -m weekly_paper.run status                        # 每源健康度

# ─── 通用调试技巧 ────────────────────────────────────────────────
.venv/bin/python -m weekly_report.run ingest --source dwarkesh-yt  # 只抓单个源（debug）
.venv/bin/python -m weekly_paper.run report --week 2026-W17        # 回测/补跑某一周
.venv/bin/python -m weekly_paper.run filter --threshold 0.4        # 评分门槛更宽松
```

### 历史周回灌（backfill）

要给前 N 周补生成报告（举例：补 W16/W17 paper 报告）：

```bash
# 1) 把当前 W18 的 items 文件复制成 W16/W17 的基础（共享所有 RSS 历史，filter_in_week 会按周窗口收敛）
cp weekly_paper/data/items/2026-W18.jsonl weekly_paper/data/items/2026-W17.jsonl
cp weekly_paper/data/items/2026-W18.jsonl weekly_paper/data/items/2026-W16.jsonl

# 2) HF papers 是按周抓页面的，每周需单独 ingest（不会和现有 SeenIndex 冲突）
.venv/bin/python -m weekly_paper.run ingest --week 2026-W17 --source hf-papers-weekly
.venv/bin/python -m weekly_paper.run ingest --week 2026-W16 --source hf-papers-weekly

# 3) 生成报告（每周 ~10-15 min）
.venv/bin/python -m weekly_paper.run report --week 2026-W17
.venv/bin/python -m weekly_paper.run report --week 2026-W16
```

> ⚠️ DeepSeek API 有时会出现 30+ 分钟级别的 hang，OpenAI client 会自动重试。如果一周
> 报告超过 1 小时还没完成，可以杀掉重跑（filter 阶段是幂等的）。

---

## 架构

两个 pipeline 并行跑，共用 ingest / storage / LLM 基础设施，**各自有独立的 sources、
prompts 和 data 目录**：

### 数据流（weekly_report：新闻/访谈轨）

```
   topics/industry-agi/sources.json
               │
               ▼ (43 个源, RSS/YouTube/Apple Podcast/Substack)
   ┌────────────────────┐         ┌──────────────────────┐
   │ ingest (rss.py)    │ ──────▶ │ weekly_report/state/ │ ← 每源进度 / yt cache
   └────────┬───────────┘         │   seen.jsonl         │ ← 全局 url 去重
            ▼                     └──────────────────────┘
   items/<week>.jsonl  →  heuristic prefilter  →  filter (DeepSeek 多轨分类)
                                                       │
                            ┌──────────────────────────┤
                            ▼ track=tech               ▼ track=industry
                   synth tech (DeepSeek)        synth industry (DeepSeek)
                            │                          │
                            ▼                          ▼
                  reports/<week>-tech.md   reports/<week>-industry.md
```

### 数据流（weekly_paper：研究/paper 轨）

```
   topics/research-agi/sources.json     topics/{7 topics}/orgs.json::blog_rss
               │                                       │
               ▼ (HF / dair_ai / alphaxiv)            ▼ (按 URL 去重 → 6 个 lab blog)
                       \                              /
                        \                            /
                         ▼                          ▼
       sources_loader.py 合并 → 9 active 源
                       (4 cross blog + 2 单 topic blog + 3 aggregator)
                                  │
                                  ▼
   ┌─────────────────────────────────────────────────────┐
   │ ingest (复用 weekly_report.ingest.rss + 自定义 hf_papers)│
   └────────┬─────────────────────────────────────────────┘
            ▼
   items/<week>.jsonl  →  heuristic  →  filter (DeepSeek 7-topic classifier)
                                                  │
                                                  ▼
                                  filtered/<week>.jsonl
                                                  │
                                                  ▼
                                   synth (DeepSeek，1 次调用，按 topic 分区)
                                                  │
                                                  ▼
                                   reports/<week>-paper.md
```

### 关键设计决策

| 决策 | 为什么 |
|---|---|
| **Pipeline 而非 Agentic Loop** | source 是手维护的精选列表，不需要 agent 探索；pipeline 可预测、可重跑、可控成本。"智能" 只在最后两阶段。 |
| **JSONL 而非 SQLite** | 方便 `jq` / 编辑器 / git diff，按周 batch 天然适配。每个 stage 一个文件 = 天然 checkpoint。 |
| **每周一个目录单元** | 报告/状态都按 ISO 周 (`2026-W18`) 组织，回测、对比、清理都是 `rm <week>.jsonl` 级操作。 |
| **SeenIndex append-only** | 跨周 url 去重；启动 1 秒载入 set，运行时 O(1) 查询。 |
| **YouTube handle 运行时解析** | sources.json 写人类可读的 `@handle`，首次抓取时 scrape 出 `channelId` 并缓存到 state，后续不再解析。 |
| **多轨分类 + 双报告** | 用一次 filter 调用，同时给两份报告挑料。技术读者和商业读者读各自的，不互相污染信号。 |
| **Prompt 外置为 markdown** | 调风格不改 Python；想加新主题、调评分，改 `prompts/*.md` 即可。 |
| **每源独立失败容错** | 单源挂掉不影响整体；记录 `consecutive_failures`，后续可降权/告警。 |

详细技术决策见 [`weekly_report/README.md`](weekly_report/README.md)。

---

## 📥 添加新源

两个子模块的源管理是分开的，但都遵循 "改 JSON → 重跑 ingest" 的零代码模式：

| 子模块 | 加什么 | 加在哪个文件 |
|---|---|---|
| `weekly_report` | 新闻 / 访谈 / podcast / YouTube / Substack | `topics/industry-agi/sources.json` |
| `weekly_paper` (aggregator) | HF 周精选 / dair_ai newsletter / alphaxiv 等聚合源 | `topics/research-agi/sources.json` |
| `weekly_paper` (lab blog) | 任意 lab 的官方 blog RSS | 对应 `topics/<topic>/orgs.json` 的 `blog_rss` 字段 |

### A. 给 weekly_report 加源

**所有源在一个文件**：`topics/industry-agi/sources.json`。三种最常见的添加方式：

#### 1. 直连 RSS（newsletter / Substack / 博客）

```json
{
  "id": "your-source-id",
  "name": "Display Name",
  "group_id": "EN_NEWSLETTER",
  "type": "newsletter",
  "tier": "A",
  "lang": "en",
  "rss_url": "https://example.com/feed",
  "homepage": "https://example.com/"
}
```

#### 2. YouTube 频道（只给 handle 即可）

```json
{
  "id": "your-source-id",
  "name": "Channel Name",
  "group_id": "EN_YT_PODCAST",
  "type": "youtube",
  "tier": "A",
  "lang": "en",
  "youtube_handle": "ChannelHandle",
  "homepage": "https://www.youtube.com/@ChannelHandle"
}
```

系统会自动把 `@handle` 解析成 `channelId` 并缓存到 `weekly_report/data/state/sources.json`。

#### 3. 播客（小宇宙 / Apple Podcast）

先拿 Apple Podcasts 的播客 ID（URL 里 `id12345...` 那串），调 lookup API 拿真实 feed：

```bash
curl -s "https://itunes.apple.com/lookup?id=1613083252" | python3 -c "import sys,json;print(json.load(sys.stdin)['results'][0]['feedUrl'])"
# → https://feed.xyzfm.space/xxg7ryklkkft
```

```json
{
  "id": "onboard",
  "name": "OnBoard! (Monica)",
  "group_id": "CN_PODCAST",
  "type": "podcast",
  "tier": "S",
  "lang": "zh",
  "rss_url": "https://feed.xyzfm.space/xxg7ryklkkft",
  "homepage": "https://podcasts.apple.com/us/podcast/onboard/id1613083252"
}
```

#### 4. SSR blog 无 RSS（Next.js / Webflow 等）

如果一个 blog 没有 RSS 但 index 页是 SSR 的（`/blog`, `/engineering` 这类列表页直
接含每篇文章的 `<a href="...">`），可以用 `type: "scrape"`：

```json
{
  "id": "anthropic-engineering",
  "name": "Anthropic Engineering",
  "group_id": "EN_LAB_OFFICIAL",
  "type": "scrape",
  "tier": "S",
  "lang": "en",
  "index_url": "https://www.anthropic.com/engineering",
  "article_url_prefix": "https://www.anthropic.com/engineering/",
  "homepage": "https://www.anthropic.com/engineering"
}
```

`weekly_report/ingest/web_scrape.py` 会做：

1. fetch `index_url`，正则抠出所有 `href="<article_url_prefix><slug>"`（自动按 URL
   去重）；
2. 并发 fetch 每篇文章页（默认 6 worker，单源最多 60 篇）；
3. 解析每篇的：
   - title — `<meta property="og:title">`，自动剥掉 ` | Claude` / ` \ Anthropic` 等站点尾巴；
   - summary — 优先尝试每页的 article-specific hero `<p>`（class 含 `Hero`+`summary`），
     回退 og:description / `<meta name="description">`；自动检测并跳过通用站点描述
     （"Anthropic is an AI safety…"）；
   - published_at — 依次尝试 `article:published_time` / JSON-LD `datePublished` /
     Anthropic 的 `>Published <date>` / `<time datetime>`，支持 ISO 与 `Apr 30, 2026`
     人类格式；
4. 308/301 重定向自动跟随；如果 redirect 走到不同 host（典型：blog 文章被搬到 docs
   站），优雅跳过这一篇，不让整个源 fail。

### 字段释义

| 字段 | 必填 | 说明 |
|---|---|---|
| `id` | ✅ | **全局唯一 + kebab-case**。一旦定下来不要改（改了会丢历史 state 和 SeenIndex 去重）|
| `name` | ✅ | 报告里显示的源名 |
| `group_id` | ✅ | 必须是 `groups` 里定义过的 |
| `type` | ✅ | `newsletter` / `youtube` / `podcast` / `wechat` / `x` / `rss` / `scrape` |
| `tier` | ✅ | `S` / `A` / `B`，**仅作 prompt 提示**，LLM 不会单凭 tier 决定保留 |
| `lang` | ✅ | `en` / `zh`，影响 LLM oneliner 用什么语言 |
| `rss_url` | △ | 直连 RSS（最优先），任何能被 feedparser 解析的 URL |
| `youtube_handle` | △ | YouTube `@` 后面那串，给了就会自动抓 |
| `youtube_channel_id` | △ | 一般不用填，handle 解析后自动缓存 |
| `rsshub_path` | △ | 公众号/微博等用，需自建 RSSHub |
| `index_url` | △ | 仅 `type: scrape` — 文章列表页 URL |
| `article_url_prefix` | △ | 仅 `type: scrape` — 文章 URL 前缀，用来从 index 里筛文章链接 |
| `homepage` | ⭕ | 给人看的，报告里偶尔会用 |
| `notes` | ⭕ | 给你自己看的备注 |
| `disabled` | ⭕ | 可选，`true` = 跳过 ingest（暂未启用的源占位） |

### 中文源接入小抄

| 平台类型 | 接法 | 例子 |
|---|---|---|
| 国内站点（极客公园、虎嗅类） | 直接 RSS：`/rss` `/feed` `/rss.xml` 三种常见路径试一遍 | `https://www.geekpark.net/rss` |
| 小宇宙 / Apple Podcast | 调 `https://itunes.apple.com/lookup?id=<APPLE_ID>` 拿 `feedUrl` | `https://feed.xyzfm.space/xxg7ryklkkft` |
| YouTube 中文频道 | 跟英文一样，给 `youtube_handle` | 张小珺 / WhyNotTV |
| 微信公众号独发 | 公开 RSSHub 已不可靠，需自建 RSSHub Docker | 海外独角兽暂 `disabled` |

### 加完后的快速验证

```bash
# 只抓刚加的那一个源（不重跑全部）
.venv/bin/python -m weekly_report.run ingest --source <your-new-id>

# 看每个源的最新状态
.venv/bin/python -m weekly_report.run status
```

如果抓到 0 条 + 报错，看 `weekly_report/data/state/sources.json` 里的 `last_error`。

### B. 给 weekly_paper 加源

#### B1. 加一个 lab blog（最常见）

直接编辑对应 topic 的 `orgs.json`，给某 org 加 `blog_rss`：

```json
{
  "name": "OpenAI",
  "blog_rss": "https://openai.com/blog/rss.xml",
  ...
}
```

如果同一个 blog（比如 OpenAI / DeepMind / Anthropic）在多个 topic 的 `orgs.json` 里都
出现，`sources_loader.py` 会**自动按 URL 去重**：

- 出现在 ≥3 个 topic → 标为 `"cross"` topic + `"S"` tier
- 只在 1-2 个 topic → 保留首个出现的 topic
- 由 LLM 在 filter 阶段重新分类到正确的 topic

不需要去多个 `orgs.json` 同步维护；所有出现都会被合并成 1 个抓取目标。

#### B2. 加一个 aggregator 源（HF 周精选 / dair_ai 等）

编辑 `topics/research-agi/sources.json`，添加：

```json
{
  "id": "your-aggregator-id",
  "name": "Display Name",
  "type": "newsletter",                 // 或 "rss" / "hf-papers" / "alphaxiv" / "arxiv"
  "tier": "S",
  "lang": "en",
  "rss_url": "https://example.com/feed",
  "homepage": "https://example.com/",
  "topic": "research-agi"               // aggregator 一律 research-agi，让 LLM 重分类
}
```

特殊 type 说明：

| type | 谁处理 | 备注 |
|---|---|---|
| `newsletter` / `rss` | `weekly_report.ingest.rss` 复用 | 99% 情况够用 |
| `hf-papers` | `weekly_paper.ingest.hf_papers`（自定义 scraper） | URL 用 `https://huggingface.co/papers/week/<week_id>` 模板，weekly_paper 会自动替换 `<week_id>` |
| `alphaxiv` | `weekly_paper.ingest.alphaxiv`（自定义 scraper） | 抓 `https://www.alphaxiv.org/` 的 7-day trending，从 RSC stream 解析；带 visits/votes/topics/github 信号，早于本周一的 trending 论文会 clamp 到周一 |
| `arxiv` | 占位（v2 实现） | 已注册到 `VALID_TYPES`，等待自定义 scraper |

#### B3. 验证

```bash
.venv/bin/python -m weekly_paper.run ingest --source <your-new-id>
.venv/bin/python -m weekly_paper.run status
```

---

## 当前源清单（截至 2026-W19）

### `weekly_report` 源（49 个，46 active + 3 disabled）

```
EN_NEWSLETTER (15)  Stratechery, Import AI, Interconnects, SemiAnalysis, Platformer,
                    Newcomer, One Useful Thing, AI Snake Oil, Pragmatic Engineer,
                    Lenny's Newsletter, Latent Space, Dwarkesh Substack, Big Technology,
                    ChinaTalk, Synced Review

EN_YT_PODCAST (13)  Dwarkesh Patel, No Priors, Unsupervised Learning, Cognitive Revolution,
                    BG2 Pod, Acquired, Hard Fork, Decoder, Lex Fridman, a16z Podcast,
                    20VC, Logan Bartlett Show, Lenny's Podcast

EN_LAB_OFFICIAL (10) Anthropic YT, Google DeepMind YT, Y Combinator YT, Sequoia Capital YT,
                    OpenAI YT, OpenAI News (RSS), Google DeepMind blog.google (RSS),
                    Google DeepMind Publications (scrape), Anthropic Engineering (scrape),
                    Claude Blog (scrape)

CN_NEWSLETTER (1)   极客公园

CN_PODCAST (5)      OnBoard! (Monica), 晚点聊 LateTalk, 晚点在场, 42章经, 硅谷101

CN_YT_PODCAST (2)   张小珺, WhyNotTV

CN_RSSHUB (3,disabled) 海外独角兽, Founder Park, 远川研究所  (需自建 RSSHub)
```

### `weekly_paper` 源（9 active）

```
Aggregator (3)       hf-papers-weekly (HuggingFace Daily Papers 周页),
                     dair-ai-newsletter (NLP Newsletter by Elvis Saravia),
                     alphaxiv-trending (alphaxiv 7-day trending; 自定义 RSC scraper)

Lab Blog cross (4)   blog-openai, blog-google-deepmind, blog-huggingface-trl,
                     blog-allen-institute-for-ai-tülu                       ← 同 URL 出现在 ≥2 topic

Lab Blog single (2)  blog-github-copilot, blog-aider-paul-gauthier          ← 仅 agent-harness

[暂未启用的 RSS]     Anthropic news（Next.js SPA，无 RSS，待自定义 scraper）；
                     大部分国产 lab（Qwen/DeepSeek/Moonshot/Zhipu）；
                     Meta AI / Google Research / MS Research（orgs.json 中无 blog_rss 字段）
```

> 7 topics 的 `orgs.json::blog_rss` 字段会被 `sources_loader.py` 自动展开 + 去重，不需要
> 单独维护清单。
>
> 要看实际抓取目标：
>
> ```bash
> .venv/bin/python -c "from weekly_paper.sources_loader import load_all_paper_sources as L; [print(s.id, s.topic, 'disabled' if s.disabled else 'active') for s in L().sources]"
> ```

---

## 项目结构

```
info_system/
├── README.md                       # 本文件
├── .env.example
├── requirements.txt
│
├── weekly_report/                  自动周报：新闻/访谈轨
│   ├── README.md                   #   详细技术文档
│   ├── run.py                      #   CLI 入口
│   ├── sources.py                  #   Source 数据模型 + sources.json 加载
│   ├── items.py                    #   Item 数据模型 + URL 归一化
│   ├── storage.py                  #   JSONL / SeenIndex / week-id 工具（被 weekly_paper 复用）
│   ├── llm.py                      #   DeepSeek client + CostTracker（被 weekly_paper 复用）
│   ├── ingest/rss.py               #   RSS / Atom / YouTube 抓取（被 weekly_paper 复用）
│   ├── filter.py                   #   LLM 多轨分类
│   ├── synthesize.py               #   LLM 综述生成两份周报
│   ├── prompts/                    #   ★ LLM 指令
│   │   ├── filter.md
│   │   ├── synthesize-tech.md
│   │   └── synthesize-industry.md
│   └── data/
│       ├── state/                  #   ★ git tracked（每源进度 + 全局 SeenIndex）
│       ├── items/                  #   gitignore，每周 raw items
│       ├── filtered/               #   gitignore，每周带 LLM 评分
│       └── reports/                #   ★ git tracked，<week>-tech.md / <week>-industry.md
│
├── weekly_paper/                   ⭐ 自动周报：研究/paper 轨（新）
│   ├── README.md                   #   模块详细文档
│   ├── run.py                      #   CLI 入口（重用 weekly_report.ingest 等）
│   ├── paths.py                    #   data 目录定义 + 7 topic 常量
│   ├── sources_loader.py           #   合并 research-agi/sources.json + 7 topics 的 blog_rss
│   ├── ingest/hf_papers.py         #   HuggingFace 周精选 paper 自定义 scraper
│   ├── ingest/alphaxiv.py          #   alphaxiv 7-day trending 自定义 scraper（RSC）
│   ├── filter.py                   #   LLM 7-topic 分类器
│   ├── synthesize.py               #   LLM 一次综述生成全部 7 个 topic 分区
│   ├── prompts/
│   │   ├── filter.md               #   7-topic 分类 + 评分规则
│   │   └── synthesize.md           #   按 topic 分区的报告骨架
│   └── data/                       #   独立 state/items/filtered/reports，与 weekly_report 互不影响
│
├── topics/                         #   每个 topic 一个目录
│   ├── industry-agi/               #   weekly_report 的源
│   │   └── sources.json
│   ├── research-agi/               #   ⭐ weekly_paper 的 aggregator 源（HF / dair_ai 等）
│   │   └── sources.json
│   ├── agent-harness/              #   weekly_paper 自动用 orgs.json::blog_rss
│   │   └── orgs.json
│   ├── agent-rl/
│   │   └── orgs.json
│   ├── image-generation/           #   60 学者，OPML 子系统用 scholars.json
│   │   └── scholars.json
│   ├── video-generation/
│   │   └── orgs.json
│   ├── vla-embodied/
│   │   └── orgs.json
│   ├── vlm-llm-posttrain/
│   │   └── orgs.json
│   └── world-model/
│       └── orgs.json
│
├── generate_feeds.py               #   OPML 子系统（仍可用，把 7 topics 的 orgs/scholars 导出 OPML）
└── out/                            #   OPML 子系统的产物
    └── all.opml
```

---

## 调 prompt（不改代码改风格）

LLM 全部指令在两个 `prompts/` 目录：

**weekly_report/prompts/**

| 文件 | 控制什么 | 什么时候改 |
|---|---|---|
| `filter.md` | 多轨分类规则、评分尺度、theme 列表、边界判定 | 发现某类内容总进错 track，或想加新分类 |
| `synthesize-tech.md` | tech 周报结构（builder 访谈、新模型、tech digest…） | 想换报告骨架（加/删主题区） |
| `synthesize-industry.md` | industry 周报结构（商业大事件、产品、资本、政策、VC…） | 同上 |

**weekly_paper/prompts/**

| 文件 | 控制什么 | 什么时候改 |
|---|---|---|
| `filter.md` | 7-topic 分类、评分尺度、🎯 benchmark 强制保留规则、🏭 工业级 tech report 强制高分规则 | 想新加一个研究主题，或某主题总被错分 |
| `synthesize.md` | 报告骨架（TL;DR / 7 topic 分区 / 长读 / 编辑观察） | 调每个 topic 区块的格式、控制总长度 |

`weekly_paper/prompts/filter.md` 内置两条**强约束**，调风格时不要轻易删：

- **🎯 Benchmark / Eval handling**：任何提出新评测集 / leaderboard 的 paper，无论
  来自哪个 tier，统一按规则给 0.70-0.95；oneliner 必须写明 benchmark 名字 + 覆盖范围
  + 模型对比关键数字。原则："**宁可放过营销噪声，也不能漏掉新 benchmark**"。
- **🏭 Industrial-grade Technical Report**：任何来自前沿 / 工业 lab 的 system card /
  model card / full technical report，强制 0.85-0.95；带 ablation / 训练细节 / 工程量
  化结果的优先。原则："**宁可放过 5 篇噪声，也不能漏掉 1 篇 tech report**"。

改完直接重跑 `synth`，**filter 缓存还在的话只重花 synth 的几分钱**。

---

## 实测成本（DeepSeek V4 Pro · `deepseek-v4-pro`）

V4 Pro 定价（cache-miss 折扣价，截至 2026-05-31）：input $0.435/M、output $0.87/M。

### `weekly_paper` 实测（W16/W17/W18，每周 1 次报告）

| 周 | in-week 项 | 保留项 | filter 时间/成本 | synth 时间/成本 | **总计** |
|---|---|---|---|---|---|
| 2026-W18 | 74 | 44 (59%) | 7.3 min · $0.0254 | 4.2 min · $0.0157 | **11.5 min · $0.0411** |
| 2026-W17 | 79 | 54 (68%) | 9.2 min · $0.0305 | 5.5 min · $0.0220 | **14.7 min · $0.0526** |
| 2026-W16 | 68 | 50 (74%) | 9.9 min · $0.0285 | 4.4 min · $0.0179 | **14.3 min · $0.0464** |
| **均值** | **74** | **49** | **8.8 min · $0.028** | **4.7 min · $0.019** | **~13 min · $0.047** |

token 量级：每周 ~50K input + ~25K output（filter + synth 合计）。

### `weekly_report` 估算（43 sources, ~50 in-week items, 双轨）

> 注：V4 Pro 切换后还未做完整周端到端测；下表是按 V3 实测 + V4 Pro 价格折算的估算。

| 场景 | 时间 | 成本 |
|---|---|---|
| 只 ingest（无 LLM） | ~20s | $0 |
| filter (多轨分类) | ~3-5 min | ~$0.020 |
| synth (一份 ≈ tech 或 industry) | ~3-5 min | ~$0.012 |
| **完整端到端 = ingest + filter + synth × 2** | **~10-15 min** | **~$0.045 / 周** |

### 总览

两份合计 **~$0.09 / 周**，年成本 **≈ RMB 33 元**。V4 Pro 比 V3 chat 慢 ~5×、贵 ~1.8×，
但 oneliner 与综述明显更具体（benchmark 名字、对比数字、跨 topic 趋势抓得更准）。

> 想省时间/钱：把 `.env` 里的 `DEEPSEEK_MODEL_FILTER=deepseek-v4-flash`
> （filter 阶段是分类任务，flash 完全够用，~5× 便宜 + 快得多），synth 留 v4-pro 保质量。
> 不改代码。

---

## OPML 子系统（辅）

`generate_feeds.py` 是早期的子系统，**面向不同用途**：把 `topics/*/scholars.json` /
`topics/*/orgs.json` 的研究者/机构清单导出为 RSS 阅读器可吃的 OPML 文件，再加 GitHub
org activity / Google Scholar 等论文源。

主要用法：

```bash
# 处理所有 topic + 生成总 OPML
python3 generate_feeds.py --merge

# 只处理某一个 topic
python3 generate_feeds.py --topic vla-embodied

# 自建 RSSHub 后用本地实例
python3 generate_feeds.py --instance http://localhost:1200 --merge
```

产物在 `topics/<topic>/out/feeds.opml`，导入 Inoreader / Feedly / NetNewsWire 即可。

详细设计（包括 RSSHub 路由、X handle / Google Scholar / HuggingFace 派生 URL 的规则）
见本 README 历史版本（git log）。

> **注**：三个子系统的输入文件是部分共享的：
> - `weekly_report` 用 `topics/industry-agi/sources.json`
> - `weekly_paper` 用 `topics/research-agi/sources.json` + 7 topics 的 `orgs.json::blog_rss`
> - OPML 子系统用 7 topics 的 `orgs.json` + `scholars.json`（完整字段）
>
> `orgs.json` 是 OPML 子系统和 weekly_paper 共用的 source-of-truth。在 `orgs.json`
> 里加 / 修 `blog_rss` 字段，weekly_paper 下次 ingest 自动生效。

---

## Roadmap

按优先级：

**weekly_paper 扩展（v2）**
- ✅ **alphaxiv 7-day trending HTML scraper**：从 Next.js RSC stream 抽取 trendingPapers，带 visits/votes/topics/github 信号
- ✅ **OpenAI / Google DeepMind 官方源接入**：`openai-news`（RSS）、`openai-yt`（YouTube）、`google-deepmind-blog`（blog.google RSS）、`deepmind-publications`（SSR scrape）— W19 验证 5/5 OpenAI 新发布命中（GPT-5.5 Instant + system card + voice AI + ChatGPT ads + PwC）
- ✅ **Anthropic Engineering / Claude Blog scraper**：通用 `type: scrape` 已覆盖 `anthropic.com/engineering` + `claude.com/blog`（Webflow SSR + Next.js SSR，带 308 跨域兜底、og 标签 + JSON-LD 双路解析）
- 🟡 **Anthropic news scraper**：`anthropic.com/news` 是 Next.js SPA（无 SSR），单独适配中；目前在 7 个 `orgs.json` 里仍 `disabled`
- ⏳ **HF community blog scraper**：补 SenseNova-U1 这类只发在 huggingface.co/blog/<org> 而不进 daily papers 的内容
- ⏳ **arxiv 类目 RSS**（cs.LG / cs.CV / cs.RO / cs.CL）：作为 long-tail 兜底
- ⏳ **GitHub `releases.atom` for 关键 repo**（DeepSeek、Qwen、Mistral 等）：比 org activity 信号高 10×
- ⏳ **HF org papers feed**：需 self-hosted RSSHub，公共实例已 403

**两子系统共用**
- ⏳ **自建 RSSHub Docker**：解锁公众号独发的拾象/远川/Founder Park + HF org papers
- ⏳ **播客 / 视频转录**（Groq Whisper + YouTube auto-caption）：让 LLM 看到内容而非只是 RSS 摘要
- ⏳ **抽 `core/` 共享包**：目前 weekly_paper 直接 import weekly_report 的 storage/llm/items/ingest，等模块成熟后正式抽出
- ⏳ **输出渠道**（Notion API / Email / Telegram push）：周报自动送到阅读器
- ⏳ **GitHub Actions 周一定时调度**：每周一早 8 点自动跑、push 报告
- ⏳ **跨周 trend 检测**：同一 builder/paper-topic 连续 N 周出现作为编辑观察的输入
- ⏳ **过滤回放工具**：可视化看 dropped items 列表，方便人工 review 评分阈值
- ⏳ **DeepSeek API 稳定性兜底**：v4-pro 偶有 30+ min hang，需要在 `weekly_report/llm.py` 加 timeout/降级到 v4-flash 的 fallback 链

---

## License & 致谢

MIT.

灵感来自 [zarazhangrui/follow-builders](https://github.com/zarazhangrui/follow-builders)；
OPML 子系统的「研究者 + 机构」schema 是它的扩展，weekly_report / weekly_paper 子系统
是更进一步的「自动综述 + 多轨周报」管线。
