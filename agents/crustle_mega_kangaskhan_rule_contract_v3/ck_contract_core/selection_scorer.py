from __future__ import annotations

from .runtime import CardIds, ENERGY_IDS, prize_count, energy_count


def score_poffin_target(card_id: int, deck_state) -> tuple[float, str]:
    if card_id == CardIds.DWEBBLE:
        return (320.0 if deck_state.dwebble_in_play == 0 else 160.0), "poffin_dwebble"
    if card_id == CardIds.MEGA_KANGASKHAN_EX:
        return (300.0 if deck_state.kangaskhan_in_play == 0 else 130.0), "poffin_kang"
    return -100.0, "poffin_off_plan"


def score_petrel_target(card_id: int, deck_state) -> tuple[float, str]:
    objective = deck_state.objective
    if objective == "setup_backup" and card_id in {CardIds.BUDDY_BUDDY_POFFIN, CardIds.HILDA, CardIds.ULTRA_BALL, CardIds.POKEGEAR}:
        return 400.0, "petrel_backup_route"
    if objective == "setup_crustle_wall" and card_id in {CardIds.HILDA, CardIds.BUDDY_BUDDY_POFFIN, CardIds.ULTRA_BALL, CardIds.SWITCH}:
        return 360.0, "petrel_wall_route"
    if objective in {"wall_control", "resource_lock"} and card_id in {CardIds.ERI, CardIds.XEROSIC, CardIds.HAND_TRIMMER, CardIds.HANDHELD_FAN, CardIds.JUMBO_ICE_CREAM, CardIds.BOSS_ORDERS}:
        return 420.0, "petrel_control_route"
    if objective in {"finish", "pressure_prize"} and card_id in {CardIds.BOSS_ORDERS, CardIds.LISIA, CardIds.PETREL}:
        return 500.0, "petrel_prize_route"
    return -80.0, "petrel_low_value"


def score_hilda_target(card_id: int, deck_state, matchup=None, candidate_ids: set[int] | None = None) -> tuple[float, str]:
    objective = deck_state.objective
    if card_id == CardIds.CRUSTLE:
        return (420.0 if objective in {"setup_crustle_wall", "wall_control", "protect_bench_core"} else 160.0), "hilda_crustle"
    if card_id == CardIds.DWEBBLE:
        return (380.0 if deck_state.dwebble_in_play == 0 else 180.0), "hilda_dwebble"
    if card_id == CardIds.MEGA_KANGASKHAN_EX:
        return (330.0 if deck_state.kangaskhan_in_play == 0 else 160.0), "hilda_kang"
    if card_id == CardIds.MIST_ENERGY:
        return (430.0 if objective == "protect_bench_core" or getattr(matchup, "values_mist_energy", False) else 180.0), "hilda_mist"
    if card_id == CardIds.GROW_GRASS_ENERGY:
        return (390.0 if objective == "setup_crustle_wall" else 170.0), "hilda_growing_grass"
    if card_id == CardIds.SPIKY_ENERGY:
        return (330.0 if objective in {"wall_control", "kang_engine"} else 150.0), "hilda_spiky"
    if card_id == CardIds.BASIC_GRASS:
        return 150.0, "hilda_basic_grass"
    return -40.0, "hilda_low_value"


def score_ultra_ball_discard(card_id: int, deck_state) -> tuple[float, str]:
    if card_id in {CardIds.CRUSTLE, CardIds.DWEBBLE, CardIds.MEGA_KANGASKHAN_EX}:
        return -500.0, "protect_core_pokemon"
    if card_id in {CardIds.MIST_ENERGY, CardIds.GROW_GRASS_ENERGY, CardIds.SPIKY_ENERGY}:
        return -220.0, "protect_special_energy"
    if card_id == CardIds.BASIC_GRASS:
        return -60.0, "basic_energy_discardable_if_forced"
    if card_id in {CardIds.LILLIE, CardIds.COMMUNITY_CENTER, CardIds.FESTIVAL_GROUNDS}:
        return 120.0, "discard_lower_priority_resource"
    return 20.0, "discard_generic"


def score_gust_target(pokemon, deck_state) -> tuple[float, str]:
    if pokemon is None:
        return 0.0, "no_target"
    prizes = prize_count(pokemon)
    hp = getattr(pokemon, "hp", 999)
    can_ko = deck_state.current_attack_damage >= hp > 0
    has_bench_spread = bool(getattr(getattr(deck_state.matchup, "threat", None), "has_bench_spread", False))
    if can_ko and prizes >= deck_state.my_prizes_left:
        return 1000.0, "gust_win"
    if has_bench_spread and can_ko and hp <= 130:
        return 920.0 + prizes * 90.0, "gust_ko_spread_setup_or_low_hp"
    if can_ko:
        return 600.0 + prizes * 80.0, "gust_prize"
    if has_bench_spread and hp <= 130:
        return 360.0, "gust_pressure_spread_setup_or_low_hp"
    if energy_count(pokemon) == 0 and hp > 120:
        return 180.0, "gust_stall"
    return 40.0, "gust_low_value"


def score_switch_target(card_id: int, deck_state) -> tuple[float, str]:
    if card_id == CardIds.CRUSTLE:
        return (700.0 if deck_state.objective in {"setup_crustle_wall", "wall_control", "protect_bench_core"} else 260.0), "switch_crustle"
    if card_id == CardIds.MEGA_KANGASKHAN_EX:
        return (520.0 if deck_state.objective == "kang_engine" else 180.0), "switch_kang"
    if card_id == CardIds.DWEBBLE:
        return 80.0, "switch_dwebble"
    return 10.0, "switch_other"
