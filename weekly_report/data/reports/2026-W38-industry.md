# Weekly Industry Report · 2026-W38

_33 items kept across 13 sources · window 2026-09-14 → 2026-09-21_

## 🔥 30 秒 TL;DR

- **Meta 个人 AI 助手 Muse 上线一周登顶美国 App Store 免费榜**，超越 ChatGPT，主打代用户执行填表、购物、订餐等实际任务，被视为「个人超级智能」战略的市场验证。([极客公园](http://www.geekpark.net/news/370615))
- **字节豆包工作正式发布、飞书 8.0 为 Agent 重构协同平台**，腾讯 WorkBuddy 已跑出千万月活、阿里整合钉钉与桌面/云端 Agent——中国大厂 Agent 办公「大会战」全面开打。([极客公园](http://www.geekpark.net/news/370460) · [极客公园](http://www.geekpark.net/news/370431))
- **Manus 拟完成 5 亿美元融资、估值翻倍至 40 亿美元**，为撤销 Meta 收购交易后首轮，将成中国估值最高的 AI 智能体创业公司。([极客公园](http://www.geekpark.net/news/370539))
- **Crusoe 单轮融资近 40 亿美元、投后估值 309 亿美元**；同期地瓜机器人完成 4 亿美元 C 轮、Bain Capital Ventures 新设 16 亿美元基金——资本继续向 AI 基建与具身智能集中。([Newcomer](https://www.newcomer.co/p/war-in-the-middle-east-and-rising) · [极客公园](http://www.geekpark.net/news/370539))
- **OpenAI、Anthropic、谷歌 DeepMind 三方联手研究 AI 安全措施**，OpenAI 政策主管称此类协调无需反垄断豁免；但特朗普公开抨击 Anthropic CEO 的放缓呼吁，白宫内部就监管形成两派。([极客公园](http://www.geekpark.net/news/370375) · [极客公园](http://www.geekpark.net/news/370306))

## 📂 主题深度

### 🤝 商业大事件 / Major Deals & Strategy

**为什么本周值得看**: 本周战略主线是「Agent 即界面」——Salesforce 主动放弃 UI 护城河、Box 押注应用层 harness、中国大厂把办公协同平台重构成 Agent 底座。与此同时，AI 基建融资开始被地缘与利率风险笼罩，但 Crusoe 的 309 亿美元估值说明资本尚未退潮。

- [Salesforce AI Force, Agents as UI, The Race to Headless](https://stratechery.com/2026/salesforce-ai-force-agents-as-ui-the-race-to-headless/) — _Stratechery_ · Ben Thompson 认为 Salesforce 放弃 UI 护城河是明智之举，因为 UI 作为护城河对所有人都在消失，竞争转向 headless 架构与 Agent 界面。
- [腾讯、字节、阿里「会战」AI 办公之后：Agent 领域格局已变](http://www.geekpark.net/news/370431) — _极客公园_ · 汪华判断大厂重金押注 AI 办公的驱动力是「恐惧」：Claude Code 未到千万月活时 ARR 已达 200 亿美元，高价值专业工作入口可能不建立在日活之上；GLM-5.3-Flash、DeepSeek-V4-Flash 把成本打下来，才是中国 Agent 爆发的真正原点。
- [Box's Aaron Levie: On Reinventing Yourself in the AI Age](https://www.youtube.com/watch?v=NE4CLThMPGU) — _Sequoia Capital_ · Levie 主张价值不在模型本身，而在从模型能力到银行、律所、药企实际工作流的「桥」；Box 自建紧贴自身文件系统与权限的 agent harness，在准确率与延迟上击败直接调用 Claude/ChatGPT，并警告实验室的 token 补贴不可持续。
- [War in the Middle East & Rising Interest Rates Threaten the Funding for AI Build-Out](https://www.newcomer.co/p/war-in-the-middle-east-and-rising) — _Newcomer_ · 中东冲突与石油出口下滑威胁支撑 AI 基建的资本流，但目前尚未明显放缓；同篇还提到 Menlo Ventures 报告发现消费者用 AI 赚钱但仍留在现有聊天机器人。
- [京东押注物理 AI，冲在前面的是一群 95 后](http://www.geekpark.net/news/370519) — _极客公园_ · 京东 JDD 大会主题定为「JoyAI · 跃迁物理世界」，战略目标是建设全球最大物理世界运营中心；团队复盘「京东 AI 购」纯对话式购物试点后承认对话模式不适配全部购物场景。
- [Token 之后，谁来组织 AI 计算？Arm 寻找下一代计算的答案](http://www.geekpark.net/news/370453) — _极客公园_ · Arm 首次把未来拆成云 AI、边缘 AI、物理 AI 三条线，从「CPU IP 供应商」转向计算基建底座；基于 Arm 技术的芯片累计出货已超 3500 亿颗。
- [Databricks' Ali Ghodsi Never Wanted to Be CEO. Now He's Among the Best](https://www.youtube.com/watch?v=k7wPdCNfljQ) — _Sequoia Capital_ · Ghodsi 复盘 2015 年以「试用」身份接任 CEO（当时公司仅 150 万美元收入、董事会暗中面试他人），其方法论是找出公司最大瓶颈并投入不成比例的注意力两三年，以此建起 Lakehouse 品类。

### 📦 产品 & 平台动向 / Products & Platforms

**为什么本周值得看**: 本周产品侧两条线并行：一是 Agent 从「对话」走向「办事」并开始接管支付与交易（蚂蚁 APASS、努比亚 AI 手机、Claude 合并 Cowork）；二是 AI 硬件在手机背面与消费级机器人两个新品类上同时爆发。

- [在飞书的上下文底座上，豆包开工了](http://www.geekpark.net/news/370460) — _极客公园_ · 飞书 8.0 为 Agent 重构协同平台，豆包工作提供原生融入飞书的企业级 Agent，定向共创的「豆包工作伙伴」探索拥有独立身份、权限和记忆的团队智能体；字节 CEO 梁汝波到场回顾四轮技术浪潮。
- [Astra for Law: Frontier intelligence built for your practice.](https://www.youtube.com/watch?v=YeeGHCixr7o) — _OpenAI_ · OpenAI 推出 Astra for Law，基于 GPT-6 Astra 搭配法律分析与写作指令，新建 Legal Search Index 覆盖美国判例、法规、法院规则等超 2.3 亿 URL 且每日更新；同时上线 26 个合作方插件与 47 个社区插件，合作方包括 Thomson Reuters、Harvey、Legora、iManage。
- [当智能体开始替人花钱，如何证明「它是谁」？](http://www.geekpark.net/news/370440) — _极客公园_ · 蚂蚁集团外滩大会发布 APASS 智能体支付信任基础设施，基于 KYA（认知你的智能体）理念，通过身份与意图两条信任链核验 Agent 身份、授权边界与实际行为，解决静态免密授权在开放网络长任务中「变成空白支票」的问题。
- [Meta 个人助手登顶美国 App Store；张雪机车发 5 款新车…](http://www.geekpark.net/news/370615) — _极客公园_ · Meta Muse 上线仅一周登顶苹果美国 App Store 免费榜，可代用户填表、购物、订餐、找宠物照看，并连接邮箱、日历、Spotify、Instagram、OpenTable；同篇还传 Anthropic 考虑在 IPO 前发布新一代旗舰模型以塑造估值环境。
- [马斯克再暗示合并特斯拉和 SpaceX；传 iPhone 18 Pro 系列卖爆…](http://www.geekpark.net/news/370472) — _极客公园_ · 努比亚 NaviX Ultra 上市，官方称「全球首款 AI 智能体手机」、首台搭载豆包手机助手消费者版，5999 元起，京东预约超 37 万台，首销销售额「一秒破亿」；搭载行业首个集成指纹识别的独立 AI 按键。
- [AI 硬件创业者，疯狂涌入手机的背面](http://www.geekpark.net/news/370610) — _极客公园_ · Plaud AI 录音卡累计出货破百万台、ARR 达 1 亿美元、用户超 250 万；阅星曈完成近 5000 万元 A 轮追加融资，极稚科技无源墨水屏手机壳卖出超 14 万只（八成销往海外）；钉钉、出门问问、科大讯飞、360 已进入 AI 录音卡市场。
- [Claude Cowork and chat are now one Claude](https://claude.com/blog/cowork-is-now-claude) — _Claude Blog_ · Anthropic 将 Claude Cowork 与 chat 合并为统一 Claude，在 Pro 与 Max 套餐推出，定位「交付任务、保留最终决定权」。
- [专访爆火「机器鸭」背后的硬件推手](http://www.geekpark.net/news/370269) — _极客公园_ · Hugging Face 旗下 Pollen Robotics 设计的 399 美元机器鸭 Microduck 由深圳矽递科技（Seeed Studio）制造，高峰期平均每 4 秒卖出一台，五天预售破万台、销售额超 500 万美元，订单排到明年；潘昊观察到硅谷团队来华正从「采购」变成「托孤」。

### 💰 资本 & 财报 / Capital & Earnings

**为什么本周值得看**: 资金继续向 AI 基建与 Agent 安全层集中，单笔规模显著放大（Crusoe 近 40 亿美元、地瓜 4 亿美元），且节奏加快——地瓜距上轮仅 5 个月。同时字节的净利率下滑揭示大厂为 AI 投入付出的财务代价。

- [War in the Middle East & Rising Interest Rates Threaten the Funding for AI Build-Out](https://www.newcomer.co/p/war-in-the-middle-east-and-rising) — _Newcomer_ · Crusoe 单轮融资近 40 亿美元，投后估值 309 亿美元；Bain Capital Ventures 同期公布 16 亿美元新基金。
- [影视飓风 Tim 称 iPhone Duo「烫到握不住」…](http://www.geekpark.net/news/370539) — _极客公园_ · Manus 即将完成 5 亿美元融资、估值翻倍至 40 亿美元，为撤销 Meta 收购交易后首轮，现有投资方含腾讯、红杉中国、真格基金；地瓜机器人完成 4 亿美元 C 轮，未来资产领投、资方近 30 家，距上轮仅 5 个月，今年累计融资近 50 亿元人民币，发力点为 560 TOPS 旭日 S600 芯片与全链路软件平台。
- [The AI Employee for Banks](https://www.youtube.com/watch?v=UKwpr_Trvns) — _Y Combinator_ · Kastle 为银行打造 AI 员工，自动化抵押贷款服务、消费信贷等后台运营，已服务前 25 大抵押贷款服务商中的 10 家、处理超 20 亿美元交易，完成 2400 万美元 A 轮。
- [Building the Safety Layer for AI Agents](https://www.youtube.com/watch?v=5XO7ZEOGpJc) — _Y Combinator_ · Raindrop 为 AI agent 构建安全层，检测生产环境中的失败工具调用与幻觉，客户含 Vercel、Clay、Framer、Speak，完成 A 轮后总融资达 5000 万美元。
- [OpenAI、Anthropic、谷歌联手研究 AI 安全…](http://www.geekpark.net/news/370375) — _极客公园_ · 字节跳动 2026 上半年净利润同比下降、净利率降至约 16.7%（2023 年为 26%、2024 年为 21%），营收同比增 30%、海外收入占比创新高；公司近期从银行获得约 300 亿美元贷款，为史上最大规模。阿里寻求配股募资约 100 亿美元用于 AI 基建，智谱 AI 启动 50 亿美元股权及可转债发行。

### ⚖️ 政策 & 地缘 / Policy & Geopolitics

**为什么本周值得看**: 本周监管辩论出现罕见反转——AI 实验室领袖集体呼吁监管甚至寻求反垄断豁免，而美国政府明确不感兴趣，副总统万斯称之为「特洛伊木马」。同时「pacing the frontier」成为学界与产业界争论焦点。

- [Following: The government doesn't want to regulate AI](https://www.platformer.news/trump-johnson-ai-safety-regulation/) — _Platformer_ · AI 实验室领袖一致认为美国需要尽快行动，但总统与众议长均无兴趣推动 AI 安全立法。
- [Pacing the Frontier, AI's Digital Limits, AI Commissars](https://stratechery.com/2026/pacing-the-frontier-ais-digital-limits-ai-commissars/) — _Stratechery_ · Ben Thompson 批评 Dario Amodei 的 pacing the frontier 提案不切实际，认为其本质指向对 AI 的政治控制。
- [iOS 27、MacOS 27 正式发布…](http://www.geekpark.net/news/370306) — _极客公园_ · 特朗普发文称 AI 唯一需要的「护栏」就是一位强悍聪明的总统，措辞较上周末承认需要监管明显强硬；白宫内部形成两派（贝森特、Cairncross 支持更强保护 vs. Kratsios、Sacks 认为监管扼杀创新），副总统万斯称前沿 AI 公司主动求监管「有点像特洛伊木马」；中国外交部回应 Anthropic 限制论，反对以遏制手段干预 AI 发展。
- [Does AI need an antitrust exemption so it doesn't kill everyone????](https://www.youtube.com/watch?v=6oo0ZrojX-I) — _Decoder_ · 前 DOJ 反垄断主管 Jonathan Kanter 深入讨论 AI 安全监管如何与反垄断法、竞争政策及对华关系相互作用。
- [ModelTalk: Pacing the Frontier](https://www.chinatalk.media/p/modeltalk-pacing-the-frontier) — _ChinaTalk_ · 圆桌讨论为何 Hugging Face 被黑事件比多年「灭绝论」更能破圈、METR 的信任垄断与 CAISI 的 1000 万美元、以及智谱与月之暗面继续加速、军事机密经代理路由泄漏进 Claude 等问题。
- [The Balance of AI Power: Anton Leicht on Politics, Pacing Deals, and Muddling Through Well](https://www.youtube.com/watch?v=rdEn9cpMScA) — _The Cognitive Revolution_ · 卡内基学者 Leicht 讨论前沿训练暂停的战略权衡、行业自律障碍，以及中等强国如何用数据中心容量与半导体筹码换取模型访问权，强调防止私人实验室或单一政府垄断控制与防范灾难性风险同等重要。
- [Microsoft AI CEO says AI threats are real, and Anthropic is making it worse](https://www.youtube.com/watch?v=T7VOrTLMg74) — _Decoder_ · Mustafa Suleyman 谈 alignment 是否失效、Hugging Face 事件、行业标准推行，并批评 Anthropic 与模型福利议题。

### 📈 VC & 市场观点 / VC & Market Perspectives

**为什么本周值得看**: 本周市场观点集中在一个判断上——AI 的价值捕获正在从模型层向应用层与信任基建层迁移，而 Agent 交易的身份、授权与责任问题成为新的商业机会窗口。

- [外滩大会线下圆桌｜敢把钱包交给 AI 吗？](https://sv101.fireside.fm/265) — _硅谷101_ · 蚂蚁 CEO 韩歆毅、万事达首席产品官 Jorn Lambert、OPPO 刘作虎、阿里首席科学家周靖人同台，讨论 Agent 交易的两条线（Agent 帮人完成任务 vs. Agent-to-Agent 支付）及授权、身份、KYA、资金安全与可追溯等信任基建，并展望 800 亿 Agent 的商业想象。
- [The Overhang](https://www.oneusefulthing.org/p/the-overhang) — _One Useful Thing_ · Ethan Mollick 认为 AI 风险担忧与他自己更新太慢的问题同源：人类制度与流程的运转速度跟不上 AI 发展速度，只关注未来 AI 会忽略当下已发生的现实。
- [助听器躺赚三十年暴利，被 AI 打破了](http://www.geekpark.net/news/370445) — _极客公园_ · 深圳听象科技旗下昂听一年内用户超 5 万、做到美国亚马逊助听器类目 Top1、年销超 1500 万美元、份额从 1% 增至 18%；飞声开放式 AI 助听器在日本众筹超 300 万美元创类目纪录，AI 音频分离把价格打到五大外资巨头（索诺瓦、Demant、WS 听力、瑞声达、斯达克）的十分之一。

## 📚 长读 / Long Reads (周末再看)

- [外滩大会线下圆桌｜敢把钱包交给 AI 吗？](https://sv101.fireside.fm/265) — _硅谷101_ · 蚂蚁、万事达、OPPO、阿里四方同台拆解 Agent 支付的身份与授权基建，是理解「Agent 成为交易主体」最完整的一手讨论。~36 min listen
- [The Balance of AI Power: Anton Leicht](https://www.youtube.com/watch?v=rdEn9cpMScA) — _The Cognitive Revolution_ · 从地缘政治视角看中等强国如何用算力与芯片换取模型访问权，框架清晰、可迁移。~60 min listen
- [ModelTalk: Pacing the Frontier](https://www.chinatalk.media/p/modeltalk-pacing-the-frontier) — _ChinaTalk_ · 一周内 Dario 呼吁放缓与特朗普称之为阴谋的完整复盘，含 METR/CAISI 监管信任之争与中国侧动向。~45 min listen
- [Box's Aaron Levie: On Reinventing Yourself in the AI Age](https://www.youtube.com/watch?v=NE4CLThMPGU) — _Sequoia Capital_ · 上市公司如何在季度财报压力下完成 AI 转型，以及为什么 token 补贴不可持续。~40 min listen
- [助听器躺赚三十年暴利，被 AI 打破了](http://www.geekpark.net/news/370445) — _极客公园_ · 一个被五家外资垄断二十年的市场如何被 AI 音频分离从技术关卡和定价逻辑两端同时拆解。~12 min read

## 📊 本周观察

本周最清晰的跨领域信号是 **Agent 从「能对话」转向「能办事」，而瓶颈从模型能力转移到了信任基建**。蚂蚁 APASS、万事达机器间支付网络、努比亚 AI 智能体手机、Claude 合并 Cowork 都在同一周落地，指向同一个问题：当 Agent 开始替人花钱，身份、授权与责任如何被验证。与此同时，中国大厂在办公场景的 Agent 会战说明，真正的护城河可能不在模型，而在企业长期积累的组织上下文与权限体系——这也解释了为什么 Salesforce 主动放弃 UI 护城河、Box 押注紧贴自身文件系统的 harness。

## 🗑️ 已分流 / 过滤

本周过滤掉 76 条噪声内容；另有 23 条技术类内容已分流至技术报告。
