# weekly_report — 深度技术文档

> ℹ️ 项目高层介绍 / 安装 / 添加源 / 整体架构请看 [根 README](../README.md)。
> 本文件是 weekly_report 模块的**深度技术参考**：实现细节、调试技巧、数据查询配方等。

每周自动抓 `topics/*/sources.json` 里的源（RSS / YouTube / podcast），存成 JSONL，
后续 LLM 阶段把它综述成一份周报供碎片时间阅读。

数据存储是 **JSONL + 内容寻址 cache**（不是 SQLite），方便人工 review、git diff、跨机迁移。

---

## 当前实现的范围

- ✅ Source 加载（`sources.py`）
- ✅ 持久化层（`storage.py`）：原子 JSON 写、JSONL append、SeenIndex 跨周去重、ISO 周窗口
- ✅ RSS / Atom / YouTube 抓取（`ingest/rss.py`，含 YouTube `@handle → channel_id` 解析 + 缓存）
- ✅ 无 LLM 的 preview 输出（`compose.py`）：按 group + source 分组、按周窗口过滤
- ✅ **DeepSeek LLM 客户端**（`llm.py`）：retry、JSON mode、CostTracker
- ✅ **LLM filter**（`filter.py`）：heuristic 预过滤 + DeepSeek 多轨分类（`tech` / `industry` / `noise` + score + theme + oneliner）
- ✅ **LLM synthesize**（`synthesize.py`）：每个 track 一次调用，生成对应周报
- ✅ **双轨周报**：
  - `reports/<week>-tech.md` — 一线 builder/CEO/researcher 访谈、新模型、新方法、新评测（你的核心信号）
  - `reports/<week>-industry.md` — 商业大事件、产品发布、资本财报、政策地缘、VC 视角
- ✅ **Prompts 外置**（`prompts/filter.md`, `prompts/synthesize-tech.md`, `prompts/synthesize-industry.md`）— 调 prompt 不改代码
- ✅ CLI（`run.py`）：`ingest / preview / filter / synth [--track] / report [--track] / status`

**实测端到端成本（W18，99 → 27 tech + 31 industry kept，含 7 个新中文源）**：~$0.030/周（约 2 分人民币），耗时 ~180s。

**已接入的中文源**：
- `CN_NEWSLETTER`: 极客公园（中文科技日报，AI/产品/创业广覆盖）
- `CN_PODCAST`: OnBoard! / 晚点聊 LateTalk / 晚点在场 / 42章经 / 硅谷101（小宇宙 / Apple Podcast RSS）
- `CN_YT_PODCAST`: 张小珺 / WhyNotTV
- `CN_RSSHUB` (disabled): 海外独角兽 / Founder Park / 远川研究所 — 公众号独发，等自建 RSSHub

**还没做的（按优先级）：**

- ⏳ 自建 RSSHub Docker：解锁公众号独发的拾象/远川/Founder Park
- ⏳ Step 4: 播客转录（Groq Whisper），YouTube auto-caption — 让 LLM 看到内容而非只是 RSS 摘要
- ⏳ Step 5: 输出渠道（Notion API / Email / Telegram push）
- ⏳ Step 6: GitHub Actions 周一定时调度

---

## 用法

```bash
# 0. 一次性安装依赖 + 配 .env (cp .env.example .env, 填 DEEPSEEK_API_KEY)
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# === 完整周报流程 (~$0.02 + ~2.5 分钟，出两份报告) ===
.venv/bin/python -m weekly_report.run ingest    # 抓所有源 → items/<week>.jsonl
.venv/bin/python -m weekly_report.run report    # filter + synth(tech) + synth(industry)

# === 只要某一份 ===
.venv/bin/python -m weekly_report.run report --track tech       # 只 tech
.venv/bin/python -m weekly_report.run report --track industry   # 只 industry

# === 分阶段执行（每阶段都是 checkpoint，可单独重跑）===
.venv/bin/python -m weekly_report.run ingest    # 抓 (无 LLM, ~15s)
.venv/bin/python -m weekly_report.run preview   # 看抓到啥的 raw 列表 (无 LLM)
.venv/bin/python -m weekly_report.run filter    # LLM 多轨分类 (~60s, ~$0.01)
.venv/bin/python -m weekly_report.run synth     # 两份 synth (~80s, ~$0.012)
.venv/bin/python -m weekly_report.run synth --track tech    # 只重生成 tech

# === 调试技巧 ===
.venv/bin/python -m weekly_report.run ingest --source dwarkesh-yt
.venv/bin/python -m weekly_report.run report --week 2026-W17
.venv/bin/python -m weekly_report.run filter --threshold 0.4    # 更宽松
.venv/bin/python -m weekly_report.run status
```

## 调 prompt

LLM 的所有指令在 `prompts/`，**改这三个文件无需改 Python 代码**：

- `prompts/filter.md` — 多轨分类（tech/industry/noise）+ 评分尺度 + theme 列表 + 边界 case
- `prompts/synthesize-tech.md` — 技术周报结构（builder 访谈、新模型、tech digest…）
- `prompts/synthesize-industry.md` — 产业周报结构（商业大事件、产品、资本、政策、VC…）

改完直接重跑对应 stage（`filter` / `synth`），不需要重抓。`synth` 默认 `--track both` 出两份；`--track tech` / `--track industry` 单出。

---

## 文件布局

```
weekly_report/
├── __init__.py
├── README.md                 # 本文件
├── items.py                  # Item dataclass + url_hash() 归一化
├── sources.py                # 加载 topics/*/sources.json
├── storage.py                # JSONL / state / SeenIndex / week id
├── compose.py                # 无 LLM 的 preview 渲染
├── llm.py                    # DeepSeek 客户端（OpenAI 兼容）+ CostTracker
├── filter.py                 # LLM filter 阶段（score / theme / oneliner）
├── synthesize.py             # LLM synth 阶段（最终 markdown 周报）
├── run.py                    # CLI 入口
├── ingest/
│   ├── __init__.py
│   └── rss.py                # RSS / Atom / YouTube
├── prompts/                  # ★ LLM 指令（改这仨不用改代码）
│   ├── filter.md
│   ├── synthesize-tech.md
│   └── synthesize-industry.md
└── data/                     # 运行时数据（部分 gitignore）
    ├── state/                # ★ git tracked
    │   ├── sources.json      # 每个 source 的进度（last_seen 等）
    │   └── seen.jsonl        # 全局 url 去重日志
    ├── items/                # gitignore，每周一个 jsonl（原始抓取）
    │   └── 2026-W18.jsonl
    ├── filtered/             # gitignore，每周一个 jsonl（带 LLM 评分）
    │   └── 2026-W18.jsonl
    ├── clusters/             # gitignore（预留，目前 synth 一步到位不分 cluster 文件）
    ├── cache/                # gitignore（Step 4 转录用）
    │   └── transcripts/
    └── reports/              # ★ git tracked，最终周报
        ├── 2026-W18-preview.md   # 无 LLM 的 raw 列表（debug 用）
        └── 2026-W18.md           # 最终 LLM 综述
```

---

## sources.json schema

参见 `topics/industry-agi/sources.json`。核心字段：

```jsonc
{
  "id": "stable-id",            // 唯一，state 跟踪用，定下来不要改
  "name": "Display Name",
  "group_id": "...",
  "type": "newsletter|youtube|podcast|wechat|x|rss",
  "tier": "S|A|B",              // 给 LLM 的提示，不会单凭 tier 决定保留
  "lang": "en|zh",              // 影响 LLM oneliner 用什么语言
  "rss_url": "...",             // 直连 RSS（最优先）
  "youtube_handle": "...",      // 没 channel_id 时用，运行时自动解析并缓存到 state
  "youtube_channel_id": "UC...", // 已知就直接用
  "rsshub_path": "/wechat/...",  // 没直连 RSS 时备用（需自建 RSSHub）
  "homepage": "...",
  "notes": "...",
  "disabled": true              // 可选，true = 跳过 ingest（暂未启用的 wechat 源）
}
```

新增源 = 改 JSON，不改代码。

### 中文源接入小抄

| 平台 | 接法 | 例子 |
|---|---|---|
| 国内站点（极客公园、虎嗅等） | 直接 RSS：`/rss` `/feed` `/rss.xml` 三个常见路径 | `https://www.geekpark.net/rss` |
| 小宇宙 / Apple Podcast | 调 `https://itunes.apple.com/lookup?id=<APPLE_ID>` 拿 `feedUrl`，多数是 fireside / xyzfm | `https://feed.xyzfm.space/xxg7ryklkkft` (OnBoard!) |
| 微信公众号（独发） | 公开 RSSHub 已基本不可用，需自建 RSSHub 或迁移 substack | 海外独角兽 / 远川 暂 `disabled` |
| YouTube 中文频道 | 跟英文一样，给 `youtube_handle` 即可 | 张小珺 / WhyNotTV |

---

## 关键设计决策

1. **Pipeline 而非 Agentic Loop**：source 是手维护的精选列表，不需要 agent 探索，
   pipeline 可预测、可调试、便宜。"智能" 只在最后的 synthesize 阶段。

2. **JSONL 而非 SQLite**：方便 `jq / 编辑器 / git diff`，pipeline 天然按周 batch，
   跨周查询少。每个 stage 一个文件。详见根 README。

3. **大字段外置**：transcript / 全文 → `cache/<sha256>.json`，主 jsonl 永远 < 10MB
   仍可秒开。

4. **SeenIndex append-only**：跨周 url 去重，启动时 1 秒载入 set，运行时 O(1) 查询。

5. **YouTube handle 运行时解析**：`sources.json` 里写 `@handle`（人可读），
   首次抓取时 scrape 出 channel_id 并缓存到 `state/sources.json`，后续不再解析。

6. **每个 source 独立失败容错**：单源挂掉不影响整体，记录 `consecutive_failures`，
   后续可以根据它降权或告警。

---

## ad-hoc 数据查询（替代 SQL）

```bash
# 本周条目数 by source
jq -r .source_id weekly_report/data/items/2026-W18.jsonl | sort | uniq -c | sort -rn

# 某个源的所有条目
jq -c 'select(.source_id == "dwarkesh-substack")' weekly_report/data/items/2026-W18.jsonl

# 看 tier=S 的
jq -c 'select(.source_tier == "S") | {source_id, title, url}' weekly_report/data/items/2026-W18.jsonl

# 时长 > 1 小时的视频/播客（适合长读 list）
jq -c 'select(.duration_sec > 3600) | {source_id, title, duration_sec, url}' weekly_report/data/items/2026-W18.jsonl
```
