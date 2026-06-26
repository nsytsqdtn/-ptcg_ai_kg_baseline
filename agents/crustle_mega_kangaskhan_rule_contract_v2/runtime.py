from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from cg.api import AreaType, OptionType


def load_deck_from_csv(path: Path) -> list[int]:
    return [int(line.strip()) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def choose_safe_action(option_count: int) -> list[int]:
    if option_count <= 0:
        return []
    return [0]


def safe_fallback(obs_dict: dict) -> list[int]:
    select = obs_dict.get("select") or {}
    if hasattr(select, "option"):
        options = getattr(select, "option", None) or []
    else:
        options = select.get("option") or []
    return choose_safe_action(len(options))


def make_rule_prior_result(total_logit: float, breakdown: dict[str, float], reason_tags: list[str]) -> dict[str, Any]:
    return {
        "total_logit": float(total_logit),
        "breakdown": dict(breakdown),
        "reason_tags": list(reason_tags),
    }


class CardIds:
    DWEBBLE = 344
    CRUSTLE = 345
    MEGA_KANGASKHAN_EX = 756
    BUDDY_BUDDY_POFFIN = 1086
    HAND_TRIMMER = 1087
    ULTRA_BALL = 1121
    POKEGEAR = 1122
    SWITCH = 1123
    JUMBO_ICE_CREAM = 1147
    HERO_CAPE = 1159
    HANDHELD_FAN = 1161
    BOSS_ORDERS = 1182
    ERI = 1186
    BIANCA_DEVOTION = 1190
    XEROSIC = 1197
    LISIA = 1204
    PETREL = 1219
    HILDA = 1225
    LILLIE = 1227
    COMMUNITY_CENTER = 1242
    FESTIVAL_GROUNDS = 1245
    ROCKET_FACTORY = 1257
    BASIC_GRASS = 1
    MIST_ENERGY = 11
    SPIKY_ENERGY = 14
    GROW_GRASS_ENERGY = 18


CORE_POKEMON = {
    CardIds.DWEBBLE,
    CardIds.CRUSTLE,
    CardIds.MEGA_KANGASKHAN_EX,
}
ENERGY_IDS = {
    CardIds.BASIC_GRASS,
    CardIds.MIST_ENERGY,
    CardIds.SPIKY_ENERGY,
    CardIds.GROW_GRASS_ENERGY,
}
KNOWN_EX_IDS = {
    CardIds.MEGA_KANGASKHAN_EX,
    121,  # Dragapult ex
    678,  # Mega Lucario ex
}
ROCKET_SUPPORTERS = {CardIds.PETREL}


def count_ids(cards: list[Any]) -> Counter[int]:
    counts: Counter[int] = Counter()
    for card in cards:
        if card is None:
            continue
        counts[card.id] += 1
    return counts


def get_card_name(card: Any) -> str:
    return getattr(card, "name", f"id:{getattr(card, 'id', 'unknown')}")


def get_selected_card(obs, option):
    try:
        if option.type in {OptionType.PLAY, OptionType.ATTACH}:
            return obs.current.players[obs.current.yourIndex].hand[option.index]
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


def _area_label(area) -> str:
    name = getattr(area, "name", str(area or ""))
    return str(name).replace("_", " ").title()


def describe_option(obs, option) -> str:
    card = get_selected_card(obs, option)
    card_name = get_card_name(card) if card is not None else None
    option_name = getattr(option.type, "name", str(option.type)).replace("_", " ").title()

    if option.type == OptionType.PLAY and card_name:
        return f"PLAY {card_name}"
    if option.type == OptionType.ATTACH and card_name:
        target = None
        try:
            target = get_selected_card(
                obs,
                type(
                    "TargetRef",
                    (),
                    {
                        "type": OptionType.CARD,
                        "area": option.inPlayArea,
                        "index": option.inPlayIndex,
                        "playerIndex": obs.current.yourIndex,
                    },
                )(),
            )
        except Exception:
            target = None
        target_name = get_card_name(target) if target is not None else f"{_area_label(getattr(option, 'inPlayArea', None))}:{getattr(option, 'inPlayIndex', 0)}"
        return f"ATTACH {card_name} -> {_area_label(getattr(option, 'inPlayArea', None))} {target_name}"
    if option.type == OptionType.CARD and card_name:
        return f"SELECT {card_name} from {_area_label(getattr(option, 'area', None))}"
    if option.type == OptionType.ATTACK:
        return f"ATTACK {card_name}" if card_name else "ATTACK"
    if option.type == OptionType.ABILITY:
        return f"ABILITY {card_name}" if card_name else "ABILITY"
    if option.type == OptionType.RETREAT:
        return "RETREAT"
    if option.type == OptionType.EVOLVE and card_name:
        return f"EVOLVE {card_name}"
    if option.type == OptionType.END:
        return "END TURN"
    if card_name:
        return f"{option_name.upper()} {card_name}"
    return option_name.upper()


def normalize_selection(scored, obs, require_positive: bool = True) -> list[int]:
    n = len(obs.select.option)
    minc = max(0, min(getattr(obs.select, "minCount", 1), n))
    maxc = max(minc, min(getattr(obs.select, "maxCount", 1), n))
    out: list[int] = []
    seen: set[int] = set()
    for item in scored:
        if item.index in seen:
            continue
        raw = float(item.prior.get("total_logit", item.total_logit))
        if len(out) < minc:
            out.append(item.index)
            seen.add(item.index)
        elif not require_positive or raw > 0 or item.total_logit > 0:
            out.append(item.index)
            seen.add(item.index)
        if len(out) >= maxc:
            break
    for item in scored:
        if len(out) >= minc:
            break
        if item.index not in seen:
            out.append(item.index)
            seen.add(item.index)
    return out


def is_ex_card(card: Any) -> bool:
    if card is None:
        return False
    card_id = getattr(card, "id", None)
    if card_id in KNOWN_EX_IDS:
        return True
    max_hp = getattr(card, "maxHp", None) or getattr(card, "maxHP", None) or 0
    if max_hp >= 300:
        return True
    name = get_card_name(card).lower()
    return " ex" in name or name.endswith(" ex") or " ex," in name


def is_basic_pokemon(card: Any) -> bool:
    return card.id in {CardIds.DWEBBLE, CardIds.MEGA_KANGASKHAN_EX}


def prize_count(card: Any) -> int:
    if card is None:
        return 0
    name = get_card_name(card).lower()
    if "mega " in name and " ex" in name:
        return 3
    if " ex" in name:
        return 2
    return 1


def energy_count(card: Any) -> int:
    if card is None:
        return 0
    energies = getattr(card, "energies", None)
    if energies is None:
        energies = getattr(card, "energyCards", None)
    return len(energies or [])


def damage_taken(card: Any) -> int:
    if card is None:
        return 0
    max_hp = getattr(card, "maxHp", None) or getattr(card, "maxHP", None) or 0
    hp = getattr(card, "hp", max_hp) or max_hp
    if not max_hp:
        return 0
    return max(0, max_hp - hp)


def has_tool(card: Any, tool_id: int) -> bool:
    for tool in getattr(card, "tools", []) or []:
        if tool.id == tool_id:
            return True
    return False
