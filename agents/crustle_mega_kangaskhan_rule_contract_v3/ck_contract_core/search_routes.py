from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from .runtime import CardIds, CORE_POKEMON


class RouteStatus(str, Enum):
    CONFIRMED = "confirmed"
    POSSIBLE = "possible"
    DEAD = "dead"


@dataclass(frozen=True)
class SearchRoute:
    effect_id: int
    status: RouteStatus
    targets: tuple[int, ...]
    confirmed_targets: tuple[int, ...]
    possible_targets: tuple[int, ...]
    reason: str
    value: int = 0

    @property
    def live(self) -> bool:
        return self.status in {RouteStatus.CONFIRMED, RouteStatus.POSSIBLE}


def deck_status(deck_knowledge, card_id: int) -> RouteStatus:
    if deck_knowledge is None:
        return RouteStatus.POSSIBLE
    try:
        value = deck_knowledge.deck_has(card_id)
    except Exception:
        return RouteStatus.POSSIBLE
    if value is True:
        return RouteStatus.CONFIRMED
    if value is False:
        return RouteStatus.DEAD
    return RouteStatus.POSSIBLE


def deck_has_maybe(deck_knowledge, card_id: int) -> bool:
    return deck_status(deck_knowledge, card_id) != RouteStatus.DEAD


def _unique(ids: Iterable[int]) -> tuple[int, ...]:
    seen: set[int] = set()
    out: list[int] = []
    for cid in ids or []:
        if cid in seen:
            continue
        seen.add(cid)
        out.append(cid)
    return tuple(out)


def split_live_ids(ids: Iterable[int], deck_knowledge) -> tuple[RouteStatus, tuple[int, ...], tuple[int, ...], tuple[int, ...]]:
    confirmed: list[int] = []
    possible: list[int] = []
    for cid in _unique(ids):
        status = deck_status(deck_knowledge, cid)
        if status == RouteStatus.CONFIRMED:
            confirmed.append(cid)
        elif status == RouteStatus.POSSIBLE:
            possible.append(cid)
    targets = tuple(confirmed + possible)
    if confirmed:
        return RouteStatus.CONFIRMED, targets, tuple(confirmed), tuple(possible)
    if possible:
        return RouteStatus.POSSIBLE, targets, (), tuple(possible)
    return RouteStatus.DEAD, (), (), ()


def live_ids(ids: Iterable[int], deck_knowledge) -> tuple[int, ...]:
    return split_live_ids(ids, deck_knowledge)[1]


def is_pokemon_id(card_id: int) -> bool:
    return card_id in CORE_POKEMON


def _default_poffin_targets(plan, obligations) -> tuple[int, ...]:
    targets = tuple(getattr(plan, "poffin_basic_ids", ()) or ())
    if targets:
        return targets
    return (CardIds.DWEBBLE, CardIds.MEGA_KANGASKHAN_EX)


def _default_hilda_pairs(plan, obligations) -> tuple[tuple[int, int], ...]:
    pairs = tuple(getattr(plan, "hilda_pair_preferences", ()) or ())
    if pairs:
        return pairs
    objective = getattr(plan, "objective", getattr(plan, "mode", ""))
    if getattr(obligations, "must_add_backup", False):
        return (
            (CardIds.DWEBBLE, CardIds.GROW_GRASS_ENERGY),
            (CardIds.MEGA_KANGASKHAN_EX, CardIds.SPIKY_ENERGY),
            (CardIds.DWEBBLE, CardIds.MIST_ENERGY),
        )
    if objective in {"setup_crustle_wall", "preserve_wall", "wall_control", "protect_bench_core"}:
        return (
            (CardIds.CRUSTLE, CardIds.GROW_GRASS_ENERGY),
            (CardIds.DWEBBLE, CardIds.GROW_GRASS_ENERGY),
            (CardIds.DWEBBLE, CardIds.MIST_ENERGY),
            (CardIds.CRUSTLE, CardIds.MIST_ENERGY),
            (CardIds.MEGA_KANGASKHAN_EX, CardIds.MIST_ENERGY),
        )
    if objective == "kang_engine":
        return (
            (CardIds.MEGA_KANGASKHAN_EX, CardIds.SPIKY_ENERGY),
            (CardIds.MEGA_KANGASKHAN_EX, CardIds.MIST_ENERGY),
        )
    return (
        (CardIds.DWEBBLE, CardIds.GROW_GRASS_ENERGY),
        (CardIds.CRUSTLE, CardIds.GROW_GRASS_ENERGY),
        (CardIds.MEGA_KANGASKHAN_EX, CardIds.SPIKY_ENERGY),
    )


def _default_petrel_targets(plan, obligations) -> tuple[int, ...]:
    targets = tuple(getattr(plan, "petrel_target_ids", ()) or ())
    if targets:
        return targets
    objective = getattr(plan, "objective", getattr(plan, "mode", ""))
    if getattr(obligations, "must_add_backup", False):
        return (CardIds.BUDDY_BUDDY_POFFIN, CardIds.HILDA, CardIds.ULTRA_BALL, CardIds.POKEGEAR)
    if objective == "finish":
        return (CardIds.BOSS_ORDERS, CardIds.LISIA, CardIds.PETREL)
    if objective == "prevent_loss":
        return (CardIds.JUMBO_ICE_CREAM, CardIds.BIANCA_DEVOTION, CardIds.SWITCH)
    if objective in {"setup_crustle_wall", "setup_backup", "protect_bench_core"}:
        return (CardIds.HILDA, CardIds.BUDDY_BUDDY_POFFIN, CardIds.ULTRA_BALL, CardIds.SWITCH, CardIds.POKEGEAR)
    if objective in {"wall_control", "resource_lock", "preserve_wall"}:
        return (CardIds.ERI, CardIds.XEROSIC, CardIds.HAND_TRIMMER, CardIds.HANDHELD_FAN, CardIds.JUMBO_ICE_CREAM, CardIds.BOSS_ORDERS, CardIds.LISIA)
    if objective in {"take_prize", "pressure_prize"}:
        return (CardIds.BOSS_ORDERS, CardIds.LISIA, CardIds.PETREL)
    return (CardIds.HILDA, CardIds.BUDDY_BUDDY_POFFIN, CardIds.ULTRA_BALL, CardIds.ERI)


def _default_pokegear_targets(plan, obligations) -> tuple[int, ...]:
    objective = getattr(plan, "objective", getattr(plan, "mode", ""))
    if getattr(obligations, "must_add_backup", False):
        return (CardIds.HILDA, CardIds.PETREL)
    if objective == "setup_crustle_wall":
        return (CardIds.HILDA, CardIds.PETREL)
    if objective in {"wall_control", "resource_lock", "preserve_wall"}:
        return (CardIds.ERI, CardIds.XEROSIC, CardIds.PETREL, CardIds.BOSS_ORDERS)
    if objective in {"finish", "take_prize", "pressure_prize"}:
        return (CardIds.BOSS_ORDERS, CardIds.LISIA, CardIds.PETREL)
    return (CardIds.HILDA, CardIds.PETREL, CardIds.ERI)


def _route(effect_id: int, ids: Iterable[int], deck_knowledge, reason: str, value_confirmed: int = 100, value_possible: int = 35) -> SearchRoute:
    status, targets, confirmed, possible = split_live_ids(ids, deck_knowledge)
    value = value_confirmed if status == RouteStatus.CONFIRMED else value_possible if status == RouteStatus.POSSIBLE else 0
    return SearchRoute(effect_id, status, targets, confirmed, possible, reason, value)


def resolve_search_route(effect_id: int | None, plan, obligations, deck_knowledge) -> SearchRoute:
    if effect_id == CardIds.BUDDY_BUDDY_POFFIN:
        return _route(effect_id, _default_poffin_targets(plan, obligations), deck_knowledge, "poffin_basic", 100, 45)

    if effect_id == CardIds.HILDA:
        confirmed_pairs: list[tuple[int, int]] = []
        possible_pairs: list[tuple[int, int]] = []
        for p_id, e_id in _default_hilda_pairs(plan, obligations):
            ps = deck_status(deck_knowledge, p_id)
            es = deck_status(deck_knowledge, e_id)
            if ps == RouteStatus.DEAD or es == RouteStatus.DEAD:
                continue
            if ps == RouteStatus.CONFIRMED and es == RouteStatus.CONFIRMED:
                confirmed_pairs.append((p_id, e_id))
            else:
                possible_pairs.append((p_id, e_id))
        confirmed = tuple(cid for pair in confirmed_pairs for cid in pair)
        possible = tuple(cid for pair in possible_pairs for cid in pair)
        targets = confirmed + tuple(cid for cid in possible if cid not in set(confirmed))
        if confirmed_pairs:
            status = RouteStatus.CONFIRMED
        elif possible_pairs:
            status = RouteStatus.POSSIBLE
        else:
            status = RouteStatus.DEAD
        value = 100 if status == RouteStatus.CONFIRMED else 35 if status == RouteStatus.POSSIBLE else 0
        return SearchRoute(effect_id, status, targets, confirmed, possible, "hilda_pair", value)

    if effect_id == CardIds.PETREL:
        return _route(effect_id, _default_petrel_targets(plan, obligations), deck_knowledge, "petrel_trainer", 100, 40)

    if effect_id == CardIds.ULTRA_BALL:
        ids = tuple(cid for cid in (getattr(plan, "search_target_ids", ()) or CORE_POKEMON) if is_pokemon_id(cid))
        return _route(effect_id, ids, deck_knowledge, "ultra_ball_pokemon", 100, 40)

    if effect_id == CardIds.POKEGEAR:
        # Pokegear only checks a small top-deck window, so it is never a verified route.
        base = _route(effect_id, _default_pokegear_targets(plan, obligations), deck_knowledge, "pokegear_supporter_probe", 35, 35)
        if base.status == RouteStatus.DEAD:
            return base
        return SearchRoute(effect_id, RouteStatus.POSSIBLE, base.targets, (), base.targets, base.reason, 35)

    return SearchRoute(effect_id or -1, RouteStatus.DEAD, (), (), (), "unsupported_search", 0)


def current_search_deck_ids(obs) -> set[int] | None:
    try:
        deck = getattr(getattr(obs, "select", None), "deck", None)
        if deck is None:
            return None
        return {getattr(card, "id", None) for card in deck if card is not None}
    except Exception:
        return None


def resolve_search_route_for_obs(effect_id: int | None, obs, plan, obligations, deck_knowledge) -> SearchRoute:
    """Resolve route using the current select.deck view when available.

    In an actual search-selection frame, obs.select.deck is the authoritative
    current deck view. Historical deck knowledge is only used outside that frame.
    """
    deck_ids = current_search_deck_ids(obs)
    if deck_ids is None:
        return resolve_search_route(effect_id, plan, obligations, deck_knowledge)

    base = resolve_search_route(effect_id, plan, obligations, deck_knowledge)
    if effect_id == CardIds.HILDA:
        confirmed: list[int] = []
        possible: list[int] = []
        for p_id, e_id in _default_hilda_pairs(plan, obligations):
            if p_id in deck_ids and e_id in deck_ids:
                confirmed.extend([p_id, e_id])
        if confirmed:
            targets = _unique(confirmed)
            return SearchRoute(effect_id, RouteStatus.CONFIRMED, targets, targets, (), "hilda_pair_current_deck", 120)
        return SearchRoute(effect_id, RouteStatus.DEAD, (), (), (), "hilda_pair_not_in_current_deck", 0)

    if effect_id == CardIds.BUDDY_BUDDY_POFFIN:
        ids = [cid for cid in _default_poffin_targets(plan, obligations) if cid in deck_ids]
        if ids:
            targets = _unique(ids)
            return SearchRoute(effect_id, RouteStatus.CONFIRMED, targets, targets, (), "poffin_current_deck", 120)
        return SearchRoute(effect_id, RouteStatus.DEAD, (), (), (), "poffin_not_in_current_deck", 0)

    if effect_id == CardIds.PETREL:
        ids = [cid for cid in _default_petrel_targets(plan, obligations) if cid in deck_ids]
        if ids:
            targets = _unique(ids)
            return SearchRoute(effect_id, RouteStatus.CONFIRMED, targets, targets, (), "petrel_current_deck", 120)
        return SearchRoute(effect_id, RouteStatus.DEAD, (), (), (), "petrel_not_in_current_deck", 0)

    if effect_id == CardIds.ULTRA_BALL:
        base_ids = tuple(cid for cid in (getattr(plan, "search_target_ids", ()) or CORE_POKEMON) if is_pokemon_id(cid))
        ids = [cid for cid in base_ids if cid in deck_ids]
        if ids:
            targets = _unique(ids)
            return SearchRoute(effect_id, RouteStatus.CONFIRMED, targets, targets, (), "ultra_ball_current_deck", 120)
        return SearchRoute(effect_id, RouteStatus.DEAD, (), (), (), "ultra_ball_not_in_current_deck", 0)

    # Pokegear/unsupported search effects do not expose full deck target certainty.
    return base
