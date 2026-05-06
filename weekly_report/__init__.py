"""weekly_report — 周期性把 topics/*/sources.json 里的源抓成 JSONL，
后续 stage 再用 LLM 过滤 + 综述成周报。

数据流（pipeline，不是 agentic loop）：
    sources.json → ingest → items/<week>.jsonl
                          ↘ state/sources.json   (last_seen 状态)
                          ↘ state/seen.jsonl     (全局 url 去重)
    items/<week>.jsonl → filter → filtered/<week>.jsonl    (LLM step 1, Step 3)
    filtered → cluster → clusters/<week>.json              (Step 3)
    clusters → synthesize → reports/<week>.md              (LLM step 2, Step 3)

Step 1 (current) 只跑 ingest + 一个无 LLM 的 preview compose，目的是先把
数据流打通，让你看 JSONL/preview md 是不是想要的形态。
"""
