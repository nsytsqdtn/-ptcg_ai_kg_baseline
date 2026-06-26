from __future__ import annotations

from cg.api import AreaType, SelectContext
from turn_plan import build_state_view

from selection_scorer import score_eri_discard, score_gust_target, score_petrel_target, score_ultra_ball_discard
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
    preferred_pairs = list(getattr(getattr(deck_state, "turn_plan", None), "hilda_pair_preferences", []) or [])
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
            total = -50.0
            for rank, pair in enumerate(preferred_pairs):
                if pair == (p_card.id, e_card.id):
                    total = 260.0 - rank * 15.0
                    break
            if total < 0 and p_card.id in {CardIds.DWEBBLE, CardIds.CRUSTLE, CardIds.MEGA_KANGASKHAN_EX}:
                if p_card.id in set(getattr(getattr(deck_state, "turn_plan", None), "search_target_ids", []) or []):
                    total += 80.0
                if e_card.id in set(getattr(getattr(deck_state, "turn_plan", None), "attach_energy_preference", []) or []):
                    total += 75.0
            if total > best_score:
                best_score = total
                best = [p_item.index, e_item.index]
    if best:
        return best[:maxc]
    return normalize_selection(scored, obs)


def choose_poffin_basics(obs, scored, deck_state):
    minc, maxc = _min_max(obs)
    targets = list(getattr(getattr(deck_state, "turn_plan", None), "poffin_basic_ids", []) or [])
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
    if CardIds.DWEBBLE in targets and dwebble:
        chosen.append(dwebble[0])
    if len(chosen) < maxc and CardIds.MEGA_KANGASKHAN_EX in targets and kang:
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
    targets = set(getattr(getattr(deck_state, "turn_plan", None), "petrel_target_ids", []) or [])
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
    role = getattr(getattr(deck_state, "turn_plan", None), "switch_target_role", None)
    ranked = []
    yi = obs.current.yourIndex
    for item in scored:
        option = obs.select.option[item.index]
        card = get_selected_card(obs, option)
        if card is None or option.playerIndex != yi:
            continue
        if role == "crustle":
            value = 200.0 if card.id == CardIds.CRUSTLE else -80.0 if card.id == CardIds.DWEBBLE else 20.0
        elif role == "kang":
            value = 200.0 if card.id == CardIds.MEGA_KANGASKHAN_EX else -80.0 if card.id == CardIds.DWEBBLE else 20.0
        elif role in {"crustle_or_kang", "safest_wall_or_tank"}:
            value = 190.0 if card.id == CardIds.CRUSTLE else 180.0 if card.id == CardIds.MEGA_KANGASKHAN_EX else -80.0 if card.id == CardIds.DWEBBLE else 15.0
        elif role == "best_attacker":
            value = 200.0 if card.id == CardIds.MEGA_KANGASKHAN_EX else 120.0 if card.id == CardIds.CRUSTLE else -60.0
        elif role == "none":
            value = -200.0
        else:
            value = 10.0
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
