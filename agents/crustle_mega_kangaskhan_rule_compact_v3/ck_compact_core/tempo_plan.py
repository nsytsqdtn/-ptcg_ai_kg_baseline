from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .runtime import CardIds


@dataclass(frozen=True)
class TempoPlan:
    available: bool = False
    source: str = "none"                 # crustle_block / opponent_miss / no_tempo
    payoff: str = "none"                 # win_prize / prize / setup / build_attacker / protect_bench / disrupt_energy / disrupt_hand / heal / pressure / stabilize
    urgency: str = "normal"              # emergency / high / normal / low
    buys_turns: int = 0
    reason: str = "none"
    priority_cards: tuple[int, ...] = tuple()
    target_card_id: int | None = None
    attack_pressure_damage: int = 0
    debug: dict[str, Any] = field(default_factory=dict)


def build_tempo_plan(state: Any, setup: Any, prize: Any) -> TempoPlan:
    threat = state.opponent_threat

    # Direct win/prize has its own plan, but tempo still records why it should be cashed.
    if prize.available and prize.confidence == "confirmed" and prize.wins_game:
        return TempoPlan(True, "confirmed_prize", "win_prize", "emergency", 0, "confirmed_win_available", target_card_id=prize.target_card_id)

    if threat.immediate_prize_threat:
        if setup.need_backup:
            return TempoPlan(True, "opponent_threat", "setup", "emergency", 0, "avoid_no_active_under_immediate_threat", priority_cards=tuple(setup.priority_cards))
        if state.active_view is not None and state.active_view.hp <= 100:
            return TempoPlan(True, "opponent_threat", "heal", "high", 0, "active_can_be_ko_heal_if_possible", priority_cards=(CardIds.JUMBO_ICE_CREAM, CardIds.BIANCA_DEVOTION, CardIds.HERO_CAPE))
        if threat.recommended_defense == "protect_bench":
            return TempoPlan(True, "opponent_threat", "protect_bench", "high", 0, "bench_core_under_attack_effect", priority_cards=(CardIds.MIST_ENERGY, CardIds.JUMBO_ICE_CREAM, CardIds.ERI, CardIds.HAND_TRIMMER))
        return TempoPlan(True, "opponent_threat", "disrupt_energy", "high", 0, "reduce_immediate_attack_threat", priority_cards=(CardIds.XEROSIC, CardIds.HANDHELD_FAN, CardIds.BOSS_ORDERS))

    if threat.two_turn_bench_pressure or threat.recommended_defense == "protect_bench":
        return TempoPlan(True, "opponent_pressure", "protect_bench", "high", 0, "two_turn_bench_prize_pressure", priority_cards=(CardIds.MIST_ENERGY, CardIds.JUMBO_ICE_CREAM, CardIds.ERI, CardIds.HAND_TRIMMER))

    if threat.gust_prize_pressure:
        return TempoPlan(True, "opponent_pressure", "disrupt_hand", "high", 0, "opponent_hand_can_convert_gust_prize", priority_cards=(CardIds.ERI, CardIds.HAND_TRIMMER, CardIds.XEROSIC))

    if threat.non_ex_wall_breaker_ready:
        # Against non-ex wall breakers, cash tempo into KO/gust pressure if possible; otherwise disrupt.
        if prize.available and prize.confidence == "confirmed":
            return TempoPlan(True, "non_ex_breaker", "prize", "high", 0, "confirmed_prize_against_wall_breaker", target_card_id=prize.target_card_id)
        return TempoPlan(True, "non_ex_breaker", "disrupt_energy", "high", 0, "non_ex_attacker_can_break_crustle", priority_cards=(CardIds.BOSS_ORDERS, CardIds.XEROSIC, CardIds.HANDHELD_FAN))

    if threat.defense_buys_tempo:
        # This is the key v3 behavior: the wall creates one turn, then we cash it.
        if prize.available and prize.confidence == "confirmed" and not prize.breaks_defense:
            return TempoPlan(True, "crustle_block", "prize", "high", threat.expected_delay_turns, "cash_crustle_block_into_prize", target_card_id=prize.target_card_id)
        if setup.need_crustle or setup.need_energy_for_crustle or setup.need_backup:
            return TempoPlan(True, "crustle_block", "setup", "normal", threat.expected_delay_turns, "use_blocked_turn_to_finish_board", priority_cards=tuple(setup.priority_cards))
        if state.has_kang and not state.kang_attack_ready:
            return TempoPlan(True, "crustle_block", "build_attacker", "normal", threat.expected_delay_turns, "use_blocked_turn_to_prepare_kang", priority_cards=(CardIds.GROW_GRASS_ENERGY, CardIds.SPIKY_ENERGY, CardIds.MIST_ENERGY, CardIds.HILDA))
        if prize.pressure_available:
            return TempoPlan(True, "crustle_block", "pressure", "normal", threat.expected_delay_turns, "use_blocked_turn_to_create_two_turn_ko", target_card_id=prize.pressure_target_card_id, attack_pressure_damage=prize.pressure_damage)
        return TempoPlan(True, "crustle_block", "disrupt_hand", "normal", threat.expected_delay_turns, "no_clean_payoff_disrupt_hand", priority_cards=(CardIds.ERI, CardIds.HAND_TRIMMER, CardIds.PETREL))

    if prize.available and prize.confidence == "confirmed":
        return TempoPlan(True, "neutral", "prize", "normal", 0, "confirmed_prize_without_defense_window", target_card_id=prize.target_card_id)

    if setup.need_backup or setup.need_crustle:
        return TempoPlan(True, "neutral", "setup", "normal", 0, "board_not_established", priority_cards=tuple(setup.priority_cards))

    if prize.pressure_available:
        return TempoPlan(True, "neutral", "pressure", "low", 0, "no_prize_use_pressure", target_card_id=prize.pressure_target_card_id, attack_pressure_damage=prize.pressure_damage)

    return TempoPlan(False, "none", "stabilize", "low", 0, "no_immediate_plan", priority_cards=(CardIds.PETREL, CardIds.POKEGEAR, CardIds.LILLIE))
