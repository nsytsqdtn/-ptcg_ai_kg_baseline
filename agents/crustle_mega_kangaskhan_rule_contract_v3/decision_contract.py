from __future__ import annotations

from cg.api import OptionType, SelectContext
from runtime import CardIds, ENERGY_IDS
from search_routes import resolve_search_route


def _search_card_id(action) -> int | None:
    return action.card_id


def can_contribute_to_backup(action, snapshot, plan, deck_knowledge) -> bool:
    tags = action.tags
    if "bench_basic" in tags or "backup_route" in tags:
        return True
    if "play_search" in tags:
        # Only count search as a backup route if it can find a Basic or a search
        # card that leads to Basic setup under current deck knowledge.
        cid = _search_card_id(action)
        route = resolve_search_route(cid, plan, None, deck_knowledge) if cid is not None else None
        return bool(route and route.live and any(t in {CardIds.DWEBBLE, CardIds.MEGA_KANGASKHAN_EX, CardIds.BUDDY_BUDDY_POFFIN, CardIds.HILDA, CardIds.ULTRA_BALL} for t in route.targets))
    if "switch" in tags and getattr(snapshot, "field_count", 0) >= 2:
        return True
    if "attach_spiky" in tags or "attach_mist" in tags:
        return bool(getattr(snapshot, "active_under_ko_threat", False))
    return False


def violates_obligations(action, snapshot, obligations, plan, deck_knowledge) -> bool:
    tags = action.tags
    objective = getattr(plan, "objective", getattr(plan, "mode", ""))

    if getattr(obligations, "must_not_end_turn", False) and "end_turn" in tags:
        return True
    if getattr(obligations, "must_not_attack", False) and "attack" in tags:
        return True
    if getattr(obligations, "must_not_retreat", False) and "retreat" in tags:
        return True
    if getattr(obligations, "must_not_draw", False) and "draw_deck" in tags and objective != "finish":
        return True
    if getattr(obligations, "must_add_backup", False) and not can_contribute_to_backup(action, snapshot, plan, deck_knowledge):
        return True
    if getattr(obligations, "must_preserve_wall", False):
        if "wall_break" in tags and "finish_route" not in tags:
            return True
    return False


def violates_search_contract(action, snapshot, obligations, plan, deck_knowledge) -> bool:
    if "play_search" not in action.tags:
        return False
    route = resolve_search_route(action.card_id, plan, obligations, deck_knowledge)
    return not route.live


def violates_plan_contract(action, snapshot, obligations, plan, deck_knowledge) -> bool:
    objective = getattr(plan, "objective", getattr(plan, "mode", ""))
    tags = action.tags

    if objective == "setup_backup":
        return not can_contribute_to_backup(action, snapshot, plan, deck_knowledge)
    if objective == "setup_crustle_wall":
        allowed = {"evolve_crustle", "switch_to_crustle", "wall_preserve", "search_pokemon", "search_energy", "play_search", "attach_growing_grass", "attach_basic_grass", "bench_basic", "backup_route"}
        return not bool(tags & allowed)
    if objective == "preserve_wall":
        if "wall_break" in tags:
            return True
        allowed = {"wall_preserve", "disruption", "heal", "attach_spiky", "attach_mist", "attach_growing_grass", "search_trainer", "play_search", "attack", "end_turn"}
        return not bool(tags & allowed)
    if objective == "protect_bench_core":
        allowed = {"attach_mist", "search_energy", "search_pokemon", "play_search", "bench_basic", "backup_route", "wall_preserve", "evolve_crustle", "switch"}
        return not bool(tags & allowed)
    if objective == "kang_engine":
        if getattr(obligations, "must_add_backup", False) or getattr(obligations, "must_not_draw", False):
            return True
    return False


def apply_decision_contract(obs, classified, snapshot, obligations, plan, deck_knowledge):
    # During non-main effect resolution, avoid over-filtering target choices. The
    # context chooser will enforce route-specific target selection.
    context = getattr(obs.select, "context", None)
    hard_filter_context = context in {SelectContext.MAIN, SelectContext.ATTACK, SelectContext.ACTIVATE} or context is None

    allowed = []
    for action in classified:
        if hard_filter_context:
            if violates_obligations(action, snapshot, obligations, plan, deck_knowledge):
                continue
            if violates_plan_contract(action, snapshot, obligations, plan, deck_knowledge):
                continue
            if violates_search_contract(action, snapshot, obligations, plan, deck_knowledge):
                continue
        else:
            if violates_search_contract(action, snapshot, obligations, plan, deck_knowledge):
                # Only PLAY search is filtered here; SELECT target routes are handled later.
                continue
        allowed.append(action)
    return allowed or list(classified)
