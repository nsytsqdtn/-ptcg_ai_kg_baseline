from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class WallPlan:
    status: str
    opponent_wallable: bool
    need_heal_wall: bool
    need_heal_kang: bool
    need_protect_core: bool
    need_stop_energy: bool
    need_stop_hand: bool
    preferred_response: str
    reason: str
    leak_reasons: list[str] = field(default_factory=list)


def build_wall_plan(state) -> WallPlan:
    raw_status = state.wall_status
    opponent_wallable = bool(state.crustle_active and state.opponent_active_is_ex)
    need_heal_wall = bool(state.crustle_active and state.active_view is not None and state.active_view.hp <= 80)
    need_heal_kang = bool(state.kang_active and state.active_view is not None and state.active_view.hp <= 120)

    # Conservative bench protection: damaged/low-HP core bench is real pressure;
    # merely lacking Mist Energy is not enough to hijack the turn plan.
    need_protect_core = bool(
        raw_status in {"online", "leaky"}
        and (state.has_low_hp_core_bench or (state.has_damaged_core_bench and state.opponent_active_energy_count >= 2))
    )
    need_stop_energy = bool(raw_status in {"online", "leaky"} and state.opponent_active_energy_count >= 2)
    need_stop_hand = bool(raw_status in {"online", "leaky"} and state.opponent_hand_count >= 5)

    status = raw_status
    if raw_status == "leaky" and (state.active_under_threat or need_protect_core):
        status = "broken"

    if need_heal_wall or need_heal_kang:
        response = "heal"
    elif need_stop_energy:
        response = "energy_disrupt"
    elif need_protect_core:
        response = "protect_core"
    elif need_stop_hand:
        response = "hand_disrupt"
    else:
        response = "wait_or_small_pressure"

    reasons = []
    if opponent_wallable:
        reasons.append("opponent_active_wallable")
    if status == "broken":
        reasons.append("wall_broken_or_leaky")
    if need_heal_wall:
        reasons.append("heal_wall")
    if need_heal_kang:
        reasons.append("heal_kang")
    if need_protect_core:
        reasons.append("protect_core")
    if need_stop_energy:
        reasons.append("stop_energy")
    if need_stop_hand:
        reasons.append("stop_hand")
    for reason in state.wall_leak_reasons:
        if reason not in reasons:
            reasons.append(reason)

    return WallPlan(
        status=status,
        opponent_wallable=opponent_wallable,
        need_heal_wall=need_heal_wall,
        need_heal_kang=need_heal_kang,
        need_protect_core=need_protect_core,
        need_stop_energy=need_stop_energy,
        need_stop_hand=need_stop_hand,
        preferred_response=response,
        reason=";".join(reasons) if reasons else status,
        leak_reasons=list(state.wall_leak_reasons),
    )
