from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .runtime import CardIds, energy_count, has_attached


@dataclass
class PrizePlan:
    available: bool = False
    confidence: str = "none"     # confirmed / possible / none
    attacker_slot: str | None = None
    attacker_name: str | None = None
    attacker_card_id: int | None = None
    target_slot: str | None = None
    target_name: str | None = None
    target_card_id: int | None = None
    damage: int = 0
    prize_gain: int = 0
    route: str = "none"          # direct / boss / lisia / petrel_to_boss / none
    need_switch: bool = False
    need_energy: bool = False
    breaks_wall: bool = False
    wins_game: bool = False
    reason: str = "no_prize_plan"

    # Non-KO pressure is intentionally secondary. It is used only inside WallPlan
    # scoring so it cannot hijack setup or a stable wall the way older pressure
    # rules did.
    pressure_available: bool = False
    pressure_attacker_card_id: int | None = None
    pressure_target_card_id: int | None = None
    pressure_damage: int = 0
    pressure_need_energy: bool = False
    pressure_reason: str = "no_pressure"


def build_prize_plan(state, actions=None) -> PrizePlan:
    actions = actions or []
    candidates: list[PrizePlan] = []
    attackers = _candidate_attackers(state, actions)
    best_pressure = _build_pressure_hint(state, attackers)

    for attacker in attackers:
        attacker_id, attacker_name, attacker_slot, damage, need_switch, need_energy, attacker_confidence = attacker
        if damage <= 0:
            continue
        breaks_wall = bool(state.crustle_active and attacker_id != CardIds.CRUSTLE and need_switch)

        # Direct active target does not need gust. If the attacker is active and
        # only needs one legal attachment, this is a confirmed two-step line:
        # attach now, then attack in the next decision of the same turn.
        if state.opponent_active_view is not None and damage >= state.opponent_active_view.hp:
            prize = state.opponent_active_view.prize_value
            confidence = attacker_confidence
            candidates.append(PrizePlan(
                available=True,
                confidence=confidence,
                attacker_slot=attacker_slot,
                attacker_name=attacker_name,
                attacker_card_id=attacker_id,
                target_slot="active",
                target_name=state.opponent_active_view.name_en,
                target_card_id=state.opponent_active_view.card_id,
                damage=damage,
                prize_gain=prize,
                route="direct",
                need_switch=need_switch,
                need_energy=need_energy,
                breaks_wall=breaks_wall,
                wins_game=prize >= state.my_prizes_left,
                reason="direct_ko" if not need_energy else "attach_then_direct_ko",
            ))

        # Bench targets require a gust route. Hand Boss is confirmed. Lisia is
        # confirmed only for targets heuristically treated as Basic. Petrel is a
        # Supporter too, so Petrel -> Boss/Lisia is not a same-turn confirmed KO;
        # keep it possible only as future pressure.
        for target in state.opponent_targets:
            if target.slot != "bench" or damage < target.hp:
                continue
            route, gust_confidence = _gust_route_for_target(state, target)
            if route == "none":
                continue
            confidence = _combine_confidence(attacker_confidence, gust_confidence)
            prize = target.prize_value
            candidates.append(PrizePlan(
                available=True,
                confidence=confidence,
                attacker_slot=attacker_slot,
                attacker_name=attacker_name,
                attacker_card_id=attacker_id,
                target_slot="bench",
                target_name=target.name_en,
                target_card_id=target.card_id,
                damage=damage,
                prize_gain=prize,
                route=route,
                need_switch=need_switch,
                need_energy=need_energy,
                breaks_wall=breaks_wall,
                wins_game=prize >= state.my_prizes_left and confidence == "confirmed",
                reason=f"{route}_bench_ko" if not need_energy else f"attach_then_{route}_bench_ko",
            ))

    if not candidates:
        return best_pressure
    best = max(candidates, key=_prize_plan_value)
    # Preserve the pressure hint for WallPlan even when a speculative KO route
    # exists but is not selected by choose_plan due confidence/risk.
    best.pressure_available = best_pressure.pressure_available
    best.pressure_attacker_card_id = best_pressure.pressure_attacker_card_id
    best.pressure_target_card_id = best_pressure.pressure_target_card_id
    best.pressure_damage = best_pressure.pressure_damage
    best.pressure_need_energy = best_pressure.pressure_need_energy
    best.pressure_reason = best_pressure.pressure_reason
    return best


def _candidate_attackers(state, actions) -> list[tuple[int, str, str, int, bool, bool, str]]:
    out: list[tuple[int, str, str, int, bool, bool, str]] = []
    # Tuple: card_id, name, slot, damage, need_switch, need_energy, confidence.
    if state.active is not None:
        active_energy = energy_count(state.active)
        if state.active_id == CardIds.CRUSTLE:
            if state.can_attack_now:
                out.append((CardIds.CRUSTLE, "Crustle", "active", 120, False, False, "confirmed"))
            elif active_energy == 2 and _has_attach_to_attacker(actions, CardIds.CRUSTLE, require_grass=not _has_grass_energy(state.active), active_only=True):
                out.append((CardIds.CRUSTLE, "Crustle", "active", 120, False, True, "confirmed"))
        elif state.active_id == CardIds.MEGA_KANGASKHAN_EX:
            if state.can_attack_now:
                out.append((CardIds.MEGA_KANGASKHAN_EX, "Mega Kangaskhan ex", "active", 200, False, False, "confirmed"))
            elif active_energy == 2 and _has_attach_to_attacker(actions, CardIds.MEGA_KANGASKHAN_EX, active_only=True):
                out.append((CardIds.MEGA_KANGASKHAN_EX, "Mega Kangaskhan ex", "active", 200, False, True, "confirmed"))

    for idx, card in enumerate(state.bench):
        cid = getattr(card, "id", None)
        if cid == CardIds.CRUSTLE:
            if energy_count(card) >= 3:
                out.append((CardIds.CRUSTLE, "Crustle", f"bench:{idx}", 120, True, False, "confirmed"))
            elif energy_count(card) == 2 and _has_attach_to_attacker(actions, CardIds.CRUSTLE, require_grass=not _has_grass_energy(card), bench_only=True):
                out.append((CardIds.CRUSTLE, "Crustle", f"bench:{idx}", 120, True, True, "possible"))
        elif cid == CardIds.MEGA_KANGASKHAN_EX:
            if energy_count(card) >= 3:
                out.append((CardIds.MEGA_KANGASKHAN_EX, "Mega Kangaskhan ex", f"bench:{idx}", 200, True, False, "confirmed"))
            elif energy_count(card) == 2 and _has_attach_to_attacker(actions, CardIds.MEGA_KANGASKHAN_EX, bench_only=True):
                out.append((CardIds.MEGA_KANGASKHAN_EX, "Mega Kangaskhan ex", f"bench:{idx}", 200, True, True, "possible"))
    return out


def _has_grass_energy(card: Any) -> bool:
    return has_attached(card, CardIds.BASIC_GRASS) or has_attached(card, CardIds.GROW_GRASS_ENERGY)


def _has_attach_to_attacker(actions, attacker_id: int, require_grass: bool = False, active_only: bool = False, bench_only: bool = False) -> bool:
    for action in actions or []:
        if not action.has("attach_energy") or action.target_id != attacker_id:
            continue
        if active_only and not action.has("target_active"):
            continue
        if bench_only and not action.has("target_bench"):
            continue
        if require_grass and not (action.has("attach_growing_grass") or action.has("attach_basic_grass")):
            continue
        return True
    return False


def _gust_route_for_target(state, target) -> tuple[str, str]:
    if state.hand_has(CardIds.BOSS_ORDERS):
        return "boss", "confirmed"
    if target.is_basic and state.hand_has(CardIds.LISIA):
        return "lisia", "confirmed"
    if state.hand_has(CardIds.PETREL):
        # Petrel is itself a Supporter, so it cannot be a confirmed same-turn
        # route into Boss/Lisia. Keep it as possible pressure only.
        boss_status = state.card_status(CardIds.BOSS_ORDERS)
        lisia_status = state.card_status(CardIds.LISIA) if target.is_basic else "dead"
        if boss_status != "dead" or lisia_status != "dead":
            return "petrel_to_boss", "possible"
    return "none", "none"


def _combine_confidence(a: str, b: str) -> str:
    if a == "confirmed" and b == "confirmed":
        return "confirmed"
    if a == "none" or b == "none":
        return "none"
    return "possible"


def _build_pressure_hint(state, attackers) -> PrizePlan:
    plan = PrizePlan()
    best_value = 0.0
    for attacker_id, _name, _slot, damage, _need_switch, need_energy, _confidence in attackers:
        if state.opponent_active_view is None or damage <= 0:
            continue
        hp = max(1, state.opponent_active_view.hp)
        ratio = damage / float(hp)
        # Only expose pressure hints that matter; this cannot choose PrizePlan by
        # itself, but WallPlan may use it when otherwise waiting.
        if ratio >= 0.55:
            value = ratio * 100 + state.opponent_active_view.prize_value * 20
            if value > best_value:
                best_value = value
                plan.pressure_available = True
                plan.pressure_attacker_card_id = attacker_id
                plan.pressure_target_card_id = state.opponent_active_view.card_id
                plan.pressure_damage = damage
                plan.pressure_need_energy = need_energy
                plan.pressure_reason = "direct_pressure" if not need_energy else "attach_then_direct_pressure"
    return plan


def _prize_plan_value(plan: PrizePlan) -> float:
    value = plan.prize_gain * 300.0
    if plan.wins_game:
        value += 2000.0
    if plan.route == "direct":
        value += 150.0
    if plan.confidence == "possible":
        value -= 260.0
    if plan.need_switch:
        value -= 160.0
    if plan.need_energy:
        value -= 120.0
    if plan.breaks_wall:
        value -= 280.0
    if plan.attacker_card_id == CardIds.CRUSTLE:
        value += 60.0
    return value
