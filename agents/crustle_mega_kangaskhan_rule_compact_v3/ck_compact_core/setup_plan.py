from __future__ import annotations

from dataclasses import dataclass, field

from .runtime import CardIds


@dataclass
class SetupPlan:
    need_backup: bool
    need_dwebble: bool
    need_crustle: bool
    need_crustle_active: bool
    need_energy_for_crustle: bool
    allow_ascension: bool
    priority_cards: list[int] = field(default_factory=list)
    reason: str = ""


def build_setup_plan(state) -> SetupPlan:
    # Keep the compact backup rule small, but account for a likely KO on the
    # current Active. This is meant to reduce no-active losses without returning
    # to the older T1-T5 over-protection rule.
    need_backup = (
        state.field_count <= 1
        or (state.turn <= 3 and state.field_count < 2)
        or (
            state.active_under_threat
            and state.field_count <= 2
            and state.bench_space > 0
            and not state.current_active_damage_blocked
        )
    )
    need_dwebble = not state.has_dwebble and not state.has_crustle
    need_crustle = state.has_dwebble and not state.has_crustle
    need_crustle_active = state.has_crustle and not state.crustle_active and state.opponent_active_is_ex and not state.opponent_threat.non_ex_wall_breaker_ready
    # Crustle attack costs Grass + two colorless. For setup, a Dwebble/Crustle line
    # with fewer than 3 attached energy still wants energy preparation.
    need_energy_for_crustle = (state.has_dwebble or state.has_crustle) and not state.crustle_attack_ready
    allow_ascension = bool(state.dwebble_active and state.field_count >= 2 and not state.deck_danger)

    priority: list[int] = []
    reasons: list[str] = []
    if need_backup:
        reasons.append("need_backup")
        priority += [CardIds.DWEBBLE, CardIds.BUDDY_BUDDY_POFFIN, CardIds.ULTRA_BALL, CardIds.PETREL, CardIds.POKEGEAR, CardIds.MEGA_KANGASKHAN_EX]
    if need_dwebble:
        reasons.append("need_dwebble")
        priority += [CardIds.DWEBBLE, CardIds.BUDDY_BUDDY_POFFIN, CardIds.ULTRA_BALL, CardIds.PETREL, CardIds.POKEGEAR]
    if need_crustle:
        reasons.append("need_crustle")
        priority += [CardIds.CRUSTLE, CardIds.HILDA, CardIds.ULTRA_BALL, CardIds.PETREL]
    if need_crustle_active:
        reasons.append("need_crustle_active")
        priority += [CardIds.SWITCH, CardIds.CRUSTLE]
    if need_energy_for_crustle:
        reasons.append("need_energy_for_crustle")
        priority += [CardIds.GROW_GRASS_ENERGY, CardIds.BASIC_GRASS, CardIds.HILDA, CardIds.MIST_ENERGY]

    # Keep order but drop duplicates.
    seen = set()
    priority_cards = []
    for cid in priority:
        if cid not in seen:
            priority_cards.append(cid); seen.add(cid)

    return SetupPlan(
        need_backup=need_backup,
        need_dwebble=need_dwebble,
        need_crustle=need_crustle,
        need_crustle_active=need_crustle_active,
        need_energy_for_crustle=need_energy_for_crustle,
        allow_ascension=allow_ascension,
        priority_cards=priority_cards,
        reason=";".join(reasons) if reasons else "setup_stable",
    )
