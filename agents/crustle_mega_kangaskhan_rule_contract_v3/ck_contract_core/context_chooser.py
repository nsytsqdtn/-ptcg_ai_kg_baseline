from __future__ import annotations

from cg.api import AreaType, SelectContext

from .selection_scorer import score_ultra_ball_discard, score_gust_target, score_switch_target
from .runtime import CardIds, ENERGY_IDS
from .search_routes import resolve_search_route, resolve_search_route_for_obs, deck_status, RouteStatus


def get_selected_card(obs, option):
    try:
        if option.area == AreaType.HAND:
            return obs.current.players[option.playerIndex].hand[option.index]
        if option.area == AreaType.DECK:
            return obs.select.deck[option.index]
        if option.area == AreaType.ACTIVE:
            return obs.current.players[option.playerIndex].active[option.index]
        if option.area == AreaType.BENCH:
            return obs.current.players[option.playerIndex].bench[option.index]
        if option.area == AreaType.LOOKING:
            return obs.current.looking[option.index]
    except Exception:
        return None
    return None


def _min_max(obs) -> tuple[int, int]:
    n = len(obs.select.option)
    minc = max(0, min(getattr(obs.select, "minCount", 1), n))
    maxc = max(minc, min(getattr(obs.select, "maxCount", 1), n))
    return minc, maxc


def choose_positive_or_min(ranked: list[tuple[float, int]], minc: int, maxc: int) -> list[int]:
    ranked = sorted(ranked, key=lambda pair: pair[0], reverse=True)
    positive = [idx for score, idx in ranked if score > 0]
    if len(positive) >= minc:
        return positive[:maxc]
    return [idx for _, idx in ranked[:minc]]


def _normalize(scored, obs, require_positive: bool = True) -> list[int]:
    minc, maxc = _min_max(obs)
    ranked = []
    for item in scored:
        raw = float(item.prior.get("total_logit", item.total_logit))
        ranked.append((raw if require_positive else raw + 1.0, item.index))
    return choose_positive_or_min(ranked, minc, maxc)


def _plan_from(deck_state=None, plan=None):
    if plan is not None:
        return plan
    return getattr(deck_state, "turn_plan", None)


def _targets_from_route(route):
    return set(route.targets or ())


def _rank_lowest_loss(scored, obs) -> list[int]:
    minc, maxc = _min_max(obs)
    ranked = [(float(item.prior.get("total_logit", item.total_logit)), item.index) for item in scored]
    return choose_positive_or_min(ranked, minc, maxc)


def choose_hilda_pair(obs, scored, deck_state, deck_knowledge, plan=None, obligations=None):
    minc, maxc = _min_max(obs)
    plan = _plan_from(deck_state, plan)
    route = resolve_search_route_for_obs(CardIds.HILDA, obs, plan, obligations, deck_knowledge)
    target_ids = _targets_from_route(route)
    candidates = []
    for item in scored:
        option = obs.select.option[item.index]
        card = get_selected_card(obs, option)
        if card is None:
            continue
        # During actual deck selection, absence from obs.select.deck is already enforced by legal options.
        if option.area != AreaType.DECK and deck_status(deck_knowledge, card.id) == RouteStatus.DEAD:
            continue
        candidates.append((item, card))

    preferred_pairs = list(getattr(plan, "hilda_pair_preferences", ()) or [])
    by_id: dict[int, list[int]] = {}
    for item, card in candidates:
        by_id.setdefault(card.id, []).append(item.index)

    for p_id, e_id in preferred_pairs:
        if target_ids and (p_id not in target_ids or e_id not in target_ids):
            continue
        if p_id in by_id and e_id in by_id:
            return [by_id[p_id][0], by_id[e_id][0]][:maxc]

    ranked = []
    for item, card in candidates:
        score = -50.0
        if card.id in target_ids:
            score += 1000.0 if route.status == RouteStatus.CONFIRMED else 450.0
        if card.id in {CardIds.DWEBBLE, CardIds.CRUSTLE, CardIds.MEGA_KANGASKHAN_EX}:
            score += 250.0
        if card.id in ENERGY_IDS:
            score += 120.0
        ranked.append((score, item.index))
    return choose_positive_or_min(ranked, minc, maxc) if ranked else _rank_lowest_loss(scored, obs)


def choose_poffin_basics(obs, scored, deck_state, deck_knowledge=None, plan=None, obligations=None):
    minc, maxc = _min_max(obs)
    plan = _plan_from(deck_state, plan)
    route = resolve_search_route_for_obs(CardIds.BUDDY_BUDDY_POFFIN, obs, plan, obligations, deck_knowledge)
    target_ids = _targets_from_route(route)
    ranked = []
    for item in scored:
        card = get_selected_card(obs, obs.select.option[item.index])
        if card is None:
            continue
        score = -100.0
        if card.id in target_ids:
            score = 1000.0 if route.status == RouteStatus.CONFIRMED else 450.0
        elif card.id == CardIds.DWEBBLE:
            score = 400.0
        elif card.id == CardIds.MEGA_KANGASKHAN_EX:
            score = 300.0
        ranked.append((score, item.index))
    return choose_positive_or_min(ranked, minc, maxc) if ranked else _rank_lowest_loss(scored, obs)


def choose_ultra_ball_discards(obs, scored, deck_state):
    ranked = []
    for item in scored:
        card = get_selected_card(obs, obs.select.option[item.index])
        if card is None:
            continue
        discard_score, _ = score_ultra_ball_discard(card.id, deck_state)
        ranked.append((discard_score, item.index))
    minc, maxc = _min_max(obs)
    return choose_positive_or_min(ranked, minc, maxc)


def choose_petrel_target(obs, scored, deck_state, deck_knowledge, plan=None, obligations=None):
    minc, maxc = _min_max(obs)
    plan = _plan_from(deck_state, plan)
    route = resolve_search_route_for_obs(CardIds.PETREL, obs, plan, obligations, deck_knowledge)
    target_ids = _targets_from_route(route)
    ranked = []
    for item in scored:
        card = get_selected_card(obs, obs.select.option[item.index])
        if card is None:
            continue
        score = -100.0
        if card.id in target_ids:
            score = 1200.0 if route.status == RouteStatus.CONFIRMED else 500.0
        if deck_status(deck_knowledge, card.id) == RouteStatus.DEAD:
            score -= 10000.0
        ranked.append((score, item.index))
    return choose_positive_or_min(ranked, minc, maxc) if ranked else _rank_lowest_loss(scored, obs)


def choose_gust_target(obs, scored, deck_state):
    minc, maxc = _min_max(obs)
    ranked = []
    for item in scored:
        card = get_selected_card(obs, obs.select.option[item.index])
        if card is None:
            continue
        value, _ = score_gust_target(card, deck_state)
        ranked.append((value, item.index))
    return choose_positive_or_min(ranked, minc, maxc)


def choose_switch_target(obs, scored, deck_state, plan=None):
    minc, maxc = _min_max(obs)
    ranked = []
    yi = obs.current.yourIndex
    target_role = getattr(_plan_from(deck_state, plan), "switch_target_role", None)
    for item in scored:
        option = obs.select.option[item.index]
        card = get_selected_card(obs, option)
        if card is None or getattr(option, "playerIndex", yi) != yi:
            continue
        value, _ = score_switch_target(card.id, deck_state)
        if target_role == "crustle" and card.id == CardIds.CRUSTLE:
            value += 1000.0
        if target_role == "kang" and card.id == CardIds.MEGA_KANGASKHAN_EX:
            value += 800.0
        ranked.append((value, item.index))
    return choose_positive_or_min(ranked, minc, maxc) if ranked else _rank_lowest_loss(scored, obs)


def choose_actions_by_context(obs, scored, deck_state, deck_knowledge, snapshot=None, plan=None, obligations=None):
    effect_id = getattr(getattr(obs.select, "effect", None), "id", None)
    context = getattr(obs.select, "context", None)
    if effect_id == CardIds.HILDA:
        return choose_hilda_pair(obs, scored, deck_state, deck_knowledge, plan, obligations)
    if effect_id == CardIds.BUDDY_BUDDY_POFFIN:
        return choose_poffin_basics(obs, scored, deck_state, deck_knowledge, plan, obligations)
    if effect_id == CardIds.ULTRA_BALL and context == SelectContext.DISCARD:
        return choose_ultra_ball_discards(obs, scored, deck_state)
    if effect_id == CardIds.PETREL:
        return choose_petrel_target(obs, scored, deck_state, deck_knowledge, plan, obligations)
    if context in {SelectContext.SWITCH, SelectContext.TO_ACTIVE}:
        if any(getattr(obs.select.option[item.index], "playerIndex", obs.current.yourIndex) != obs.current.yourIndex for item in scored):
            return choose_gust_target(obs, scored, deck_state)
        return choose_switch_target(obs, scored, deck_state, plan)
    return _normalize(scored, obs)


def choose_by_plan(obs, scored, snapshot, plan, deck_knowledge=None, obligations=None):
    from .turn_plan import build_state_view
    deck_state = build_state_view(snapshot, plan, deck_knowledge)
    return choose_actions_by_context(obs, scored, deck_state, deck_knowledge, snapshot, plan, obligations)
