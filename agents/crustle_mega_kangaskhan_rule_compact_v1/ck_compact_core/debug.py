from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .runtime import get_card_name_en, get_card_name_zh


def debug_enabled() -> bool:
    return os.environ.get("RULE_DEBUG") == "1" or os.environ.get("COMPACT_DEBUG") == "1"


def action_label(obs: Any, idx: int) -> dict[str, Any]:
    try:
        option = obs.select.option[idx]
        kind = str(getattr(option, "type", "UNKNOWN")).split(".")[-1]
        rec: dict[str, Any] = {"index": idx, "kind": kind}
        card = None
        if hasattr(option, "index"):
            try:
                from .actions import get_card_for_option
                card = get_card_for_option(obs, option)
            except Exception:
                card = None
        if card is not None:
            rec["card_en"] = get_card_name_en(card)
            rec["card_zh"] = get_card_name_zh(card)
            rec["card_id"] = getattr(card, "id", None)
        return rec
    except Exception:
        return {"index": idx}


def write_debug(path: Path, obs, state, setup, wall, prize, selected_plan: str, scored, selected: list[int]) -> None:
    if not debug_enabled():
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        rec = {
            "turn": state.turn,
            "phase": state.phase,
            "context": state.context_name,
            "wall_status": state.wall_status,
            "active_under_threat": state.active_under_threat,
            "active_threat_damage_estimate": state.active_threat_damage_estimate,
            "wall_leak_reasons": state.wall_leak_reasons,
            "selected_plan": selected_plan,
            "setup": {
                "need_backup": setup.need_backup,
                "need_dwebble": setup.need_dwebble,
                "need_crustle": setup.need_crustle,
                "need_crustle_active": setup.need_crustle_active,
                "need_energy_for_crustle": setup.need_energy_for_crustle,
                "allow_ascension": setup.allow_ascension,
                "reason": setup.reason,
            },
            "wall": {
                "status": wall.status,
                "preferred_response": wall.preferred_response,
                "opponent_wallable": wall.opponent_wallable,
                "need_heal_wall": wall.need_heal_wall,
                "need_heal_kang": wall.need_heal_kang,
                "need_protect_core": wall.need_protect_core,
                "need_stop_energy": wall.need_stop_energy,
                "need_stop_hand": wall.need_stop_hand,
                "reason": wall.reason,
                "leak_reasons": wall.leak_reasons,
            },
            "prize": {
                "available": prize.available,
                "confidence": prize.confidence,
                "attacker": prize.attacker_name,
                "target": prize.target_name,
                "damage": prize.damage,
                "prize_gain": prize.prize_gain,
                "route": prize.route,
                "need_switch": prize.need_switch,
                "need_energy": prize.need_energy,
                "breaks_wall": prize.breaks_wall,
                "wins_game": prize.wins_game,
                "reason": prize.reason,
                "pressure_available": prize.pressure_available,
                "pressure_damage": prize.pressure_damage,
                "pressure_need_energy": prize.pressure_need_energy,
                "pressure_reason": prize.pressure_reason,
            },
            "top_actions": [
                {
                    **action_label(obs, item.index),
                    "score": item.score,
                    "tags": sorted(item.action.tags),
                    "reasons": item.reasons[:8],
                }
                for item in (scored or [])[:8]
            ],
            "selected": [action_label(obs, i) for i in selected],
        }
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        return
