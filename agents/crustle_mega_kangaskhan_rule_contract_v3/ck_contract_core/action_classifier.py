from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from cg.api import AreaType, OptionType
from .runtime import CardIds, ENERGY_IDS, CORE_POKEMON, energy_count, get_card_name
from .search_routes import resolve_search_route

SEARCH_CARDS = {CardIds.BUDDY_BUDDY_POFFIN, CardIds.HILDA, CardIds.PETREL, CardIds.ULTRA_BALL, CardIds.POKEGEAR}
DRAW_CARDS = {CardIds.LILLIE}
DISRUPTION_CARDS = {CardIds.ERI, CardIds.XEROSIC, CardIds.HAND_TRIMMER}
HEAL_CARDS = {CardIds.JUMBO_ICE_CREAM, CardIds.BIANCA_DEVOTION}
GUST_CARDS = {CardIds.BOSS_ORDERS, CardIds.LISIA}
STADIUM_CARDS = {CardIds.COMMUNITY_CENTER, CardIds.FESTIVAL_GROUNDS, CardIds.ROCKET_FACTORY}


@dataclass
class ClassifiedAction:
    index: int
    option: Any
    score_hint: float = 0.0
    tags: set[str] = field(default_factory=set)
    card_id: int | None = None
    target_id: int | None = None
    draw_cost: int = 0
    reason: list[str] = field(default_factory=list)


def get_card_for_option(obs, option):
    try:
        state = obs.current
        yi = state.yourIndex
        if option.type == OptionType.PLAY:
            return state.players[yi].hand[option.index]
        if option.type == OptionType.ATTACH:
            if option.area == AreaType.HAND:
                return state.players[yi].hand[option.index]
            if option.area == AreaType.DECK:
                return obs.select.deck[option.index]
        if option.type == OptionType.EVOLVE:
            if option.area == AreaType.HAND:
                return state.players[yi].hand[option.index]
        if option.type == OptionType.ABILITY:
            ps = state.players[getattr(option, "playerIndex", yi)]
            if option.area == AreaType.ACTIVE:
                return ps.active[option.index]
            if option.area == AreaType.BENCH:
                return ps.bench[option.index]
        if option.type == OptionType.CARD:
            ps = state.players[getattr(option, "playerIndex", yi)]
            if option.area == AreaType.HAND:
                return ps.hand[option.index]
            if option.area == AreaType.DECK:
                return obs.select.deck[option.index]
            if option.area == AreaType.ACTIVE:
                return ps.active[option.index]
            if option.area == AreaType.BENCH:
                return ps.bench[option.index]
            if option.area == AreaType.LOOKING:
                return obs.current.looking[option.index]
    except Exception:
        return None
    return None


def get_attach_target(obs, option):
    try:
        ps = obs.current.players[obs.current.yourIndex]
        if option.inPlayArea == AreaType.ACTIVE:
            return ps.active[option.inPlayIndex]
        if option.inPlayArea == AreaType.BENCH:
            return ps.bench[option.inPlayIndex]
    except Exception:
        return None
    return None


def _attack_is_dwebble_ascension(snapshot, option) -> bool:
    # Attack IDs are unstable across generated metadata; if active is Dwebble and
    # the attack is legal while the plan is not a real damage plan, treat it as an
    # end-turn Ascension candidate for safety purposes.
    return bool(getattr(snapshot, "active_is_dwebble", False))


def _ability_draw_cost(card_id: int | None) -> int:
    if card_id == CardIds.MEGA_KANGASKHAN_EX:
        return 2
    return 0


def classify_action(obs, index: int, snapshot, obligations, plan, deck_knowledge) -> ClassifiedAction:
    option = obs.select.option[index]
    action = ClassifiedAction(index=index, option=option)
    tags = action.tags
    card = get_card_for_option(obs, option)
    if card is not None:
        action.card_id = getattr(card, "id", None)

    if option.type == OptionType.END:
        tags.update({"end_turn"})
        return action

    if option.type == OptionType.ATTACK:
        tags.update({"attack", "end_turn"})
        if _attack_is_dwebble_ascension(snapshot, option):
            tags.add("ascension_attack")
        return action

    if option.type == OptionType.RETREAT:
        tags.update({"retreat", "switch"})
        return action

    if option.type == OptionType.PLAY and card is not None:
        cid = card.id
        if cid in {CardIds.DWEBBLE, CardIds.MEGA_KANGASKHAN_EX}:
            tags.update({"bench_basic", "backup_route"})
        if cid == CardIds.CRUSTLE:
            tags.update({"evolve_crustle", "wall_preserve"})
        if cid in SEARCH_CARDS:
            tags.update({"play_search", "resource_spend"})
            route = resolve_search_route(cid, plan, obligations, deck_knowledge)
            if route.live:
                tags.add("backup_route") if any(t in {CardIds.DWEBBLE, CardIds.MEGA_KANGASKHAN_EX} for t in route.targets) else None
            if cid == CardIds.BUDDY_BUDDY_POFFIN:
                tags.add("search_basic")
            elif cid == CardIds.HILDA:
                tags.update({"search_pokemon", "search_energy", "play_supporter"})
            elif cid == CardIds.PETREL:
                tags.update({"search_trainer", "play_supporter"})
            elif cid == CardIds.POKEGEAR:
                tags.update({"search_trainer"})
            elif cid == CardIds.ULTRA_BALL:
                tags.add("search_pokemon")
        if cid in DRAW_CARDS:
            tags.update({"draw_deck", "play_draw", "play_supporter"})
            action.draw_cost = 4
        if cid in DISRUPTION_CARDS:
            tags.update({"disruption", "resource_spend"})
            if cid in {CardIds.ERI, CardIds.XEROSIC}:
                tags.add("play_supporter")
        if cid in HEAL_CARDS:
            tags.update({"heal", "resource_spend"})
            if cid == CardIds.BIANCA_DEVOTION:
                tags.add("play_supporter")
        if cid in GUST_CARDS:
            tags.update({"gust", "resource_spend", "play_supporter"})
        if cid == CardIds.SWITCH:
            tags.update({"switch", "resource_spend"})
        if cid in STADIUM_CARDS:
            tags.update({"play_stadium", "resource_spend"})
        return action

    if option.type == OptionType.ATTACH and card is not None:
        cid = card.id
        target = get_attach_target(obs, option)
        target_id = getattr(target, "id", None)
        action.target_id = target_id
        tags.update({"attach_energy" if cid in ENERGY_IDS else "resource_spend"})
        if cid == CardIds.MIST_ENERGY:
            tags.add("attach_mist")
            if target_id in {CardIds.DWEBBLE, CardIds.CRUSTLE, CardIds.MEGA_KANGASKHAN_EX}:
                tags.add("attach_mist_core")
            if getattr(option, "inPlayArea", None) == AreaType.BENCH:
                tags.add("attach_to_bench")
            if target_id == CardIds.DWEBBLE:
                tags.add("attach_to_dwebble")
            elif target_id == CardIds.CRUSTLE:
                tags.add("attach_to_crustle")
            elif target_id == CardIds.MEGA_KANGASKHAN_EX:
                tags.add("attach_to_kang")
        elif cid == CardIds.GROW_GRASS_ENERGY:
            tags.add("attach_growing_grass")
        elif cid == CardIds.SPIKY_ENERGY:
            tags.add("attach_spiky")
        elif cid == CardIds.BASIC_GRASS:
            tags.add("attach_basic_grass")
        if target_id == CardIds.CRUSTLE:
            tags.add("wall_preserve")
        return action

    if option.type == OptionType.EVOLVE and card is not None:
        if card.id == CardIds.CRUSTLE:
            tags.update({"evolve_crustle", "wall_preserve"})
        return action

    if option.type == OptionType.ABILITY:
        cid = action.card_id
        cost = _ability_draw_cost(cid)
        if cost:
            tags.add("draw_deck")
            action.draw_cost = cost
        return action

    if option.type == OptionType.CARD and card is not None:
        cid = card.id
        action.card_id = cid
        context = getattr(obs.select, "context", None)
        if cid in {CardIds.DWEBBLE, CardIds.MEGA_KANGASKHAN_EX}:
            tags.update({"bench_basic", "backup_route"})
        if cid == CardIds.CRUSTLE:
            tags.update({"evolve_crustle", "wall_preserve", "switch_to_crustle"})
        if cid == CardIds.MEGA_KANGASKHAN_EX:
            tags.add("switch_to_kang")
        if cid in CORE_POKEMON:
            tags.add("search_pokemon")
        if cid in ENERGY_IDS:
            tags.add("search_energy")
        if cid == CardIds.MIST_ENERGY:
            tags.add("attach_mist")
        if cid == CardIds.GROW_GRASS_ENERGY:
            tags.add("attach_growing_grass")
        # Target selection from opponent bench after Boss/Lisia.
        if getattr(option, "playerIndex", obs.current.yourIndex) != obs.current.yourIndex:
            tags.add("gust_target")
        return action

    return action


def classify_actions(obs, indices, snapshot, obligations, plan, deck_knowledge) -> list[ClassifiedAction]:
    return [classify_action(obs, i, snapshot, obligations, plan, deck_knowledge) for i in indices]
