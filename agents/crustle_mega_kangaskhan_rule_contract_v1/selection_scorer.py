from __future__ import annotations

from runtime import CORE_POKEMON, CardIds, prize_count


PETREL_TARGETS_BY_PLAN = {
    "close_game": {CardIds.BOSS_ORDERS, CardIds.LISIA},
    "prevent_loss": {CardIds.JUMBO_ICE_CREAM, CardIds.BIANCA_DEVOTION, CardIds.SWITCH},
    "survival_setup": {CardIds.BUDDY_BUDDY_POFFIN, CardIds.HILDA, CardIds.ULTRA_BALL},
    "setup_crustle_wall_now": {CardIds.HILDA, CardIds.BUDDY_BUDDY_POFFIN, CardIds.ULTRA_BALL, CardIds.SWITCH},
    "wall_and_tax": {CardIds.ERI, CardIds.XEROSIC, CardIds.HAND_TRIMMER, CardIds.HANDHELD_FAN},
    "protect_bench_vs_dragapult": {CardIds.HILDA, CardIds.POKEGEAR, CardIds.SWITCH},
    "setup_crustle": {CardIds.HILDA, CardIds.BUDDY_BUDDY_POFFIN, CardIds.ULTRA_BALL},
    "setup_kangaskhan": {CardIds.LILLIE, CardIds.HILDA, CardIds.ULTRA_BALL},
    "tank_and_heal": {CardIds.JUMBO_ICE_CREAM, CardIds.BIANCA_DEVOTION, CardIds.HERO_CAPE, CardIds.COMMUNITY_CENTER},
    "disruption_loop": {CardIds.ERI, CardIds.XEROSIC, CardIds.HAND_TRIMMER, CardIds.HANDHELD_FAN},
}


def _petrel_has_good_target(primary_plan: str, hand_ids: set[int], discard_ids: set[int]) -> bool:
    targets = PETREL_TARGETS_BY_PLAN.get(primary_plan, set())
    if not targets:
        return False
    return any(card_id not in hand_ids and card_id not in discard_ids for card_id in targets)


def score_petrel_play(deck_state, state, hand_ids: set[int] | None = None, discard_ids: set[int] | None = None) -> tuple[float, str | None]:
    if getattr(state, "supporterPlayed", False):
        return -100.0, "supporter_already_used"

    primary_plan = getattr(deck_state, "primary_plan", "stabilize")
    if (
        getattr(deck_state, "must_bench_basic", False)
        and getattr(deck_state, "setup_missing_crustle", False)
        and getattr(getattr(deck_state, "matchup", None), "prefers_crustle_wall", False)
    ):
        primary_plan = "setup_crustle"

    if not _petrel_has_good_target(primary_plan, set(hand_ids or set()), set(discard_ids or set())):
        return -140.0, "petrel_no_clear_target"

    if primary_plan == "close_game":
        return 125.0, "petrel_close_game"
    if primary_plan == "prevent_loss":
        return 125.0, "petrel_prevent_loss"
    if primary_plan in {"survival_setup", "setup_crustle_wall_now"}:
        return 125.0, "petrel_key_plan_target"
    if primary_plan == "setup_crustle":
        return 106.0, "petrel_setup_crustle"
    if primary_plan == "setup_kangaskhan":
        return 92.0, "petrel_setup_kang"
    if primary_plan in {"wall_and_tax", "disruption_loop"}:
        return 80.0, "petrel_disruption_target"
    if primary_plan == "protect_bench_vs_dragapult":
        return 72.0, "petrel_bench_protect"
    return 45.0, "petrel_medium"


def score_petrel_target(card_id: int, deck_state) -> tuple[float, str | None]:
    if getattr(deck_state, "must_bench_basic", False) or deck_state.primary_plan == "survival_setup":
        if card_id in {CardIds.BUDDY_BUDDY_POFFIN, CardIds.HILDA, CardIds.ULTRA_BALL}:
            return 118.0, "petrel_survival_setup"
    if deck_state.primary_plan == "close_game":
        if card_id in {CardIds.BOSS_ORDERS, CardIds.LISIA}:
            return 110.0, "petrel_close_game"
    if deck_state.primary_plan == "prevent_loss":
        if card_id in {CardIds.JUMBO_ICE_CREAM, CardIds.BIANCA_DEVOTION, CardIds.SWITCH}:
            return 100.0, "petrel_prevent_loss"
    if deck_state.primary_plan == "wall_and_tax":
        if card_id in {CardIds.ERI, CardIds.XEROSIC, CardIds.HAND_TRIMMER, CardIds.HANDHELD_FAN}:
            return 95.0, "petrel_wall_tax"
    if deck_state.primary_plan == "setup_crustle":
        if card_id in {CardIds.HILDA, CardIds.BUDDY_BUDDY_POFFIN, CardIds.ULTRA_BALL}:
            return 96.0, "petrel_setup_crustle"
    if deck_state.primary_plan == "setup_kangaskhan":
        if card_id in {CardIds.HILDA, CardIds.LILLIE, CardIds.ULTRA_BALL}:
            return 90.0, "petrel_setup_kang"
    return 40.0, None


def score_hilda_target(
    card_id: int,
    deck_state,
    matchup,
    paired_card_id: int | None = None,
    candidate_ids: set[int] | None = None,
) -> tuple[float, str | None]:
    if paired_card_id == CardIds.CRUSTLE and card_id == CardIds.GROW_GRASS_ENERGY:
        return 118.0, "hilda_pair_crustle_grow_grass"
    if paired_card_id == CardIds.DWEBBLE and matchup.values_mist_energy and card_id == CardIds.MIST_ENERGY:
        return 116.0, "hilda_pair_dwebble_mist"
    if paired_card_id == CardIds.MEGA_KANGASKHAN_EX and card_id == CardIds.SPIKY_ENERGY:
        return 112.0, "hilda_pair_kang_spiky"
    candidate_ids = set(candidate_ids or set())
    if card_id in {CardIds.CRUSTLE, CardIds.GROW_GRASS_ENERGY} and {CardIds.CRUSTLE, CardIds.GROW_GRASS_ENERGY}.issubset(candidate_ids):
        return 145.0, "hilda_complete_crustle_grow"
    if matchup.name == "dragapult_ex" and card_id in {CardIds.DWEBBLE, CardIds.CRUSTLE, CardIds.MIST_ENERGY}:
        if CardIds.MIST_ENERGY in candidate_ids and ({CardIds.DWEBBLE, CardIds.CRUSTLE} & candidate_ids):
            return 142.0, "hilda_mist_combo"
    if card_id == CardIds.CRUSTLE and (deck_state.primary_plan in {"setup_crustle", "wall_and_tax"}):
        return 105.0, "hilda_crustle"
    if card_id == CardIds.DWEBBLE and deck_state.setup_missing_crustle:
        return 95.0, "hilda_dwebble"
    if card_id == CardIds.MEGA_KANGASKHAN_EX and deck_state.primary_plan in {"setup_kangaskhan", "tank_and_heal"}:
        return 90.0, "hilda_kang"
    if card_id == CardIds.GROW_GRASS_ENERGY and deck_state.primary_plan in {"setup_crustle", "wall_and_tax"}:
        return 92.0, "hilda_grow_grass"
    if card_id == CardIds.MIST_ENERGY and matchup.values_mist_energy:
        return 88.0, "hilda_mist"
    if card_id == CardIds.SPIKY_ENERGY and deck_state.primary_plan == "tank_and_heal":
        return 86.0, "hilda_spiky"
    if card_id == CardIds.BASIC_GRASS:
        return 72.0, "hilda_basic_grass"
    if matchup.name == "unknown" and card_id in {CardIds.DWEBBLE, CardIds.MEGA_KANGASKHAN_EX, CardIds.LILLIE}:
        return 70.0, "hilda_unknown_stable"
    return 35.0, None


def infer_pair_card_id(looking_cards) -> int | None:
    for card in looking_cards or []:
        if card is None:
            continue
        if getattr(card, "id", None) in CORE_POKEMON:
            return card.id
    return None


def score_poffin_target(card_id: int, deck_state, matchup) -> tuple[float, str | None]:
    if getattr(deck_state, "must_bench_basic", False):
        if card_id == CardIds.DWEBBLE:
            return 140.0, "poffin_must_bench_dwebble"
        if card_id == CardIds.MEGA_KANGASKHAN_EX:
            return 125.0, "poffin_must_bench_kang"
    if card_id == CardIds.DWEBBLE:
        if deck_state.primary_plan in {"setup_crustle", "wall_and_tax"} or matchup.prefers_crustle_wall:
            return 104.0, "poffin_dwebble"
        return 78.0, "poffin_dwebble_fallback"
    if card_id == CardIds.MEGA_KANGASKHAN_EX:
        if deck_state.primary_plan in {"setup_kangaskhan", "stabilize"}:
            return 82.0, "poffin_kang"
        return 46.0, "poffin_kang_fallback"
    return 18.0, None


def score_ultra_ball_discard(card_id: int, deck_state) -> tuple[float, str | None]:
    protected = {
        CardIds.HERO_CAPE,
        CardIds.BIANCA_DEVOTION,
        CardIds.XEROSIC,
        CardIds.LISIA,
        CardIds.HAND_TRIMMER,
        CardIds.HANDHELD_FAN,
    }
    if card_id in protected:
        return -120.0, "protect_one_of"
    if card_id == CardIds.DWEBBLE and deck_state.setup_missing_crustle:
        return -110.0, "protect_dwebble"
    if card_id == CardIds.CRUSTLE and deck_state.crustle_in_play == 0:
        return -110.0, "protect_crustle"
    if card_id == CardIds.MEGA_KANGASKHAN_EX and deck_state.kangaskhan_in_play == 0:
        return -100.0, "protect_kang"
    if (
        card_id == CardIds.MIST_ENERGY
        and getattr(getattr(deck_state, "matchup", None), "values_mist_energy", False)
    ):
        return -90.0, "protect_mist"
    if card_id == CardIds.BASIC_GRASS:
        return 20.0, "discard_basic_grass"
    return 5.0, None


def score_gust_target(card, deck_state) -> tuple[float, str | None]:
    if card is None:
        return 0.0, None
    hp = getattr(card, "hp", 999)
    current_attack_damage = getattr(deck_state, "current_attack_damage", 0)
    can_ko = current_attack_damage >= hp > 0
    if deck_state.gust_for_win and can_ko and prize_count(card) >= getattr(deck_state, "my_prizes_left", 99):
        return 120.0, "gust_for_win"
    if (
        getattr(getattr(deck_state, "matchup", None), "values_gust_on_setup_targets", False)
        and prize_count(card) == 1
        and hp <= 70
        and len(getattr(card, "energies", []) or []) == 0
    ):
        return 96.0, "gust_setup_basic"
    if can_ko and hp <= 120:
        return 90.0, "gust_low_hp"
    if can_ko and prize_count(card) >= 2:
        return 85.0, "gust_multi_prize"
    if len(getattr(card, "energies", []) or []) == 0:
        return 65.0, "gust_stall"
    return 20.0, None


def score_switch_target(card_id: int, deck_state) -> tuple[float, str | None]:
    if deck_state.primary_plan == "wall_and_tax" and card_id == CardIds.CRUSTLE:
        return 120.0, "switch_crustle_wall"
    if deck_state.primary_plan in {"tank_and_heal", "setup_kangaskhan"} and card_id == CardIds.MEGA_KANGASKHAN_EX:
        return 105.0, "switch_kang"
    if deck_state.primary_plan == "setup_crustle" and card_id == CardIds.DWEBBLE:
        return 70.0, "switch_dwebble"
    return 20.0, None
