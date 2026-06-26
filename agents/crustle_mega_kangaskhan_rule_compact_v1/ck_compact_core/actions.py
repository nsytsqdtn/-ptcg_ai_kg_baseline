from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from cg.api import AreaType, OptionType

from .runtime import (
    CardIds,
    DISRUPTION_CARDS,
    DRAW_CARDS,
    ENERGY_IDS,
    GUST_CARDS,
    HEAL_CARDS,
    SEARCH_CARDS,
    STADIUM_CARDS,
    TOOL_CARDS,
    SUPPORTER_CARDS,
    get_card_name_en,
    get_card_name_zh,
    is_core_pokemon_id,
)


@dataclass
class ActionView:
    index: int
    option: Any
    kind: str
    card_id: int | None = None
    card_name_en: str | None = None
    card_name_zh: str | None = None
    target_id: int | None = None
    target_name_en: str | None = None
    target_name_zh: str | None = None
    tags: set[str] = field(default_factory=set)
    reason: list[str] = field(default_factory=list)

    def has(self, tag: str) -> bool:
        return tag in self.tags


def get_card_for_option(obs: Any, option: Any) -> Any | None:
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
            if option.area == AreaType.DECK:
                return obs.select.deck[option.index]
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
        if option.type in {OptionType.TOOL_CARD, OptionType.ENERGY_CARD}:
            ps = state.players[getattr(option, "playerIndex", yi)]
            pokemon = None
            if option.area == AreaType.ACTIVE:
                pokemon = ps.active[option.index]
            elif option.area == AreaType.BENCH:
                pokemon = ps.bench[option.index]
            if pokemon is None:
                return None
            if option.type == OptionType.TOOL_CARD:
                return (getattr(pokemon, "tools", []) or [None])[option.toolIndex]
            return (getattr(pokemon, "energyCards", None) or getattr(pokemon, "energies", []) or [None])[option.energyIndex]
    except Exception:
        return None
    return None


def get_attach_target(obs: Any, option: Any) -> Any | None:
    try:
        ps = obs.current.players[obs.current.yourIndex]
        if option.inPlayArea == AreaType.ACTIVE:
            return ps.active[option.inPlayIndex]
        if option.inPlayArea == AreaType.BENCH:
            return ps.bench[option.inPlayIndex]
    except Exception:
        return None
    return None


def classify_action(obs: Any, index: int, state: Any) -> ActionView:
    option = obs.select.option[index]
    kind = str(getattr(option, "type", "UNKNOWN")).split(".")[-1]
    action = ActionView(index=index, option=option, kind=kind)
    tags = action.tags
    card = get_card_for_option(obs, option)
    if card is not None:
        action.card_id = getattr(card, "id", None)
        action.card_name_en = get_card_name_en(card)
        action.card_name_zh = get_card_name_zh(card)

    if option.type == OptionType.END:
        tags.update({"end_turn"})
        return action

    if option.type == OptionType.ATTACK:
        tags.update({"attack", "end_turn"})
        if state.dwebble_active:
            tags.add("ascension_attack")
        return action

    if option.type == OptionType.RETREAT:
        tags.update({"retreat", "switch"})
        return action

    if option.type == OptionType.PLAY and card is not None:
        cid = card.id
        if cid == CardIds.DWEBBLE:
            tags.update({"bench_basic", "play_pokemon", "dwebble"})
        elif cid == CardIds.MEGA_KANGASKHAN_EX:
            tags.update({"bench_basic", "play_pokemon", "kang"})
        elif cid == CardIds.CRUSTLE:
            tags.update({"evolve_crustle", "play_pokemon"})

        if cid in SEARCH_CARDS:
            tags.update({"play_search"})
            if cid == CardIds.BUDDY_BUDDY_POFFIN:
                tags.add("search_basic")
            elif cid == CardIds.ULTRA_BALL:
                tags.add("search_pokemon")
            elif cid == CardIds.HILDA:
                tags.update({"search_pokemon", "search_energy", "supporter"})
            elif cid == CardIds.PETREL:
                tags.update({"search_trainer", "supporter"})
            elif cid == CardIds.POKEGEAR:
                tags.update({"search_trainer", "topdeck_probe"})

        if cid in DRAW_CARDS:
            tags.update({"draw", "supporter"})
        if cid in DISRUPTION_CARDS:
            tags.update({"disruption"})
            if cid in SUPPORTER_CARDS:
                tags.add("supporter")
        if cid in HEAL_CARDS:
            tags.update({"heal"})
            if cid in SUPPORTER_CARDS:
                tags.add("supporter")
        if cid in GUST_CARDS:
            tags.update({"gust", "supporter"})
        if cid == CardIds.SWITCH:
            tags.add("switch")
        if cid in TOOL_CARDS:
            tags.add("tool")
            if cid == CardIds.HERO_CAPE:
                tags.add("hp_tool")
            if cid == CardIds.HANDHELD_FAN:
                tags.add("energy_disrupt_tool")
        if cid in STADIUM_CARDS:
            tags.add("stadium")
        return action

    if option.type == OptionType.ATTACH and card is not None:
        cid = card.id
        target = get_attach_target(obs, option)
        target_id = getattr(target, "id", None)
        action.target_id = target_id
        action.target_name_en = get_card_name_en(target) if target is not None else None
        action.target_name_zh = get_card_name_zh(target) if target is not None else None
        if cid in ENERGY_IDS:
            tags.update({"attach_energy"})
        if cid == CardIds.MIST_ENERGY:
            tags.add("attach_mist")
        elif cid == CardIds.SPIKY_ENERGY:
            tags.add("attach_spiky")
        elif cid == CardIds.GROW_GRASS_ENERGY:
            tags.add("attach_growing_grass")
        elif cid == CardIds.BASIC_GRASS:
            tags.add("attach_basic_grass")
        if getattr(option, "inPlayArea", None) == AreaType.ACTIVE:
            tags.add("target_active")
        elif getattr(option, "inPlayArea", None) == AreaType.BENCH:
            tags.add("target_bench")
        if target_id == CardIds.CRUSTLE:
            tags.add("target_crustle")
        elif target_id == CardIds.MEGA_KANGASKHAN_EX:
            tags.add("target_kang")
        elif target_id == CardIds.DWEBBLE:
            tags.add("target_dwebble")
        if is_core_pokemon_id(target_id):
            tags.add("target_core")
        return action

    if option.type == OptionType.EVOLVE and card is not None:
        if card.id == CardIds.CRUSTLE:
            tags.update({"evolve_crustle"})
        return action

    if option.type == OptionType.ABILITY:
        if action.card_id == CardIds.MEGA_KANGASKHAN_EX:
            tags.add("draw")
            tags.add("kang_ability")
        return action

    if option.type == OptionType.CARD and card is not None:
        cid = card.id
        if cid == CardIds.DWEBBLE:
            tags.update({"bench_basic", "dwebble", "search_pokemon"})
        elif cid == CardIds.MEGA_KANGASKHAN_EX:
            tags.update({"bench_basic", "kang", "search_pokemon"})
        elif cid == CardIds.CRUSTLE:
            tags.update({"evolve_crustle", "search_pokemon", "switch_to_crustle"})
        if cid in ENERGY_IDS:
            tags.add("search_energy")
        if cid == CardIds.MIST_ENERGY:
            tags.add("attach_mist")
        if cid == CardIds.GROW_GRASS_ENERGY:
            tags.add("attach_growing_grass")
        if cid == CardIds.BASIC_GRASS:
            tags.add("attach_basic_grass")
        if cid in GUST_CARDS:
            tags.add("gust")
        if cid in DISRUPTION_CARDS:
            tags.add("disruption")
        if getattr(option, "playerIndex", state.my_index) != state.my_index:
            tags.add("opponent_target")
            tags.add("gust_target")
        return action

    if option.type == OptionType.YES:
        tags.add("yes")
        return action
    if option.type == OptionType.NO:
        tags.add("no")
        return action

    return action


def classify_actions(obs: Any, state: Any) -> list[ActionView]:
    return [classify_action(obs, i, state) for i in range(len(getattr(obs.select, "option", []) or []))]
