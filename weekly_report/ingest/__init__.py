"""Ingest adapters: each adapter takes a Source and yields Item dicts.

Currently:
- rss.py:    direct RSS / Atom feeds (incl. YouTube channel RSS)
- (later) podcast.py: rss + Whisper transcription
- (later) x.py:       X via RSSHub / Nitter

All adapters share the Item schema in items.py.
"""
