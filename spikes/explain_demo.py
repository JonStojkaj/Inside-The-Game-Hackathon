"""Run the explain team on every key moment of a match and write insights.json.

  LLM_PROVIDER=azure backend/.venv/bin/python spikes/explain_demo.py spikes/grf/out/matches/full-34 data/insights/full-34.json
  LLM_PROVIDER=fake  ...   (offline, deterministic)
LLM answers are cached in data/cache/llm/ (LLM_CACHE=replay reuses them without calling the model).
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from app.agents.explain import ExplainTeam, fake_explain_llm  # noqa: E402
from app.agents.llm import CachedLLM, llm_from_env  # noqa: E402
from app.source.events import derive_events  # noqa: E402
from app.source.grf import load_grf_match  # noqa: E402
from app.stats.moments import detect_moments  # noqa: E402


def main() -> None:
    match_dir, out_file = Path(sys.argv[1]), Path(sys.argv[2])
    match = load_grf_match(match_dir)
    events = derive_events(match)
    moments = detect_moments(events, match.clock_s)
    llm = llm_from_env(fake=fake_explain_llm())
    team = ExplainTeam(llm)
    insights = []
    for m in moments:
        started = time.perf_counter()
        insight = team.explain(match, m, events)
        insights.append(insight)
        verdicts = " ".join(h.verdict[0].upper() for h in insight.hypotheses)
        print(f"{int(m.clock_s // 60):2d}' {m.kind:18s} [{verdicts:9s}] {time.perf_counter() - started:5.1f}s  {insight.claim}")
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps([i.model_dump() for i in insights], ensure_ascii=False))
    if isinstance(llm, CachedLLM):
        print(f"\n{llm.name}: {llm.hits} cache hits, {llm.misses} model calls -> {out_file}")


if __name__ == "__main__":
    main()
