from __future__ import annotations

from runtime import CORE_POKEMON, CardIds, prize_count


def _plan_mode(deck_state) -> str:
    plan = getattr(deck_state, "turn_plan", None)
    if plan is not None and getattr(plan, "mode", None):
        return plan.mode
    primary = getattr(deck_state, "primary_plan", "stabilize")
    return "finish" if primary == "close_game" else primary


def petrel_targets_for_state(deck_state) -> set[int]:
    mode = _plan_mode(deck_state)
    plan = getattr(deck_state, "turn_plan", None)
    if mode == "finish":
        return {CardIds.BOSS_ORDERS, CardIds.LISIA}
    if mode == "prevent_loss":
        return {CardIds.JUMBO_ICE_CREAM, CardIds.BIANCA_DEVOTION, CardIds.SWITCH, CardIds.BUDDY_BUDDY_POFFIN}
    if mode == "survival_setup":
        return {CardIds.BUDDY_BUDDY_POFFIN, CardIds.HILDA, CardIds.ULTRA_BALL, CardIds.SWITCH}
    if mode in {"setup_crustle", "setup_crustle_wall_now", "protect_bench_vs_dragapult"}:
        return {CardIds.HILDA, CardIds.BUDDY_BUDDY_POFFIN, CardIds.ULTRA_BALL, CardIds.SWITCH}
    if mode in {"wall_and_tax", "disruption_loop", "close_pressure"}:
        return {CardIds.ERI, CardIds.XEROSIC, CardIds.HAND_TRIMMER, CardIds.HANDHELD_FAN, CardIds.BOSS_ORDERS, CardIds.LISIA}
    if mode == "tank_and_heal":
        heal_card = getattr(plan, "heal_card", None)
        targets = {CardIds.HERO_CAPE, CardIds.COMMUNITY_CENTER, CardIds.SWITCH}
        if heal_card is not None:
            targets.add(heal_card)
        else:
            targets |= {CardIds.JUMBO_ICE_CREAM, CardIds.BIANCA_DEVOTION}
        return targets
    if mode in {"kang_engine", "setup_kangaskhan", "attack_continuity"}:
        return {CardIds.HILDA, CardIds.LILLIE, CardIds.ULTRA_BALL, CardIds.JUMBO_ICE_CREAM}
    return set()


def _petrel_has_good_target(primary_plan: str, hand_ids: set[int], discard_ids: set[int]) -> bool:
    targets = petrel_targets_for_state(type("State", (), {"primary_plan": primary_plan})())
    if not targets:
        return False
    return any(card_id not in hand_ids and card_id not in discard_ids for card_id in targets)


def score_petrel_play(deck_state, state, hand_ids: set[int] | None = None, discard_ids: set[int] | None = None) -> tuple[float, str | None]:
    if getattr(state, "supporterPlayed", False):
        return -100.0, "supporter_already_used"

    primary_plan = _plan_mode(deck_state)
    if (
        getattr(deck_state, "must_bench_basic", False)
        and getattr(deck_state, "setup_missing_crustle", False)
        and getattr(getattr(deck_state, "matchup", None), "prefers_crustle_wall", False)
    ):
        primary_plan = "setup_crustle"

    if not _petrel_has_good_target(primary_plan, set(hand_ids or set()), set(discard_ids or set())):
        return -140.0, "petrel_no_clear_target"

    if primary_plan == "finish":
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
    mode = _plan_mode(deck_state)
    plan = getattr(deck_state, "turn_plan", None)
    if getattr(deck_state, "must_bench_basic", False) or mode == "survival_setup":
        if card_id == CardIds.BUDDY_BUDDY_POFFIN:
            return 140.0, "petrel_survival_poffin"
        if card_id == CardIds.ULTRA_BALL:
            return 126.0, "petrel_survival_ultra"
        if card_id == CardIds.HILDA:
            return 96.0, "petrel_survival_hilda"
    if mode == "finish":
        if card_id in {CardIds.BOSS_ORDERS, CardIds.LISIA}:
            return 110.0, "petrel_close_game"
    if mode == "prevent_loss":
        if card_id in {CardIds.JUMBO_ICE_CREAM, CardIds.BIANCA_DEVOTION, CardIds.SWITCH}:
            return 100.0, "petrel_prevent_loss"
    if mode in {"wall_and_tax", "disruption_loop", "close_pressure"}:
        if card_id in {CardIds.ERI, CardIds.XEROSIC, CardIds.HAND_TRIMMER, CardIds.HANDHELD_FAN}:
            return 95.0, "petrel_wall_tax"
        if card_id in {CardIds.BOSS_ORDERS, CardIds.LISIA}:
            return 92.0, "petrel_disruption_gust"
    if mode == "setup_crustle":
        if card_id in {CardIds.HILDA, CardIds.BUDDY_BUDDY_POFFIN, CardIds.ULTRA_BALL}:
            return 96.0, "petrel_setup_crustle"
    if mode in {"setup_kangaskhan", "kang_engine", "attack_continuity"}:
        if card_id in {CardIds.HILDA, CardIds.LILLIE, CardIds.ULTRA_BALL}:
            return 90.0, "petrel_setup_kang"
        if card_id == CardIds.JUMBO_ICE_CREAM:
            return 84.0, "petrel_kang_support"
    if mode == "tank_and_heal":
        heal_card = getattr(plan, "heal_card", None)
        if heal_card is not None and card_id == heal_card:
            return 120.0, "petrel_tank_heal_goal"
        if card_id in {CardIds.HERO_CAPE, CardIds.COMMUNITY_CENTER, CardIds.SWITCH, CardIds.JUMBO_ICE_CREAM, CardIds.BIANCA_DEVOTION}:
            return 88.0, "petrel_tank_support"
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


def score_eri_discard(card_id: int, deck_state) -> tuple[float, str | None]:
    plan = getattr(deck_state, "primary_plan", "stabilize")
    matchup = getattr(deck_state, "matchup", None)

    if card_id == CardIds.SWITCH:
        if plan in {"wall_and_tax", "setup_crustle", "setup_crustle_wall_now", "survival_setup"}:
            return 138.0, "eri_remove_switch"
        return 112.0, "eri_remove_switch"
    if card_id == CardIds.ULTRA_BALL:
        return 116.0, "eri_remove_ultra_ball"
    if card_id == CardIds.BUDDY_BUDDY_POFFIN:
        return 110.0, "eri_remove_poffin"
    if card_id == CardIds.POKEGEAR:
        return 104.0, "eri_remove_pokegear"
    if card_id == CardIds.HANDHELD_FAN:
        return 96.0, "eri_remove_fan"
    if card_id == CardIds.JUMBO_ICE_CREAM:
        return 92.0, "eri_remove_heal"
    if matchup is not None and getattr(matchup, "values_gust_on_setup_targets", False) and card_id == CardIds.SWITCH:
        return 142.0, "eri_dragapult_switch"
    if card_id in {CardIds.BASIC_GRASS, CardIds.MIST_ENERGY, CardIds.SPIKY_ENERGY, CardIds.GROW_GRASS_ENERGY}:
        return 28.0, "eri_remove_energy"
    return 18.0, "eri_low_value_item"


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
    if (
        card_id == CardIds.CRUSTLE
        and deck_state.primary_plan in {"setup_crustle", "setup_crustle_wall_now"}
        and getattr(deck_state, "can_make_crustle_wall_this_turn", False)
    ):
        return 112.0, "switch_crustle_setup"
    if deck_state.primary_plan in {"tank_and_heal", "setup_kangaskhan"} and card_id == CardIds.MEGA_KANGASKHAN_EX:
        return 105.0, "switch_kang"
    if card_id == CardIds.DWEBBLE:
        if deck_state.primary_plan in {"setup_crustle", "setup_crustle_wall_now"} and (
            getattr(deck_state, "can_make_crustle_wall_this_turn", False)
            or getattr(getattr(deck_state, "matchup", None), "prefers_crustle_wall", False)
        ):
            return -40.0, "avoid_expose_dwebble"
        if deck_state.primary_plan == "setup_crustle" and not getattr(deck_state, "can_make_crustle_wall_this_turn", False):
            return -40.0, "avoid_expose_dwebble"
        if deck_state.primary_plan == "setup_crustle":
            return 70.0, "switch_dwebble"
    return 20.0, None
