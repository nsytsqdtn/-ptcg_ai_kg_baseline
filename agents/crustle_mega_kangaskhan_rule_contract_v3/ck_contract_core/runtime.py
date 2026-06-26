from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any


def load_deck_from_csv(path: Path) -> list[int]:
    return [int(line.strip()) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def choose_safe_action(option_count: int) -> list[int]:
    if option_count <= 0:
        return []
    return [0]


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


def is_ex_card(card: Any) -> bool:
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
