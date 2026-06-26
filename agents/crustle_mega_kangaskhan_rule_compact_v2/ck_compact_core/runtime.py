from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any


class CardIds:
    # Pokemon
    DWEBBLE = 344
    CRUSTLE = 345
    MEGA_KANGASKHAN_EX = 756

    # Items / tools
    BUDDY_BUDDY_POFFIN = 1086
    HAND_TRIMMER = 1087
    ULTRA_BALL = 1121
    POKEGEAR = 1122
    SWITCH = 1123
    JUMBO_ICE_CREAM = 1147
    HERO_CAPE = 1159
    HANDHELD_FAN = 1161

    # Supporters
    BOSS_ORDERS = 1182
    ERI = 1186
    BIANCA_DEVOTION = 1190
    XEROSIC = 1197
    LISIA = 1204
    PETREL = 1219
    HILDA = 1225
    LILLIE = 1227

    # Stadiums
    COMMUNITY_CENTER = 1242
    FESTIVAL_GROUNDS = 1245
    ROCKET_FACTORY = 1257

    # Energy
    BASIC_GRASS = 1
    MIST_ENERGY = 11
    SPIKY_ENERGY = 14
    GROW_GRASS_ENERGY = 18


CORE_POKEMON = {CardIds.DWEBBLE, CardIds.CRUSTLE, CardIds.MEGA_KANGASKHAN_EX}
BASIC_POKEMON = {CardIds.DWEBBLE, CardIds.MEGA_KANGASKHAN_EX}
ENERGY_IDS = {CardIds.BASIC_GRASS, CardIds.MIST_ENERGY, CardIds.SPIKY_ENERGY, CardIds.GROW_GRASS_ENERGY}
SEARCH_CARDS = {CardIds.BUDDY_BUDDY_POFFIN, CardIds.ULTRA_BALL, CardIds.POKEGEAR, CardIds.PETREL, CardIds.HILDA}
DRAW_CARDS = {CardIds.LILLIE}
DISRUPTION_CARDS = {CardIds.ERI, CardIds.XEROSIC, CardIds.HAND_TRIMMER}
HEAL_CARDS = {CardIds.JUMBO_ICE_CREAM, CardIds.BIANCA_DEVOTION}
GUST_CARDS = {CardIds.BOSS_ORDERS, CardIds.LISIA}
STADIUM_CARDS = {CardIds.COMMUNITY_CENTER, CardIds.FESTIVAL_GROUNDS, CardIds.ROCKET_FACTORY}
TOOL_CARDS = {CardIds.HERO_CAPE, CardIds.HANDHELD_FAN}
SUPPORTER_CARDS = {CardIds.BOSS_ORDERS, CardIds.ERI, CardIds.BIANCA_DEVOTION, CardIds.XEROSIC, CardIds.LISIA, CardIds.PETREL, CardIds.HILDA, CardIds.LILLIE}

CARD_EN = {
    CardIds.DWEBBLE: "Dwebble",
    CardIds.CRUSTLE: "Crustle",
    CardIds.MEGA_KANGASKHAN_EX: "Mega Kangaskhan ex",
    CardIds.BUDDY_BUDDY_POFFIN: "Buddy-Buddy Poffin",
    CardIds.HAND_TRIMMER: "Hand Trimmer",
    CardIds.ULTRA_BALL: "Ultra Ball",
    CardIds.POKEGEAR: "Pokegear 3.0",
    CardIds.SWITCH: "Switch",
    CardIds.JUMBO_ICE_CREAM: "Jumbo Ice Cream",
    CardIds.HERO_CAPE: "Hero's Cape",
    CardIds.HANDHELD_FAN: "Handheld Fan",
    CardIds.BOSS_ORDERS: "Boss's Orders",
    CardIds.ERI: "Eri",
    CardIds.BIANCA_DEVOTION: "Bianca's Devotion",
    CardIds.XEROSIC: "Xerosic's Machinations",
    CardIds.LISIA: "Lisia's Appeal",
    CardIds.PETREL: "Team Rocket's Petrel",
    CardIds.HILDA: "Hilda",
    CardIds.LILLIE: "Lillie's Determination",
    CardIds.COMMUNITY_CENTER: "Community Center",
    CardIds.FESTIVAL_GROUNDS: "Festival Grounds",
    CardIds.ROCKET_FACTORY: "Team Rocket's Factory",
    CardIds.BASIC_GRASS: "Basic Grass Energy",
    CardIds.MIST_ENERGY: "Mist Energy",
    CardIds.SPIKY_ENERGY: "Spiky Energy",
    CardIds.GROW_GRASS_ENERGY: "Growing Grass Energy",
}

CARD_ZH = {
    CardIds.DWEBBLE: "石居蟹",
    CardIds.CRUSTLE: "岩殿居蟹",
    CardIds.MEGA_KANGASKHAN_EX: "超级袋兽ex",
    CardIds.BUDDY_BUDDY_POFFIN: "友好松饼",
    CardIds.HAND_TRIMMER: "手牌修剪器",
    CardIds.ULTRA_BALL: "高级球",
    CardIds.POKEGEAR: "宝可装置3.0",
    CardIds.SWITCH: "宝可梦交替",
    CardIds.JUMBO_ICE_CREAM: "特大冰淇淋",
    CardIds.HERO_CAPE: "英雄斗篷",
    CardIds.HANDHELD_FAN: "手持循环扇",
    CardIds.BOSS_ORDERS: "老大的指令",
    CardIds.ERI: "枇琶",
    CardIds.BIANCA_DEVOTION: "白露的真心",
    CardIds.XEROSIC: "克希洛希奇的图谋",
    CardIds.LISIA: "露琪亚的魅力展示",
    CardIds.PETREL: "火箭队的兰斯达",
    CardIds.HILDA: "斗子",
    CardIds.LILLIE: "莉莉艾的决心",
    CardIds.COMMUNITY_CENTER: "公民馆",
    CardIds.FESTIVAL_GROUNDS: "祭典会场",
    CardIds.ROCKET_FACTORY: "火箭队工厂",
    CardIds.BASIC_GRASS: "基本【草】能量",
    CardIds.MIST_ENERGY: "薄雾能量",
    CardIds.SPIKY_ENERGY: "尖刺能量",
    CardIds.GROW_GRASS_ENERGY: "成长【草】能量",
}


def load_deck_from_csv(path: Path) -> list[int]:
    return [int(line.strip()) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def choose_safe_action(option_count: int) -> list[int]:
    if option_count <= 0:
        return []
    return [0]


def count_ids(cards: list[Any]) -> Counter[int]:
    counts: Counter[int] = Counter()
    for card in cards or []:
        if card is not None:
            cid = getattr(card, "id", None)
            if cid is not None:
                counts[cid] += 1
    return counts


def get_card_name(card: Any) -> str:
    if card is None:
        return "None"
    return getattr(card, "name", CARD_EN.get(getattr(card, "id", None), f"id:{getattr(card, 'id', 'unknown')}"))


def get_card_name_en(card_or_id: Any) -> str:
    cid = card_or_id if isinstance(card_or_id, int) else getattr(card_or_id, "id", None)
    return CARD_EN.get(cid, get_card_name(card_or_id) if not isinstance(card_or_id, int) else f"id:{cid}")


def get_card_name_zh(card_or_id: Any) -> str:
    cid = card_or_id if isinstance(card_or_id, int) else getattr(card_or_id, "id", None)
    return CARD_ZH.get(cid, get_card_name_en(card_or_id))


def is_ex_card(card: Any) -> bool:
    if card is None:
        return False
    name = get_card_name(card).lower()
    return " ex" in name or name.endswith("ex") or "ex," in name


def prize_count(card: Any) -> int:
    if card is None:
        return 0
    name = get_card_name(card).lower()
    if "mega" in name and "ex" in name:
        return 3
    if " ex" in name or name.endswith("ex"):
        return 2
    return 1


def energy_cards(card: Any) -> list[Any]:
    if card is None:
        return []
    return list(getattr(card, "energies", None) or getattr(card, "energyCards", None) or [])


def energy_count(card: Any) -> int:
    return len(energy_cards(card))


def attached_card_ids(card: Any) -> list[int]:
    ids: list[int] = []
    if card is None:
        return ids
    for zone_name in ("preEvolution", "energyCards", "energies", "tools"):
        for c in getattr(card, zone_name, None) or []:
            cid = getattr(c, "id", c if isinstance(c, int) else None)
            if cid is not None:
                ids.append(int(cid))
    return ids


def has_attached(card: Any, card_id: int) -> bool:
    return card_id in attached_card_ids(card)


def max_hp(card: Any) -> int:
    if card is None:
        return 0
    return int(getattr(card, "maxHp", None) or getattr(card, "maxHP", None) or getattr(card, "hp", 0) or 0)


def hp_remaining(card: Any) -> int:
    if card is None:
        return 0
    return int(getattr(card, "hp", None) or max_hp(card) or 0)


def damage_taken(card: Any) -> int:
    return max(0, max_hp(card) - hp_remaining(card))


def is_basic_own_pokemon_id(card_id: int | None) -> bool:
    return card_id in BASIC_POKEMON


def is_core_pokemon_id(card_id: int | None) -> bool:
    return card_id in CORE_POKEMON
