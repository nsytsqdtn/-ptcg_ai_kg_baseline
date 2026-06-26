from __future__ import annotations

from cg.api import AreaType

from selection_scorer import PETREL_TARGETS_BY_PLAN, score_hilda_target, score_ultra_ball_discard
from runtime import CardIds


def get_selected_card(obs, option):
    if option.area == AreaType.HAND:
        return obs.current.players[option.playerIndex].hand[option.index]
    if option.area == AreaType.DECK:
        return obs.select.deck[option.index]
    if option.area == AreaType.ACTIVE:
        return obs.current.players[option.playerIndex].active[option.index]
    if option.area == AreaType.BENCH:
        return obs.current.players[option.playerIndex].bench[option.index]
    return None


def choose_hilda_pair(obs, scored, deck_state, deck_knowledge):
    candidate_ids = {
        getattr(card, "id", None)
        for card in getattr(obs.select, "deck", []) or []
        if card is not None
    }
    best_score = float("-inf")
    best_pair: list[int] | None = None
    for first in scored:
        first_card = get_selected_card(obs, obs.select.option[first.index])
        if first_card is None:
            continue
        for second in scored:
            if second.index == first.index:
                continue
            second_card = get_selected_card(obs, obs.select.option[second.index])
            if second_card is None:
                continue
            pokemon_card, energy_card = None, None
            if first_card.id in {CardIds.DWEBBLE, CardIds.CRUSTLE, CardIds.MEGA_KANGASKHAN_EX}:
                pokemon_card = first_card
            if second_card.id in {CardIds.DWEBBLE, CardIds.CRUSTLE, CardIds.MEGA_KANGASKHAN_EX}:
                pokemon_card = second_card
            if first_card.id in {CardIds.GROW_GRASS_ENERGY, CardIds.MIST_ENERGY, CardIds.SPIKY_ENERGY, CardIds.BASIC_GRASS}:
                energy_card = first_card
            if second_card.id in {CardIds.GROW_GRASS_ENERGY, CardIds.MIST_ENERGY, CardIds.SPIKY_ENERGY, CardIds.BASIC_GRASS}:
                energy_card = second_card
            if pokemon_card is None or energy_card is None:
                continue
            score_a, _ = score_hilda_target(
                pokemon_card.id,
                deck_state,
                getattr(deck_state, "matchup", None) or type("Matchup", (), {"name": "unknown", "values_mist_energy": False})(),
                candidate_ids=candidate_ids,
            )
            score_b, _ = score_hilda_target(
                energy_card.id,
                deck_state,
                getattr(deck_state, "matchup", None) or type("Matchup", (), {"name": "unknown", "values_mist_energy": False})(),
                paired_card_id=pokemon_card.id,
                candidate_ids=candidate_ids,
            )
            total = score_a + score_b
            if total > best_score:
                best_score = total
                best_pair = [first.index, second.index]
    if best_pair:
        return best_pair[: max(1, obs.select.maxCount)]
    return [item.index for item in scored[: max(1, obs.select.maxCount)]]


def choose_poffin_basics(obs, scored, deck_state):
    dwebble_indices = []
    kang_indices = []
    fallback = []
    for item in scored:
        card = get_selected_card(obs, obs.select.option[item.index])
        if card is None:
            continue
        if card.id == CardIds.DWEBBLE:
            dwebble_indices.append(item.index)
        elif card.id == CardIds.MEGA_KANGASKHAN_EX:
            kang_indices.append(item.index)
        else:
            fallback.append(item.index)
    chosen: list[int] = []
    if dwebble_indices:
        chosen.append(dwebble_indices[0])
    if kang_indices and len(chosen) < max(1, obs.select.maxCount):
        chosen.append(kang_indices[0])
    for index in dwebble_indices[1:] + kang_indices[1:] + fallback:
        if len(chosen) >= max(1, obs.select.maxCount):
            break
        if index not in chosen:
            chosen.append(index)
    return chosen or [item.index for item in scored[: max(1, obs.select.maxCount)]]


def choose_ultra_ball_discards(obs, scored, deck_state):
    ranked = []
    for item in scored:
        card = get_selected_card(obs, obs.select.option[item.index])
        if card is None:
            continue
        discard_score, _ = score_ultra_ball_discard(card.id, deck_state)
        ranked.append((discard_score, item.index))
    ranked.sort(key=lambda pair: pair[0], reverse=True)
    return [index for _, index in ranked[: max(1, obs.select.maxCount)]]


def choose_petrel_target(obs, scored, deck_state, deck_knowledge):
    primary_plan = getattr(deck_state, "primary_plan", "stabilize")
    targets = PETREL_TARGETS_BY_PLAN.get(primary_plan, set())
    ranked = []
    for item in scored:
        card = get_selected_card(obs, obs.select.option[item.index])
        if card is None:
            continue
        card_id = getattr(card, "id", None)
        available = True if deck_knowledge is None else deck_knowledge.deck_has(card_id)
        plan_bonus = 100.0 if card_id in targets else 0.0
        if available is False:
            plan_bonus -= 1000.0
        ranked.append((plan_bonus, item.index))
    ranked.sort(key=lambda pair: pair[0], reverse=True)
    return [ranked[0][1]] if ranked else [item.index for item in scored[:1]]


def choose_actions_by_context(obs, scored, deck_state, deck_knowledge):
    effect_id = getattr(getattr(obs.select, "effect", None), "id", None)
    context = getattr(obs.select, "context", None)
    context_name = getattr(context, "name", None) or str(context)
    if effect_id == CardIds.HILDA:
        return choose_hilda_pair(obs, scored, deck_state, deck_knowledge)
    if effect_id == CardIds.BUDDY_BUDDY_POFFIN:
        return choose_poffin_basics(obs, scored, deck_state)
    if effect_id == CardIds.ULTRA_BALL and (context_name == "DISCARD" or context == 8):
        return choose_ultra_ball_discards(obs, scored, deck_state)
    if effect_id == CardIds.PETREL:
        return choose_petrel_target(obs, scored, deck_state, deck_knowledge)
    return [item.index for item in scored[: max(1, obs.select.maxCount)]]
