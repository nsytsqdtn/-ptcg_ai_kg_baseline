from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

from runtime import describe_option, get_card_name


DEFAULT_DEBUG_PATH = Path(__file__).resolve().parent / "rule_debug.jsonl"


def _context_name(obs) -> str | None:
    context = getattr(getattr(obs, "select", None), "context", None)
    if context is None:
        return None
    return getattr(context, "name", None) or str(context)


def _snapshot_payload(snapshot) -> dict:
    return {
        "field_count": getattr(snapshot, "field_count", None),
        "bench_space": getattr(snapshot, "bench_space", None),
        "wall_online": getattr(snapshot, "wall_online", False),
        "active_under_ko_threat": getattr(snapshot, "active_under_ko_threat", False),
        "my_prizes_left": getattr(snapshot, "my_prizes_left", None),
        "opponent_prizes_left": getattr(snapshot, "opponent_prizes_left", None),
    }


def log_rule_decision(obs, snapshot, plan, scored, selected, path: Path | None = None) -> None:
    path = path or Path(os.getenv("RULE_DEBUG_PATH", DEFAULT_DEBUG_PATH))
    path.parent.mkdir(parents=True, exist_ok=True)

    state = obs.current
    my_state = state.players[state.yourIndex]
    active = my_state.active[0] if my_state.active else None
    payload = {
        "logged_at": datetime.now(UTC).isoformat(),
        "turn": getattr(state, "turn", None),
        "step": getattr(state, "step", None),
        "context": _context_name(obs),
        "mode": getattr(plan, "mode", None),
        "plan_reason": (getattr(plan, "reasons", None) or [None])[0],
        "snapshot": _snapshot_payload(snapshot),
        "active": get_card_name(active) if active is not None else None,
        "top_actions": [
            {
                "index": item.index,
                "desc": describe_option(obs, obs.select.option[item.index]),
                "score": item.total_logit,
                "tags": item.prior.get("reason_tags", []),
                "breakdown": item.prior.get("breakdown", {}),
            }
            for item in scored[:5]
        ],
        "selected": list(selected),
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
