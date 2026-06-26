from __future__ import annotations

from cg.api import SelectContext
from .runtime import CardIds
from .search_routes import resolve_search_route, RouteStatus


def _search_card_id(action) -> int | None:
    return action.card_id


def _route_for(action, plan, obligations, deck_knowledge):
    cid = _search_card_id(action)
    return resolve_search_route(cid, plan, obligations, deck_knowledge) if cid is not None else None


def can_contribute_to_backup(action, snapshot, plan, deck_knowledge, obligations=None) -> bool:
    tags = action.tags
    if "bench_basic" in tags or "backup_route" in tags:
        return True
    if "play_search" in tags:
        route = _route_for(action, plan, obligations, deck_knowledge)
        if route is None or route.status == RouteStatus.DEAD:
            return False
        return any(
            t in {CardIds.DWEBBLE, CardIds.MEGA_KANGASKHAN_EX, CardIds.BUDDY_BUDDY_POFFIN, CardIds.HILDA, CardIds.ULTRA_BALL, CardIds.POKEGEAR}
            for t in route.targets
        )
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
    if getattr(obligations, "must_add_backup", False) and not can_contribute_to_backup(action, snapshot, plan, deck_knowledge, obligations):
        return True
    if getattr(obligations, "must_preserve_wall", False):
        if "wall_break" in tags and "finish_route" not in tags:
            return True
    return False


def violates_search_contract(action, snapshot, obligations, plan, deck_knowledge) -> bool:
    if "play_search" not in action.tags:
        return False
    route = _route_for(action, plan, obligations, deck_knowledge)
    if route is None or route.status == RouteStatus.DEAD:
        return True
    objective = getattr(plan, "objective", getattr(plan, "mode", ""))
    if objective == "finish" and route.status != RouteStatus.CONFIRMED:
        return True
    # pressure_prize is allowed to use POSSIBLE Petrel/Pokegear routes as pressure,
    # but never DEAD routes. Finish remains confirmed-only.
    if objective == "take_prize" and route.status != RouteStatus.CONFIRMED and not getattr(obligations, "must_add_backup", False):
        return True
    return False


def violates_plan_contract(action, snapshot, obligations, plan, deck_knowledge) -> bool:
    objective = getattr(plan, "objective", getattr(plan, "mode", ""))
    tags = action.tags

    if objective == "setup_backup":
        return not can_contribute_to_backup(action, snapshot, plan, deck_knowledge, obligations)

    if objective == "setup_crustle_wall":
        allowed = {
            "evolve_crustle", "switch_to_crustle", "wall_preserve", "search_pokemon", "search_energy", "play_search",
            "attach_growing_grass", "attach_basic_grass", "attach_mist", "bench_basic", "backup_route", "switch",
        }
        return not bool(tags & allowed)

    if objective in {"wall_control", "preserve_wall"}:
        if "wall_break" in tags:
            return True
        allowed = {
            "wall_preserve", "disruption", "heal", "attach_spiky", "attach_mist", "attach_growing_grass", "attach_basic_grass",
            "search_trainer", "search_energy", "play_search", "attack", "end_turn", "gust", "switch",
        }
        return not bool(tags & allowed)

    if objective == "protect_bench_core":
        allowed = {
            "attach_mist", "search_energy", "search_pokemon", "search_trainer", "play_search", "bench_basic", "backup_route",
            "wall_preserve", "evolve_crustle", "switch", "gust", "disruption", "attack", "end_turn",
        }
        return not bool(tags & allowed)

    if objective in {"pressure_prize", "take_prize"}:
        allowed = {"attack", "gust", "play_search", "search_trainer", "switch", "attach_energy", "wall_preserve"}
        return not bool(tags & allowed)

    if objective == "resource_lock":
        allowed = {"disruption", "play_search", "search_trainer", "gust", "attack", "end_turn", "wall_preserve", "heal", "attach_spiky", "attach_mist"}
        return not bool(tags & allowed)

    if objective == "kang_engine":
        if getattr(obligations, "must_add_backup", False) or getattr(obligations, "must_not_draw", False):
            return True

    return False


def apply_decision_contract(obs, classified, snapshot, obligations, plan, deck_knowledge):
    context = getattr(obs.select, "context", None)
    hard_filter_context = context in {SelectContext.MAIN, SelectContext.ATTACK, SelectContext.ACTIVATE} or context is None

    allowed = []
    blocked = []
    for action in classified:
        reason = None
        if hard_filter_context:
            if violates_obligations(action, snapshot, obligations, plan, deck_knowledge):
                reason = "violates_obligations"
            elif violates_plan_contract(action, snapshot, obligations, plan, deck_knowledge):
                reason = "violates_plan_contract"
            elif violates_search_contract(action, snapshot, obligations, plan, deck_knowledge):
                reason = "violates_search_contract"
        else:
            if violates_search_contract(action, snapshot, obligations, plan, deck_knowledge):
                reason = "violates_search_contract"
        if reason:
            action.reason.append(reason)
            blocked.append(action)
            continue
        allowed.append(action)
    if allowed:
        try:
            setattr(plan, "_blocked_actions", blocked)  # frozen dataclass; harmless if it fails.
        except Exception:
            pass
        return allowed
    # If the strict plan filter blocks everything, relax only the plan layer first.
    # Keep hard obligations and dead/unsafe search routes as the strongest guardrails.
    relaxed = [
        action
        for action in blocked
        if "violates_obligations" not in action.reason and "violates_search_contract" not in action.reason
    ]
    if relaxed:
        return relaxed

    relaxed = [action for action in blocked if "violates_obligations" not in action.reason]
    if relaxed:
        return relaxed

    return list(classified)
