from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .runtime import CardIds, energy_cards, energy_count, get_card_name_en, get_card_name_zh, has_attached

# Opponent card ids commonly seen in the local evaluators. These are not used
# as hard matchup branches; they are public card-profile facts for threat math.
DREEPY = 119
DRAKLOAK = 120
DRAGAPULT_EX = 121
RIOLU_677 = 677
MEGA_LUCARIO_EX = 678
MAKUHITA = 673
HARIYAMA = 674
LUNATONE = 675
SOLROCK = 676
ABRA = 741
KADABRA = 742
ALAKAZAM = 743
KYOGRE = 721
SNOVER = 722
MEGA_ABOMASNOW_EX = 723


@dataclass(frozen=True)
class AttackProfile:
    name: str
    damage: int
    colorless_cost: int = 0
    grass_cost: int = 0
    total_cost: int = 0
    bench_damage_counters: int = 0
    is_effect_damage: bool = False
    blocked_by_crustle_ex_wall: bool = False
    notes: str = ""

    def required_total(self) -> int:
        return max(self.total_cost, self.colorless_cost + self.grass_cost)


@dataclass(frozen=True)
class CardBattleProfile:
    card_id: int
    name_en: str
    name_zh: str
    retreat_cost: int
    attacks: tuple[AttackProfile, ...] = field(default_factory=tuple)
    has_crustle_ex_wall: bool = False
    has_kang_draw: bool = False


CARD_BATTLE_PROFILES: dict[int, CardBattleProfile] = {
    CardIds.DWEBBLE: CardBattleProfile(
        card_id=CardIds.DWEBBLE,
        name_en="Dwebble",
        name_zh="石居蟹",
        retreat_cost=2,
        attacks=(AttackProfile(name="Ascension", damage=0, colorless_cost=1, total_cost=1, notes="evolve_from_deck"),),
    ),
    CardIds.CRUSTLE: CardBattleProfile(
        card_id=CardIds.CRUSTLE,
        name_en="Crustle",
        name_zh="岩殿居蟹",
        retreat_cost=3,
        has_crustle_ex_wall=True,
        attacks=(AttackProfile(name="Crustle main attack", damage=120, grass_cost=1, colorless_cost=2, total_cost=3, notes="ignore_active_effects"),),
    ),
    CardIds.MEGA_KANGASKHAN_EX: CardBattleProfile(
        card_id=CardIds.MEGA_KANGASKHAN_EX,
        name_en="Mega Kangaskhan ex",
        name_zh="超级袋兽ex",
        retreat_cost=3,
        has_kang_draw=True,
        attacks=(AttackProfile(name="Mega Kangaskhan combo", damage=200, colorless_cost=3, total_cost=3, notes="coin_bonus_ignored_for_stable_damage"),),
    ),
    DRAGAPULT_EX: CardBattleProfile(
        card_id=DRAGAPULT_EX,
        name_en="Dragapult ex",
        name_zh="多龙巴鲁托ex",
        retreat_cost=1,
        attacks=(
            AttackProfile(name="Jet Headbutt", damage=70, colorless_cost=1, total_cost=1),
            AttackProfile(name="Phantom Dive", damage=200, total_cost=2, bench_damage_counters=6, is_effect_damage=True, notes="places 6 damage counters on bench"),
        ),
    ),
    DREEPY: CardBattleProfile(
        card_id=DREEPY,
        name_en="Dreepy",
        name_zh="多龙梅西亚",
        retreat_cost=1,
        attacks=(AttackProfile(name="Bite", damage=40, total_cost=2),),
    ),
    DRAKLOAK: CardBattleProfile(
        card_id=DRAKLOAK,
        name_en="Drakloak",
        name_zh="多龙奇",
        retreat_cost=1,
        attacks=(AttackProfile(name="Headbutt", damage=70, total_cost=2),),
    ),
    MEGA_LUCARIO_EX: CardBattleProfile(
        card_id=MEGA_LUCARIO_EX,
        name_en="Mega Lucario ex",
        name_zh="超级路卡利欧ex",
        retreat_cost=2,
        attacks=(
            AttackProfile(name="Fighting acceleration", damage=130, total_cost=1, notes="attach fighting from discard"),
            AttackProfile(name="Mega Brave", damage=270, total_cost=2),
        ),
    ),
    RIOLU_677: CardBattleProfile(
        card_id=RIOLU_677,
        name_en="Riolu",
        name_zh="利欧路",
        retreat_cost=2,
        attacks=(AttackProfile(name="Riolu attack", damage=30, total_cost=1),),
    ),
    MAKUHITA: CardBattleProfile(
        card_id=MAKUHITA,
        name_en="Makuhita",
        name_zh="幕下力士",
        retreat_cost=2,
        attacks=(AttackProfile(name="Makuhita attack", damage=30, total_cost=2),),
    ),
    HARIYAMA: CardBattleProfile(
        card_id=HARIYAMA,
        name_en="Hariyama",
        name_zh="超力王",
        retreat_cost=3,
        attacks=(AttackProfile(name="Wild Press", damage=210, total_cost=3, notes="self_damage_70"),),
    ),
    LUNATONE: CardBattleProfile(
        card_id=LUNATONE, name_en="Lunatone", name_zh="月石", retreat_cost=1,
        attacks=(AttackProfile(name="Power Gem", damage=50, total_cost=2),),
    ),
    SOLROCK: CardBattleProfile(
        card_id=SOLROCK, name_en="Solrock", name_zh="太阳岩", retreat_cost=1,
        attacks=(AttackProfile(name="Cosmo Beam", damage=70, total_cost=1, notes="fails_if_lunatone_on_bench"),),
    ),
    ABRA: CardBattleProfile(
        card_id=ABRA, name_en="Abra", name_zh="凯西", retreat_cost=1,
        attacks=(AttackProfile(name="Teleport Attack", damage=10, total_cost=1, notes="switch_self_to_bench"),),
    ),
    KADABRA: CardBattleProfile(
        card_id=KADABRA, name_en="Kadabra", name_zh="勇基拉", retreat_cost=1,
        attacks=(AttackProfile(name="Confusion", damage=30, total_cost=1),),
    ),
    ALAKAZAM: CardBattleProfile(
        card_id=ALAKAZAM, name_en="Alakazam", name_zh="胡地", retreat_cost=1,
        attacks=(AttackProfile(name="Powerful Hand", damage=160, total_cost=1, is_effect_damage=True, notes="hand_size_damage_counters_estimate"),),
    ),
    KYOGRE: CardBattleProfile(
        card_id=KYOGRE, name_en="Kyogre", name_zh="盖欧卡", retreat_cost=3,
        attacks=(AttackProfile(name="Energy Rain estimate", damage=120, total_cost=1, notes="discard_water_scaling_estimate"), AttackProfile(name="Heavy Splash", damage=130, total_cost=3)),
    ),
    SNOVER: CardBattleProfile(
        card_id=SNOVER, name_en="Snover", name_zh="雪笠怪", retreat_cost=3,
        attacks=(AttackProfile(name="Slap", damage=10, total_cost=1),),
    ),
    MEGA_ABOMASNOW_EX: CardBattleProfile(
        card_id=MEGA_ABOMASNOW_EX, name_en="Mega Abomasnow ex", name_zh="超级暴雪王ex", retreat_cost=4,
        attacks=(AttackProfile(name="Avalanche Hammer estimate", damage=200, total_cost=2, notes="mill_6_energy_scaling_estimate"), AttackProfile(name="Frost Barrier", damage=200, total_cost=3, notes="next_turn_minus_30")),
    ),

}


def card_profile(card_or_id: Any) -> CardBattleProfile | None:
    cid = card_or_id if isinstance(card_or_id, int) else getattr(card_or_id, "id", None)
    return CARD_BATTLE_PROFILES.get(cid)


def retreat_cost(card_or_id: Any) -> int | None:
    prof = card_profile(card_or_id)
    return None if prof is None else prof.retreat_cost


def energy_ids(card: Any) -> list[int]:
    ids: list[int] = []
    for e in energy_cards(card):
        cid = getattr(e, "id", e if isinstance(e, int) else None)
        if cid is not None:
            ids.append(int(cid))
    return ids


def grass_energy_count(card: Any) -> int:
    return sum(1 for cid in energy_ids(card) if cid in {CardIds.BASIC_GRASS, CardIds.GROW_GRASS_ENERGY})


def can_pay_attack(card: Any, attack: AttackProfile) -> bool:
    total = energy_count(card)
    if total < attack.required_total():
        return False
    if grass_energy_count(card) < attack.grass_cost:
        return False
    return True


def missing_energy_to_attack(card: Any, attack: AttackProfile) -> int:
    missing_total = max(0, attack.required_total() - energy_count(card))
    missing_grass = max(0, attack.grass_cost - grass_energy_count(card))
    return max(missing_total, missing_grass)


def attacks_for(card: Any) -> tuple[AttackProfile, ...]:
    prof = card_profile(card)
    if prof is not None:
        return prof.attacks
    # Generic fallback for public opponent cards that are not in the small table.
    e = energy_count(card)
    is_exish = "ex" in get_card_name_en(card).lower()
    if e >= 3:
        dmg = 240 if is_exish else 180
    elif e >= 2:
        dmg = 160 if is_exish else 110
    elif e >= 1:
        dmg = 80 if is_exish else 50
    else:
        dmg = 0
    if dmg <= 0:
        return tuple()
    return (AttackProfile(name="generic_public_attack_estimate", damage=dmg, total_cost=min(max(e, 1), 3), notes="fallback"),)


def usable_attacks_for(card: Any) -> list[AttackProfile]:
    return [atk for atk in attacks_for(card) if can_pay_attack(card, atk)]


def best_usable_attack(card: Any) -> AttackProfile | None:
    attacks = usable_attacks_for(card)
    if not attacks:
        return None
    return max(attacks, key=lambda a: (a.damage, a.bench_damage_counters))


def best_possible_attack_next_energy(card: Any) -> AttackProfile | None:
    attacks = list(attacks_for(card))
    if not attacks:
        return None
    one_away = [atk for atk in attacks if missing_energy_to_attack(card, atk) <= 1]
    if not one_away:
        return None
    return max(one_away, key=lambda a: (a.damage, a.bench_damage_counters))


def damage_blocked_by_crustle_wall(attacker: Any, defender: Any, attack: AttackProfile) -> bool:
    # Crustle prevents attack damage from opponent Pokemon ex. It does not stop
    # bench damage counters or non-damage effects.
    return getattr(defender, "id", None) == CardIds.CRUSTLE and "ex" in get_card_name_en(attacker).lower() and attack.damage > 0


def stable_damage_to_defender(attacker: Any, defender: Any, attack: AttackProfile) -> int:
    if damage_blocked_by_crustle_wall(attacker, defender, attack):
        return 0
    return attack.damage


def best_damage_to_active(attacker: Any, defender: Any) -> int:
    best = best_usable_attack(attacker)
    if best is None:
        return 0
    return stable_damage_to_defender(attacker, defender, best)


def bench_counter_damage(attack: AttackProfile) -> int:
    # Damage counters are 10 HP each.
    return int(attack.bench_damage_counters or 0) * 10
