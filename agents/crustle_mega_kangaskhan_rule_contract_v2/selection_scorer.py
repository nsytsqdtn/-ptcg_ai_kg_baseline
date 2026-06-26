from __future__ import annotations

from runtime import CardIds, prize_count


def _turn_plan(deck_state):
    return getattr(deck_state, "turn_plan", None)


def petrel_targets_for_state(deck_state) -> set[int]:
    plan = _turn_plan(deck_state)
    if plan is None or not getattr(plan, "petrel_target_ids", None):
        return set()
    return set(plan.petrel_target_ids)


def score_petrel_play(deck_state, state, hand_ids: set[int] | None = None, discard_ids: set[int] | None = None) -> tuple[float, str | None]:
    if getattr(state, "supporterPlayed", False):
        return -100.0, "supporter_already_used"
    targets = petrel_targets_for_state(deck_state)
    if not targets:
        return -80.0, "petrel_no_plan_target"
    hidden = targets - set(hand_ids or set()) - set(discard_ids or set())
    if not hidden:
        return -60.0, "petrel_no_hidden_target"
    return 70.0, "petrel_plan_search_open"


def score_petrel_target(card_id: int, deck_state) -> tuple[float, str | None]:
    plan = _turn_plan(deck_state)
    targets = list(getattr(plan, "petrel_target_ids", []) or [])
    if card_id not in targets:
        return -20.0, None
    base = 160.0 - 8.0 * targets.index(card_id)
    if plan is not None and card_id == getattr(plan, "heal_card", None):
        return base + 18.0, "petrel_heal_target"
    if targets.index(card_id) == 0:
        return base + 8.0, "petrel_top_plan_target"
    return base, "petrel_plan_target"


def score_hilda_target(
    card_id: int,
    deck_state,
    matchup,
    paired_card_id: int | None = None,
    candidate_ids: set[int] | None = None,
) -> tuple[float, str | None]:
    plan = _turn_plan(deck_state)
    pairs = list(getattr(plan, "hilda_pair_preferences", []) or [])
    if paired_card_id is not None:
        for rank, (pokemon_id, energy_id) in enumerate(pairs):
            if paired_card_id == pokemon_id and card_id == energy_id:
                return 160.0 - 8.0 * rank, "hilda_plan_pair"
    else:
        for rank, (pokemon_id, _energy_id) in enumerate(pairs):
            if card_id == pokemon_id:
                return 170.0 - 8.0 * rank, "hilda_plan_pair"
    targets = list(getattr(plan, "search_target_ids", []) or [])
    if card_id in targets:
        return 90.0, "hilda_plan_target"
    return -15.0, None


def infer_pair_card_id(looking_cards) -> int | None:
    for card in looking_cards or []:
        if card is not None and getattr(card, "id", None) in {CardIds.DWEBBLE, CardIds.CRUSTLE, CardIds.MEGA_KANGASKHAN_EX}:
            return card.id
    return None


def score_poffin_target(card_id: int, deck_state, matchup) -> tuple[float, str | None]:
    targets = list(getattr(_turn_plan(deck_state), "poffin_basic_ids", []) or [])
    if card_id not in targets:
        return -25.0, None
    return 170.0 - 8.0 * targets.index(card_id), "poffin_plan_target"


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
    if card_id == CardIds.DWEBBLE and getattr(deck_state, "setup_missing_crustle", False):
        return -110.0, "protect_dwebble"
    if card_id == CardIds.CRUSTLE and getattr(deck_state, "crustle_in_play", 0) == 0:
        return -110.0, "protect_crustle"
    if card_id == CardIds.MEGA_KANGASKHAN_EX and getattr(deck_state, "kangaskhan_in_play", 0) == 0:
        return -100.0, "protect_kang"
    if card_id == CardIds.MIST_ENERGY and getattr(getattr(deck_state, "matchup", None), "values_mist_energy", False):
        return -90.0, "protect_mist"
    if card_id == CardIds.BASIC_GRASS:
        return 20.0, "discard_basic_grass"
    return 5.0, None


def score_eri_discard(card_id: int, deck_state) -> tuple[float, str | None]:
    if card_id == CardIds.SWITCH:
        return 138.0, "eri_remove_switch"
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
    if card_id in {CardIds.BASIC_GRASS, CardIds.MIST_ENERGY, CardIds.SPIKY_ENERGY, CardIds.GROW_GRASS_ENERGY}:
        return 28.0, "eri_remove_energy"
    return 18.0, "eri_low_value_item"


def score_gust_target(card, deck_state) -> tuple[float, str | None]:
    if card is None:
        return 0.0, None
    hp = getattr(card, "hp", 999)
    current_attack_damage = getattr(deck_state, "current_attack_damage", 0)
    can_ko = current_attack_damage >= hp > 0
    if getattr(deck_state, "gust_for_win", False) and can_ko and prize_count(card) >= getattr(deck_state, "my_prizes_left", 99):
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
    role = getattr(_turn_plan(deck_state), "switch_target_role", None)
    if role == "crustle" and card_id == CardIds.CRUSTLE:
        return 170.0, "switch_plan_target"
    if role == "kang" and card_id == CardIds.MEGA_KANGASKHAN_EX:
        return 170.0, "switch_plan_target"
    if role in {"crustle_or_kang", "safest_wall_or_tank"} and card_id == CardIds.CRUSTLE:
        return 165.0, "switch_plan_target"
    if role in {"crustle_or_kang", "safest_wall_or_tank", "best_attacker"} and card_id == CardIds.MEGA_KANGASKHAN_EX:
        return 155.0, "switch_plan_target"
    if card_id == CardIds.DWEBBLE:
        return -50.0, "avoid_expose_dwebble"
    return 10.0, None
