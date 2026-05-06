"""weekly_paper · 论文 / frontier lab blog / 模型技术报告自动周报。

姊妹模块 weekly_report 覆盖新闻 / 访谈 / 产业内容；weekly_paper 聚焦：
- HuggingFace papers 每周精选
- dair_ai (Elvis Saravia) 每周 ML 新闻
- 一线 lab 官方 blog（DeepMind / Anthropic / OpenAI / Allen AI / 各开源 lab）
- (后续) GitHub key repo releases / arxiv categories / alphaxiv

Pipeline 与 weekly_report 完全一致（ingest → filter → synth），共享 storage、items、
llm、ingest/rss 等基础设施。filter / synthesize 阶段使用本模块自己的 prompt：

- filter.md: 把每条 item 分类到 7 个 topic 之一（agent-harness / agent-rl /
  image-generation / video-generation / vla-embodied / vlm-llm-posttrain /
  world-model）或 noise。
- synthesize.md: 按 topic 分区，生成一份 paper-focused 周报。
"""
