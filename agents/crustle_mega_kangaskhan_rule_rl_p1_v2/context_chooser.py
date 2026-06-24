from __future__ import annotations

from cg.api import AreaType, SelectContext
from turn_plan import build_state_view

from selection_scorer import (
    petrel_targets_for_state,
    score_eri_discard,
    score_gust_target,
    score_hilda_target,
    score_poffin_target,
    score_switch_target,
    score_ultra_ball_discard,
)
from runtime import CardIds, ENERGY_IDS, get_selected_card, normalize_selection, prize_count


def _min_max(obs) -> tuple[int, int]:
    n = len(obs.select.option)
    minc = max(0, min(getattr(obs.select, "minCount", 1), n))
    maxc = max(minc, min(getattr(obs.select, "maxCount", 1), n))
    return minc, maxc


def _deck_has(deck_knowledge, card_id: int) -> bool | None:
    if deck_knowledge is None:
        return None
    return deck_knowledge.deck_has(card_id)


def choose_hilda_pair(obs, scored, deck_state, deck_knowledge):
    minc, maxc = _min_max(obs)
    candidates = []
    for item in scored:
        card = get_selected_card(obs, obs.select.option[item.index])
        if card is None:
            continue
        if _deck_has(deck_knowledge, card.id) is False and obs.select.option[item.index].area == AreaType.DECK:
            continue
        candidates.append((item, card))
    pokemon_ids = {CardIds.DWEBBLE, CardIds.CRUSTLE, CardIds.MEGA_KANGASKHAN_EX}
    energy_ids = set(ENERGY_IDS)
    best = None
    best_score = float("-inf")
    for p_item, p_card in candidates:
        if p_card.id not in pokemon_ids:
            continue
        for e_item, e_card in candidates:
            if e_item.index == p_item.index or e_card.id not in energy_ids:
                continue
            p_score, _ = score_hilda_target(p_card.id, deck_state, deck_state.matchup, candidate_ids={c.id for _, c in candidates})
            e_score, _ = score_hilda_target(e_card.id, deck_state, deck_state.matchup, paired_card_id=p_card.id, candidate_ids={c.id for _, c in candidates})
            plan_bonus = 0.0
            if deck_state.primary_plan in {"survival_setup", "setup_crustle", "setup_crustle_wall_now"}:
                if p_card.id in {CardIds.DWEBBLE, CardIds.CRUSTLE}:
                    plan_bonus += 80
                if e_card.id in {CardIds.GROW_GRASS_ENERGY, CardIds.BASIC_GRASS}:
                    plan_bonus += 50
            if deck_state.matchup.name == "dragapult_ex" and e_card.id == CardIds.MIST_ENERGY:
                plan_bonus += 70
            total = p_score + e_score + plan_bonus
            if total > best_score:
                best_score = total
                best = [p_item.index, e_item.index]
    if best:
        return best[:maxc]
    return normalize_selection(scored, obs)


def choose_poffin_basics(obs, scored, deck_state):
    minc, maxc = _min_max(obs)
    dwebble = []
    kang = []
    for item in scored:
        card = get_selected_card(obs, obs.select.option[item.index])
        if card is None:
            continue
        if card.id == CardIds.DWEBBLE:
            dwebble.append(item.index)
        elif card.id == CardIds.MEGA_KANGASKHAN_EX:
            kang.append(item.index)
    chosen: list[int] = []
    if deck_state.dwebble_in_play == 0 and dwebble:
        chosen.append(dwebble[0])
    if len(chosen) < maxc and deck_state.kangaskhan_in_play == 0 and kang:
        chosen.append(kang[0])
    if len(chosen) < maxc and dwebble:
        for i in dwebble:
            if i not in chosen:
                chosen.append(i); break
    if len(chosen) < maxc and kang:
        for i in kang:
            if i not in chosen:
                chosen.append(i); break
    # Do not fill optional bad targets; only satisfy minCount.
    if len(chosen) < minc:
        for item in scored:
            if item.index not in chosen:
                chosen.append(item.index)
            if len(chosen) >= minc:
                break
    return chosen[:maxc] if chosen else normalize_selection(scored, obs)


def choose_ultra_ball_discards(obs, scored, deck_state):
    ranked = []
    for item in scored:
        card = get_selected_card(obs, obs.select.option[item.index])
        if card is None:
            continue
        discard_score, _ = score_ultra_ball_discard(card.id, deck_state)
        ranked.append((discard_score, item.index))
    ranked.sort(key=lambda pair: pair[0], reverse=True)
    minc, maxc = _min_max(obs)
    chosen = [idx for _, idx in ranked[:maxc]]
    return chosen[:max(minc, min(maxc, len(chosen)))]


def choose_eri_discards(obs, scored, deck_state):
    ranked = []
    for item in scored:
        card = get_selected_card(obs, obs.select.option[item.index])
        if card is None:
            continue
        discard_score, _ = score_eri_discard(card.id, deck_state)
        ranked.append((discard_score, item.index))
    ranked.sort(key=lambda pair: pair[0], reverse=True)
    minc, maxc = _min_max(obs)
    chosen = [idx for _, idx in ranked[:maxc]]
    return chosen[:max(minc, min(maxc, len(chosen)))] if chosen else normalize_selection(scored, obs)


def choose_petrel_target(obs, scored, deck_state, deck_knowledge):
    minc, maxc = _min_max(obs)
    targets = petrel_targets_for_state(deck_state)
    ranked = []
    for item in scored:
        card = get_selected_card(obs, obs.select.option[item.index])
        if card is None:
            continue
        available = _deck_has(deck_knowledge, card.id)
        score, _ = score_petrel_target(card.id, deck_state)
        if card.id in targets:
            score += 200.0
        if available is False:
            score -= 10000.0
        score += float(item.prior.get("total_logit", 0.0)) * 0.01
        ranked.append((score, item.index))
    ranked.sort(key=lambda pair: pair[0], reverse=True)
    chosen = [idx for score, idx in ranked if score > -5000][:maxc]
    if len(chosen) < minc:
        chosen = [idx for _, idx in ranked[:minc]]
    return chosen or normalize_selection(scored, obs)


def choose_gust_target(obs, scored, deck_state):
    minc, maxc = _min_max(obs)
    ranked = []
    for item in scored:
        card = get_selected_card(obs, obs.select.option[item.index])
        if card is None:
            continue
        value, _ = score_gust_target(card, deck_state)
        ranked.append((value, item.index))
    ranked.sort(key=lambda x: x[0], reverse=True)
    chosen = [idx for score, idx in ranked if score > 0][:maxc]
    if len(chosen) < minc:
        chosen = [idx for _, idx in ranked[:minc]]
    return chosen


def choose_switch_target(obs, scored, deck_state):
    minc, maxc = _min_max(obs)
    ranked = []
    yi = obs.current.yourIndex
    for item in scored:
        option = obs.select.option[item.index]
        card = get_selected_card(obs, option)
        if card is None or option.playerIndex != yi:
            continue
        value, _ = score_switch_target(card.id, deck_state)
        ranked.append((value, item.index))
    ranked.sort(key=lambda x: x[0], reverse=True)
    chosen = [idx for score, idx in ranked if score > 0][:maxc]
    if len(chosen) < minc:
        chosen = [idx for _, idx in ranked[:minc]]
    return chosen or normalize_selection(scored, obs)


def choose_actions_by_context(obs, scored, deck_state, deck_knowledge):
    effect_id = getattr(getattr(obs.select, "effect", None), "id", None)
    context = getattr(obs.select, "context", None)
    if effect_id == CardIds.HILDA:
        return choose_hilda_pair(obs, scored, deck_state, deck_knowledge)
    if effect_id == CardIds.BUDDY_BUDDY_POFFIN:
        return choose_poffin_basics(obs, scored, deck_state)
    if effect_id == CardIds.ULTRA_BALL and context == SelectContext.DISCARD:
        return choose_ultra_ball_discards(obs, scored, deck_state)
    if effect_id == CardIds.ERI and context == SelectContext.DISCARD:
        return choose_eri_discards(obs, scored, deck_state)
    if effect_id == CardIds.PETREL:
        return choose_petrel_target(obs, scored, deck_state, deck_knowledge)
    if context in {SelectContext.SWITCH, SelectContext.TO_ACTIVE}:
        # Opponent target selection for Boss/Lisia, or our own switch target.
        if any(getattr(obs.select.option[item.index], "playerIndex", obs.current.yourIndex) != obs.current.yourIndex for item in scored):
            return choose_gust_target(obs, scored, deck_state)
        return choose_switch_target(obs, scored, deck_state)
    return normalize_selection(scored, obs)


def choose_by_plan(obs, scored, snapshot, plan, deck_knowledge):
    state_view = build_state_view(snapshot, plan, deck_knowledge=deck_knowledge)
    return choose_actions_by_context(obs, scored, state_view, deck_knowledge)
