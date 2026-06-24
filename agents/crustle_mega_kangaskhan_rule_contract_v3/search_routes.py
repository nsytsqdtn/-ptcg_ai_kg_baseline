from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from runtime import CardIds, ENERGY_IDS, CORE_POKEMON


@dataclass(frozen=True)
class SearchRoute:
    effect_id: int
    live: bool
    targets: tuple[int, ...]
    reason: str
    value: int = 0


def deck_has_maybe(deck_knowledge, card_id: int) -> bool:
    if deck_knowledge is None:
        return True
    try:
        return deck_knowledge.deck_has(card_id) is True
    except Exception:
        return False


def live_ids(ids: Iterable[int], deck_knowledge) -> tuple[int, ...]:
    seen: set[int] = set()
    out: list[int] = []
    for cid in ids or []:
        if cid in seen:
            continue
        seen.add(cid)
        if deck_has_maybe(deck_knowledge, cid):
            out.append(cid)
    return tuple(out)


def is_pokemon_id(card_id: int) -> bool:
    return card_id in CORE_POKEMON


def _default_poffin_targets(plan, obligations) -> tuple[int, ...]:
    targets = tuple(getattr(plan, "poffin_basic_ids", ()) or ())
    if targets:
        return targets
    if getattr(obligations, "must_add_backup", False):
        return (CardIds.DWEBBLE, CardIds.MEGA_KANGASKHAN_EX)
    if getattr(plan, "objective", getattr(plan, "mode", "")) in {"setup_crustle_wall", "preserve_wall", "protect_bench_core"}:
        return (CardIds.DWEBBLE, CardIds.MEGA_KANGASKHAN_EX)
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
    if objective in {"setup_crustle_wall", "preserve_wall", "protect_bench_core"}:
        return (
            (CardIds.CRUSTLE, CardIds.GROW_GRASS_ENERGY),
            (CardIds.DWEBBLE, CardIds.GROW_GRASS_ENERGY),
            (CardIds.DWEBBLE, CardIds.MIST_ENERGY),
            (CardIds.CRUSTLE, CardIds.MIST_ENERGY),
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
        return (CardIds.BUDDY_BUDDY_POFFIN, CardIds.HILDA, CardIds.ULTRA_BALL)
    if objective == "finish":
        return (CardIds.BOSS_ORDERS, CardIds.LISIA)
    if objective == "prevent_loss":
        return (CardIds.JUMBO_ICE_CREAM, CardIds.BIANCA_DEVOTION, CardIds.SWITCH)
    if objective in {"setup_crustle_wall", "setup_backup", "protect_bench_core"}:
        return (CardIds.HILDA, CardIds.BUDDY_BUDDY_POFFIN, CardIds.ULTRA_BALL, CardIds.SWITCH)
    if objective == "preserve_wall":
        return (CardIds.ERI, CardIds.XEROSIC, CardIds.HAND_TRIMMER, CardIds.HANDHELD_FAN, CardIds.JUMBO_ICE_CREAM)
    return (CardIds.HILDA, CardIds.BUDDY_BUDDY_POFFIN, CardIds.ULTRA_BALL)


def resolve_search_route(effect_id: int, plan, obligations, deck_knowledge) -> SearchRoute:
    if effect_id == CardIds.BUDDY_BUDDY_POFFIN:
        targets = live_ids(_default_poffin_targets(plan, obligations), deck_knowledge)
        return SearchRoute(effect_id, bool(targets), targets, "poffin_basic", 100)

    if effect_id == CardIds.HILDA:
        pairs = []
        for p_id, e_id in _default_hilda_pairs(plan, obligations):
            if deck_has_maybe(deck_knowledge, p_id) and deck_has_maybe(deck_knowledge, e_id):
                pairs.append((p_id, e_id))
        targets = tuple(cid for pair in pairs for cid in pair)
        return SearchRoute(effect_id, bool(pairs), targets, "hilda_pair", 100)

    if effect_id == CardIds.PETREL:
        targets = live_ids(_default_petrel_targets(plan, obligations), deck_knowledge)
        return SearchRoute(effect_id, bool(targets), targets, "petrel_trainer", 100)

    if effect_id == CardIds.ULTRA_BALL:
        targets = tuple(cid for cid in live_ids(getattr(plan, "search_target_ids", ()) or CORE_POKEMON, deck_knowledge) if is_pokemon_id(cid))
        return SearchRoute(effect_id, bool(targets), targets, "ultra_ball_pokemon", 100)

    return SearchRoute(effect_id, False, (), "unsupported_search", 0)
