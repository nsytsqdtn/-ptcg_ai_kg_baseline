from __future__ import annotations

from cg.api import OptionType
from .runtime import CardIds
from .search_routes import resolve_search_route, RouteStatus


def _allowed_items(obs, allowed):
    if not allowed:
        return []
    if all(isinstance(x, int) for x in allowed):
        return [(int(i), obs.select.option[int(i)], set(), None) for i in allowed if 0 <= int(i) < len(obs.select.option)]
    out = []
    for a in allowed:
        idx = getattr(a, "index", None)
        if idx is None or idx < 0 or idx >= len(obs.select.option):
            continue
        out.append((idx, obs.select.option[idx], set(getattr(a, "tags", set()) or set()), getattr(a, "card_id", None)))
    return out


def try_finish_search_if_applicable(obs, snapshot, obligations, plan, deck_knowledge, allowed_indices=None, allowed_actions=None):
    """Deterministic one-step finish sequencer.

    This is intentionally narrow: it only commits to an action when the current
    TurnPlan has already verified a win candidate. It can play the first step of
    simple finish routes (attack now, gust now, Petrel/Pokegear-like supporter
    route is not treated as verified unless confirmed by DeckKnowledge).
    """
    if getattr(plan, "objective", getattr(plan, "mode", "")) != "finish":
        return None
    allowed = _allowed_items(obs, allowed_actions if allowed_actions is not None else allowed_indices)
    if not allowed:
        return None

    # Direct win: attack immediately.
    for idx, option, tags, _ in allowed:
        if option.type == OptionType.ATTACK or "attack" in tags:
            return [idx]

    # If a gust card is already legal and the plan says the gust target wins,
    # play it as the first step. Target selection will be handled by context_chooser.
    for idx, option, tags, cid in allowed:
        if "gust" in tags or cid in {CardIds.BOSS_ORDERS, CardIds.LISIA}:
            return [idx]

    # Petrel can be a verified finish enabler only when the requested trainer is
    # confirmed in deck. Pokegear remains possible-only and is not finish-verified.
    for idx, option, tags, cid in allowed:
        if cid == CardIds.PETREL:
            route = resolve_search_route(CardIds.PETREL, plan, obligations, deck_knowledge)
            if route.status == RouteStatus.CONFIRMED:
                return [idx]

    # Switch can be the first step if a bench attacker is already part of the
    # verified plan. Keep this conservative; scoring handles pressure routes.
    for idx, option, tags, cid in allowed:
        if "switch" in tags and getattr(plan, "switch_target_role", None):
            return [idx]
    return None
