"""weekly_paper 自定义 ingest 适配器。

标准 RSS / Atom 直接复用 weekly_report.ingest.rss.ingest_source。
hf-papers 等需要 HTML scrape 的源走本目录下的专用模块。
"""
