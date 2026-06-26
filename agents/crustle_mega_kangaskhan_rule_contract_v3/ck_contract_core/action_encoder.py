from __future__ import annotations

from cg.api import AreaType, OptionType

from .runtime import CardIds, ENERGY_IDS, damage_taken


ACTION_FEATURE_NAMES = [
    "is_attack",
    "is_play",
    "is_attach",
    "is_evolve",
    "is_ability",
    "is_retreat",
    "is_dwebble",
    "is_crustle",
    "is_mega_kangaskhan",
    "is_energy",
    "is_growing_grass_energy",
    "is_mist_energy",
    "is_spiky_energy",
    "is_basic_grass_energy",
    "is_hilda",
    "is_lillie",
    "is_petrel",
    "is_boss_orders",
    "is_eri",
    "is_xerosic",
    "is_jumbo_ice_cream",
    "is_bianca_devotion",
    "is_lisia",
    "is_poffin",
    "is_ultra_ball",
    "is_switch",
    "is_hand_trimmer",
    "is_hero_cape",
    "is_handheld_fan",
    "target_is_crustle",
    "target_is_kangaskhan",
    "target_is_dwebble",
    "target_is_active",
    "target_is_damaged",
    "target_is_opponent_low_hp",
    "target_is_opponent_high_energy",
    "rule_setup_score",
    "rule_survival_score",
    "rule_attack_continuity_score",
    "rule_prize_score",
    "rule_disruption_score",
    "rule_resource_score",
    "rule_sequencing_score",
    "rule_risk_score",
]


def _card_flags(card_id: int) -> list[float]:
    return [
        1.0 if card_id == CardIds.DWEBBLE else 0.0,
        1.0 if card_id == CardIds.CRUSTLE else 0.0,
        1.0 if card_id == CardIds.MEGA_KANGASKHAN_EX else 0.0,
        1.0 if card_id in ENERGY_IDS else 0.0,
        1.0 if card_id == CardIds.GROW_GRASS_ENERGY else 0.0,
        1.0 if card_id == CardIds.MIST_ENERGY else 0.0,
        1.0 if card_id == CardIds.SPIKY_ENERGY else 0.0,
        1.0 if card_id == CardIds.BASIC_GRASS else 0.0,
        1.0 if card_id == CardIds.HILDA else 0.0,
        1.0 if card_id == CardIds.LILLIE else 0.0,
        1.0 if card_id == CardIds.PETREL else 0.0,
        1.0 if card_id == CardIds.BOSS_ORDERS else 0.0,
        1.0 if card_id == CardIds.ERI else 0.0,
        1.0 if card_id == CardIds.XEROSIC else 0.0,
        1.0 if card_id == CardIds.JUMBO_ICE_CREAM else 0.0,
        1.0 if card_id == CardIds.BIANCA_DEVOTION else 0.0,
        1.0 if card_id == CardIds.LISIA else 0.0,
        1.0 if card_id == CardIds.BUDDY_BUDDY_POFFIN else 0.0,
        1.0 if card_id == CardIds.ULTRA_BALL else 0.0,
        1.0 if card_id == CardIds.SWITCH else 0.0,
        1.0 if card_id == CardIds.HAND_TRIMMER else 0.0,
        1.0 if card_id == CardIds.HERO_CAPE else 0.0,
        1.0 if card_id == CardIds.HANDHELD_FAN else 0.0,
    ]


def _target_features(target, *, is_active: bool, is_opponent: bool) -> list[float]:
    if target is None:
        return [0.0] * 7
    return [
        1.0 if target.id == CardIds.CRUSTLE else 0.0,
        1.0 if target.id == CardIds.MEGA_KANGASKHAN_EX else 0.0,
        1.0 if target.id == CardIds.DWEBBLE else 0.0,
        1.0 if is_active else 0.0,
        1.0 if damage_taken(target) > 0 else 0.0,
        1.0 if is_opponent and getattr(target, "hp", 999) <= 120 else 0.0,
        1.0 if is_opponent and len(getattr(target, "energies", []) or []) >= 2 else 0.0,
    ]


def _rule_breakdown_features(prior: dict | None) -> list[float]:
    breakdown = {} if prior is None else prior.get("breakdown", {})
    def scaled(name: str) -> float:
        value = float(breakdown.get(name, 0.0))
        return max(-1.0, min(1.0, value / 100.0))
    return [
        scaled("setup"),
        scaled("survival"),
        scaled("attack_continuity"),
        scaled("prize"),
        scaled("disruption"),
        scaled("resource"),
        scaled("sequencing"),
        scaled("risk"),
    ]


def encode_action(obs, option, prior: dict | None = None) -> list[float]:
    my_index = obs.current.yourIndex
    card_id = 0
    target = None
    target_is_active = False
    target_is_opponent = False
    if option.type == OptionType.PLAY:
        card_id = obs.current.players[my_index].hand[option.index].id
    elif option.type == OptionType.ATTACH:
        card_id = obs.current.players[my_index].hand[option.index].id
        if option.inPlayArea == AreaType.ACTIVE:
            target = obs.current.players[my_index].active[option.inPlayIndex]
            target_is_active = True
        else:
            target = obs.current.players[my_index].bench[option.inPlayIndex]
    elif option.type == OptionType.EVOLVE:
        card_id = obs.current.players[my_index].hand[option.index].id
    elif option.type == OptionType.CARD:
        area = option.area
        player_state = obs.current.players[option.playerIndex]
        target_is_opponent = option.playerIndex != my_index
        if area == AreaType.ACTIVE:
            target = player_state.active[option.index]
            target_is_active = True
        elif area == AreaType.BENCH:
            target = player_state.bench[option.index]
        elif area == AreaType.HAND and option.playerIndex == my_index:
            target = player_state.hand[option.index]
    type_features = [
        1.0 if option.type == OptionType.ATTACK else 0.0,
        1.0 if option.type == OptionType.PLAY else 0.0,
        1.0 if option.type == OptionType.ATTACH else 0.0,
        1.0 if option.type == OptionType.EVOLVE else 0.0,
        1.0 if option.type == OptionType.ABILITY else 0.0,
        1.0 if option.type == OptionType.RETREAT else 0.0,
    ]
    return type_features + _card_flags(card_id) + _target_features(
        target,
        is_active=target_is_active,
        is_opponent=target_is_opponent,
    ) + _rule_breakdown_features(prior)
