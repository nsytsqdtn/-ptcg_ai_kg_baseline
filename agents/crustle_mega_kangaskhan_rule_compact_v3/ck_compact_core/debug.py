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


def _candidate_record(c):
    return {
        "source": c.source_slot,
        "pokemon_zh": c.source_name_zh,
        "attack": c.attack_name,
        "timing": c.timing,
        "confidence": c.confidence,
        "effective_damage_to_active": c.effective_damage_to_active,
        "bench_damage": c.bench_damage,
        "ko_active": c.can_ko_active,
        "ko_core_bench_now": c.can_ko_core_bench_now,
        "ko_core_bench_two_turn": c.can_ko_core_bench_two_turn,
        "blocked_by_crustle": c.blocked_by_crustle,
        "bypass": list(c.bypass_reasons),
        "severity": round(c.severity, 1),
    }


def write_debug(path: Path, obs, state, setup, tempo, prize, selected_plan: str, scored, selected: list[int]) -> None:
    if not debug_enabled():
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        threat = state.opponent_threat
        rec = {
            "turn": state.turn,
            "phase": state.phase,
            "context": state.context_name,
            "selected_plan": selected_plan,
            "board": {
                "active_zh": state.active_view.name_zh if state.active_view else None,
                "active_hp": state.active_view.hp if state.active_view else None,
                "field_count": state.field_count,
                "deck_count": state.my_deck_count,
                "safe_draws": state.safe_draws,
                "prizes_left": state.my_prizes_left,
            },
            "zone_knowledge": getattr(state.deck_knowledge, "debug_snapshot", lambda: {})(),
            "opponent_threat": {
                "summary": threat.summary,
                "main": _candidate_record(threat.main) if threat.main else None,
                "immediate_prize_threat": threat.immediate_prize_threat,
                "next_turn_prize_threat": threat.next_turn_prize_threat,
                "bench_damage_pressure": threat.bench_damage_pressure,
                "two_turn_bench_pressure": threat.two_turn_bench_pressure,
                "gust_prize_pressure": threat.gust_prize_pressure,
                "non_ex_wall_breaker_ready": threat.non_ex_wall_breaker_ready,
                "active_damage_blocked_by_crustle": threat.active_damage_blocked_by_crustle,
                "defense_buys_tempo": threat.defense_buys_tempo,
                "recommended_defense": threat.recommended_defense,
                "reasons": list(threat.reasons),
                "candidates": [_candidate_record(c) for c in threat.candidates[:6]],
            },
            "setup": {
                "need_backup": setup.need_backup,
                "need_dwebble": setup.need_dwebble,
                "need_crustle": setup.need_crustle,
                "need_crustle_active": setup.need_crustle_active,
                "need_energy_for_crustle": setup.need_energy_for_crustle,
                "allow_ascension": setup.allow_ascension,
                "priority_cards_zh": [get_card_name_zh(cid) for cid in setup.priority_cards],
                "reason": setup.reason,
            },
            "tempo": {
                "available": tempo.available,
                "source": tempo.source,
                "payoff": tempo.payoff,
                "urgency": tempo.urgency,
                "buys_turns": tempo.buys_turns,
                "reason": tempo.reason,
                "priority_cards_zh": [get_card_name_zh(cid) for cid in tempo.priority_cards],
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
                "breaks_defense": prize.breaks_defense,
                "wins_game": prize.wins_game,
                "reason": prize.reason,
                "pressure_available": prize.pressure_available,
                "pressure_damage": prize.pressure_damage,
                "pressure_need_energy": prize.pressure_need_energy,
                "pressure_reason": prize.pressure_reason,
            },
            "top_actions": [
                {**action_label(obs, item.index), "score": item.score, "tags": sorted(item.action.tags), "reasons": item.reasons[:10]}
                for item in (scored or [])[:10]
            ],
            "selected": [action_label(obs, i) for i in selected],
        }
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        return
