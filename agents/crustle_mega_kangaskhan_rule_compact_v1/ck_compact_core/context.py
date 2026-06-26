from __future__ import annotations

from typing import Any

from cg.api import AreaType, OptionType, SelectContext

from .actions import ActionView, get_card_for_option
from .runtime import (
    CardIds,
    ENERGY_IDS,
    get_card_name_en,
    hp_remaining,
    is_core_pokemon_id,
    prize_count,
)


def min_max(obs) -> tuple[int, int]:
    n = len(getattr(obs.select, "option", []) or [])
    minc = max(0, min(int(getattr(obs.select, "minCount", 1) or 0), n))
    maxc = max(minc, min(int(getattr(obs.select, "maxCount", 1) or 1), n))
    return minc, maxc


def normalize_ranked(ranked: list[tuple[float, int]], obs) -> list[int]:
    minc, maxc = min_max(obs)
    ranked = sorted(ranked, key=lambda x: x[0], reverse=True)
    if not ranked:
        return list(range(minc))
    positive = [idx for score, idx in ranked if score > 0]
    if len(positive) >= minc:
        return positive[:maxc]
    return [idx for _, idx in ranked[:minc]]


def selected_card(obs, action: ActionView):
    return get_card_for_option(obs, action.option)


def choose_context_action(obs, state, actions: list[ActionView], selected_plan: str, setup, wall, prize, scored=None) -> list[int]:
    effect_id = getattr(getattr(obs.select, "effect", None), "id", None)
    context = getattr(obs.select, "context", None)

    # Setup choices at game start.
    if context in {SelectContext.SETUP_ACTIVE_POKEMON, SelectContext.SETUP_BENCH_POKEMON, SelectContext.TO_FIELD, SelectContext.TO_BENCH}:
        return choose_basic_setup(obs, actions)

    if effect_id == CardIds.BUDDY_BUDDY_POFFIN:
        return choose_poffin(obs, actions, state, setup)
    if effect_id == CardIds.HILDA:
        return choose_hilda(obs, actions, state, selected_plan, setup, wall, prize)
    if effect_id == CardIds.PETREL:
        return choose_petrel(obs, actions, selected_plan, setup, wall, prize)
    if effect_id == CardIds.POKEGEAR:
        return choose_pokegear(obs, actions, selected_plan, setup, wall, prize)
    if effect_id == CardIds.ULTRA_BALL and context == SelectContext.DISCARD:
        return choose_ultra_ball_discard(obs, actions, selected_plan, setup, wall, prize)

    # Opponent target after Boss/Lisia or similar effects.
    if context in {SelectContext.SWITCH, SelectContext.TO_ACTIVE}:
        if any(getattr(a.option, "playerIndex", state.my_index) != state.my_index for a in actions):
            return choose_gust_target(obs, actions, state, prize)
        return choose_switch_target(obs, actions, selected_plan, setup, wall, prize)

    if context in {SelectContext.TO_HAND, SelectContext.LOOK, SelectContext.NOT_MOVE}:
        # Topdeck/search choice, including Pokegear's LOOKING options.
        return choose_to_hand(obs, actions, selected_plan, setup, wall, prize)

    if context == SelectContext.DISCARD:
        return choose_generic_discard(obs, actions, selected_plan, setup, wall, prize)

    # YES/NO: activate usually yes, but avoid unsafe optional draw in deck danger.
    if all(a.has("yes") or a.has("no") for a in actions):
        return choose_yes_no(obs, actions, state)

    if scored:
        ranked = [(s.score, s.index) for s in scored]
        return normalize_ranked(ranked, obs)
    return normalize_ranked([(0.0, a.index) for a in actions], obs)


def choose_basic_setup(obs, actions):
    ranked = []
    for a in actions:
        card = selected_card(obs, a)
        cid = getattr(card, "id", None)
        score = 0.0
        if cid == CardIds.DWEBBLE:
            score = 1000.0
        elif cid == CardIds.MEGA_KANGASKHAN_EX:
            score = 700.0
        ranked.append((score, a.index))
    return normalize_ranked(ranked, obs)


def choose_poffin(obs, actions, state, setup):
    ranked = []
    for a in actions:
        card = selected_card(obs, a)
        cid = getattr(card, "id", None)
        score = -20.0
        if cid == CardIds.DWEBBLE:
            score = 1000.0
        # Keep any other legal low-risk Basic only when backup is urgent.
        elif setup.need_backup:
            score = 200.0
        ranked.append((score, a.index))
    return normalize_ranked(ranked, obs)


def choose_hilda(obs, actions, state, selected_plan, setup, wall, prize):
    ranked = []
    for a in actions:
        card = selected_card(obs, a)
        cid = getattr(card, "id", None)
        score = -50.0
        if cid == CardIds.CRUSTLE:
            score = 1000.0 if setup.need_crustle or selected_plan == "setup" else 650.0
        elif cid == CardIds.GROW_GRASS_ENERGY:
            score = 850.0 if selected_plan == "setup" else 500.0
        elif cid == CardIds.BASIC_GRASS:
            score = 760.0 if selected_plan == "setup" else 450.0
        elif cid == CardIds.MIST_ENERGY:
            score = 620.0 if wall.need_protect_core else 420.0
        elif cid == CardIds.SPIKY_ENERGY:
            score = 360.0
        elif cid in ENERGY_IDS:
            score = 300.0
        ranked.append((score, a.index))
    return normalize_ranked(ranked, obs)


def choose_petrel(obs, actions, selected_plan, setup, wall, prize):
    ranked = []
    for a in actions:
        card = selected_card(obs, a)
        cid = getattr(card, "id", None)
        score = -80.0
        if selected_plan == "setup":
            if cid == CardIds.BUDDY_BUDDY_POFFIN and setup.need_backup:
                score = 1000.0
            elif cid == CardIds.HILDA and (setup.need_crustle or setup.need_energy_for_crustle):
                score = 900.0
            elif cid == CardIds.ULTRA_BALL:
                score = 760.0
            elif cid == CardIds.POKEGEAR:
                score = 420.0
        elif selected_plan == "prize":
            if cid == CardIds.BOSS_ORDERS:
                score = 1000.0
            elif cid == CardIds.LISIA:
                score = 860.0
            elif cid == CardIds.SWITCH and prize.need_switch:
                score = 800.0
        else:
            if wall.preferred_response == "heal":
                if cid == CardIds.JUMBO_ICE_CREAM:
                    score = 1000.0
                elif cid == CardIds.BIANCA_DEVOTION:
                    score = 900.0
            elif wall.preferred_response == "energy_disrupt":
                if cid == CardIds.XEROSIC:
                    score = 1000.0
                elif cid == CardIds.HANDHELD_FAN:
                    score = 850.0
                elif cid == CardIds.BOSS_ORDERS:
                    score = 650.0
            elif wall.preferred_response == "hand_disrupt":
                if cid == CardIds.ERI:
                    score = 1000.0
                elif cid == CardIds.HAND_TRIMMER:
                    score = 900.0
                elif cid == CardIds.XEROSIC:
                    score = 780.0
            else:
                if cid == CardIds.BOSS_ORDERS and prize.available:
                    score = 820.0
                elif cid == CardIds.ERI:
                    score = 620.0
                elif cid == CardIds.JUMBO_ICE_CREAM:
                    score = 560.0
                elif cid == CardIds.HILDA:
                    score = 520.0
        ranked.append((score, a.index))
    return normalize_ranked(ranked, obs)


def choose_pokegear(obs, actions, selected_plan, setup, wall, prize):
    # Pokegear only sees top cards, so choose the best visible supporter for the
    # current plan. If no useful supporter appears, choose the least bad option.
    ranked = []
    for a in actions:
        card = selected_card(obs, a)
        cid = getattr(card, "id", None)
        score = -20.0
        if selected_plan == "setup":
            if cid == CardIds.HILDA:
                score = 900.0
            elif cid == CardIds.PETREL:
                score = 820.0
            elif cid == CardIds.LILLIE and not setup.need_backup:
                score = 380.0
        elif selected_plan == "prize":
            if cid == CardIds.BOSS_ORDERS:
                score = 1000.0
            elif cid == CardIds.LISIA:
                score = 900.0
            elif cid == CardIds.PETREL:
                score = 650.0
        else:
            if cid == CardIds.PETREL:
                score = 820.0
            elif cid == CardIds.ERI:
                score = 720.0
            elif cid == CardIds.XEROSIC:
                score = 700.0
            elif cid == CardIds.BOSS_ORDERS and prize.available:
                score = 650.0
        ranked.append((score, a.index))
    return normalize_ranked(ranked, obs)


def choose_to_hand(obs, actions, selected_plan, setup, wall, prize):
    ranked = []
    for a in actions:
        card = selected_card(obs, a)
        cid = getattr(card, "id", None)
        score = 0.0
        if selected_plan == "setup":
            if cid == CardIds.CRUSTLE and setup.need_crustle:
                score = 1000.0
            elif cid == CardIds.DWEBBLE and setup.need_dwebble:
                score = 950.0
            elif cid in {CardIds.GROW_GRASS_ENERGY, CardIds.BASIC_GRASS} and setup.need_energy_for_crustle:
                score = 750.0
            elif cid == CardIds.MIST_ENERGY:
                score = 520.0
        elif selected_plan == "prize":
            if cid == prize.target_card_id:
                score = 1000.0
            elif cid in {CardIds.BOSS_ORDERS, CardIds.LISIA}:
                score = 850.0
            elif cid == CardIds.SWITCH and prize.need_switch:
                score = 720.0
        else:
            if cid == CardIds.JUMBO_ICE_CREAM and wall.preferred_response == "heal":
                score = 900.0
            elif cid == CardIds.XEROSIC and wall.preferred_response == "energy_disrupt":
                score = 850.0
            elif cid == CardIds.ERI and wall.preferred_response == "hand_disrupt":
                score = 800.0
            elif cid == CardIds.PETREL:
                score = 550.0
        ranked.append((score, a.index))
    return normalize_ranked(ranked, obs)


def choose_ultra_ball_discard(obs, actions, selected_plan, setup, wall, prize):
    ranked = []
    for a in actions:
        card = selected_card(obs, a)
        cid = getattr(card, "id", None)
        # Higher score means more disposable.
        score = 0.0
        if cid in {CardIds.CRUSTLE, CardIds.DWEBBLE, CardIds.MEGA_KANGASKHAN_EX}:
            score -= 900.0
        if cid in {CardIds.PETREL, CardIds.HILDA, CardIds.BOSS_ORDERS, CardIds.LISIA}:
            score -= 520.0
        if cid in {CardIds.MIST_ENERGY, CardIds.GROW_GRASS_ENERGY, CardIds.BASIC_GRASS}:
            score -= 360.0
        if cid in {CardIds.COMMUNITY_CENTER, CardIds.FESTIVAL_GROUNDS, CardIds.ROCKET_FACTORY}:
            score += 180.0
        if cid == CardIds.LILLIE and (state_deck_danger(obs) or setup.need_backup):
            score += 220.0
        if cid == CardIds.SPIKY_ENERGY:
            score += 80.0
        ranked.append((score, a.index))
    return normalize_ranked(ranked, obs)


def choose_generic_discard(obs, actions, selected_plan, setup, wall, prize):
    ranked = []
    for a in actions:
        card = selected_card(obs, a)
        cid = getattr(card, "id", None)
        score = 0.0
        if cid in {CardIds.CRUSTLE, CardIds.DWEBBLE, CardIds.MEGA_KANGASKHAN_EX}:
            score -= 700.0
        if cid in {CardIds.PETREL, CardIds.HILDA, CardIds.BOSS_ORDERS, CardIds.LISIA}:
            score -= 360.0
        if cid in ENERGY_IDS:
            score += 60.0
        if cid in {CardIds.COMMUNITY_CENTER, CardIds.FESTIVAL_GROUNDS, CardIds.ROCKET_FACTORY}:
            score += 160.0
        ranked.append((score, a.index))
    return normalize_ranked(ranked, obs)


def choose_gust_target(obs, actions, state, prize):
    ranked = []
    for a in actions:
        card = selected_card(obs, a)
        cid = getattr(card, "id", None)
        score = 0.0
        if prize.available and cid == prize.target_card_id:
            score = 1200.0
        elif card is not None and state.active_attack_damage >= hp_remaining(card) > 0:
            score = 500.0 + prize_count(card) * 250.0
        elif card is not None:
            score = 80.0 - hp_remaining(card) * 0.5
        ranked.append((score, a.index))
    return normalize_ranked(ranked, obs)


def choose_switch_target(obs, actions, selected_plan, setup, wall, prize):
    ranked = []
    for a in actions:
        card = selected_card(obs, a)
        cid = getattr(card, "id", None)
        score = 0.0
        if selected_plan == "setup" and setup.need_crustle_active and cid == CardIds.CRUSTLE:
            score = 1000.0
        elif selected_plan == "prize" and cid == prize.attacker_card_id:
            score = 1000.0
        elif cid == CardIds.CRUSTLE:
            score = 700.0
        elif cid == CardIds.MEGA_KANGASKHAN_EX:
            score = 420.0
        elif cid == CardIds.DWEBBLE:
            score = 320.0
        ranked.append((score, a.index))
    return normalize_ranked(ranked, obs)


def choose_yes_no(obs, actions, state):
    ranked = []
    for a in actions:
        score = 0.0
        if a.has("yes"):
            score = 100.0
        if a.has("no"):
            score = 0.0
        if state.deck_danger and a.has("yes"):
            score -= 200.0
        ranked.append((score, a.index))
    return normalize_ranked(ranked, obs)


def state_deck_danger(obs) -> bool:
    try:
        yi = obs.current.yourIndex
        me = obs.current.players[yi]
        return int(getattr(me, "deckCount", 0) or 0) <= len(getattr(me, "prize", []) or []) + 1
    except Exception:
        return False
