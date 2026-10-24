"""Live AI commentator: a deterministic, per-viewer-mode timeline of short spoken lines.

  data.py     loads an exported match (match/events/stats/moments/insights.json) + the fictional league
  phrases.py  template pools per language x kind x tone (no numbers in templates: every number comes from code)
  engine.py   candidates from events, key moments, Sliding Doors insights and live stats -> non-overlapping timeline
  speech.py   Azure AI Speech (REST) voice/prosody per mode, audio keys, rate-limited synthesis + disk cache

No LLM runs here, ever. The API (app.api.commentary) serves the timeline and synthesizes audio on demand.
"""
