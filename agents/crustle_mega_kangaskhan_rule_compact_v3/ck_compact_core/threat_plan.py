from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .battle_model import (
    AttackProfile,
    attacks_for,
    bench_counter_damage,
    best_possible_attack_next_energy,
    best_usable_attack,
    damage_blocked_by_crustle_wall,
    missing_energy_to_attack,
    stable_damage_to_defender,
)
from .runtime import CardIds, CORE_POKEMON, energy_count, get_card_name_en, get_card_name_zh, hp_remaining, is_ex_card, prize_count


@dataclass(frozen=True)
class ThreatCandidate:
    source_slot: str                     # active / bench:N
    source_card_id: int | None
    source_name_en: str
    source_name_zh: str
    attack_name: str | None
    timing: str                          # now / next_turn / future
    confidence: str                      # confirmed / likely / possible
    raw_damage_to_active: int = 0
    effective_damage_to_active: int = 0
    bench_damage: int = 0
    missing_energy: int = 0
    can_ko_active: bool = False
    can_ko_core_bench_now: bool = False
    can_ko_core_bench_two_turn: bool = False
    blocked_by_crustle: bool = False
    bypass_reasons: tuple[str, ...] = tuple()
    severity: float = 0.0


@dataclass(frozen=True)
class OpponentThreatPlan:
    candidates: tuple[ThreatCandidate, ...] = tuple()
    main: ThreatCandidate | None = None
    immediate_prize_threat: bool = False
    next_turn_prize_threat: bool = False
    bench_damage_pressure: bool = False
    two_turn_bench_pressure: bool = False
    gust_prize_pressure: bool = False
    non_ex_wall_breaker_ready: bool = False
    active_damage_blocked_by_crustle: bool = False
    defense_buys_tempo: bool = False
    expected_delay_turns: int = 0
    recommended_defense: str = "none"     # protect_bench / disrupt_energy / disrupt_hand / heal_active / build_board / none
    reasons: tuple[str, ...] = tuple()
    summary: str = "no_public_threat"

    @property
    def can_ko_active(self) -> bool:
        return any(c.timing == "now" and c.source_slot == "active" and c.can_ko_active for c in self.candidates)

    @property
    def effective_damage_to_active(self) -> int:
        return int(max((c.effective_damage_to_active for c in self.candidates if c.timing == "now" and c.source_slot == "active"), default=0))

    @property
    def raw_damage_to_active(self) -> int:
        return int(max((c.raw_damage_to_active for c in self.candidates if c.timing == "now" and c.source_slot == "active"), default=0))

    @property
    def bench_damage(self) -> int:
        return int(max((c.bench_damage for c in self.candidates), default=0))

    @property
    def blocked_by_crustle(self) -> bool:
        return self.active_damage_blocked_by_crustle


def build_opponent_threat_plan(state: Any) -> OpponentThreatPlan:
    """Build a public-information opponent threat model.

    This is intentionally broader than the old active-only estimate. It evaluates
    the opponent active and bench Pokemon, records current and one-energy-away
    attacks, marks wall bypass vectors, and turns those public facts into a
    defensive recommendation. It does not assume hidden cards, but it does treat
    high opponent hand count as generic gust/response risk.
    """
    my_active = state.active
    if my_active is None:
        return OpponentThreatPlan(summary="no_my_active")

    candidates: list[ThreatCandidate] = []
    opponent_pokemon = []
    if state.opponent_active is not None:
        opponent_pokemon.append(("active", state.opponent_active, True))
    for i, card in enumerate(state.opponent_bench or []):
        opponent_pokemon.append((f"bench:{i}", card, False))

    for slot, attacker, is_active in opponent_pokemon:
        candidates.extend(_threats_for_attacker(state, slot, attacker, is_active))

    if not candidates:
        return OpponentThreatPlan(summary="no_attack_profile")

    candidates.sort(key=lambda c: c.severity, reverse=True)
    main = candidates[0]

    immediate_prize = any(c.timing == "now" and (c.can_ko_active or c.can_ko_core_bench_now) for c in candidates)
    next_turn_prize = any(c.timing in {"next_turn", "future"} and (c.can_ko_active or c.can_ko_core_bench_now or c.can_ko_core_bench_two_turn) for c in candidates)
    bench_damage_pressure = any(c.bench_damage > 0 for c in candidates)
    two_turn_bench_pressure = any(c.can_ko_core_bench_two_turn for c in candidates)
    non_ex_ready = any("non_ex_attacker" in c.bypass_reasons and c.timing == "now" for c in candidates)
    active_blocked = any(c.source_slot == "active" and c.timing == "now" and c.blocked_by_crustle for c in candidates)
    gust_pressure = _estimate_gust_prize_pressure(state)

    reasons: list[str] = []
    if immediate_prize:
        reasons.append("immediate_prize_threat")
    if next_turn_prize:
        reasons.append("next_turn_prize_threat")
    if bench_damage_pressure:
        reasons.append("bench_damage_pressure")
    if two_turn_bench_pressure:
        reasons.append("two_turn_bench_pressure")
    if gust_pressure:
        reasons.append("gust_prize_pressure")
    if non_ex_ready:
        reasons.append("non_ex_wall_breaker_ready")
    if active_blocked:
        reasons.append("active_damage_blocked_by_crustle")

    # Crustle buys tempo only when it blocks the current active-damage plan and
    # the opponent is not simultaneously advancing a serious bench/gust prize plan.
    buys_tempo = bool(
        active_blocked
        and not immediate_prize
        and not two_turn_bench_pressure
        and not non_ex_ready
    )

    recommended = _recommended_defense(state, immediate_prize, two_turn_bench_pressure, bench_damage_pressure, gust_pressure, non_ex_ready, buys_tempo)
    if recommended != "none":
        reasons.append(f"recommended:{recommended}")

    summary = "tempo_window" if buys_tempo else ("urgent_defense" if immediate_prize else "pressure_defense")
    return OpponentThreatPlan(
        candidates=tuple(candidates),
        main=main,
        immediate_prize_threat=immediate_prize,
        next_turn_prize_threat=next_turn_prize,
        bench_damage_pressure=bench_damage_pressure,
        two_turn_bench_pressure=two_turn_bench_pressure,
        gust_prize_pressure=gust_pressure,
        non_ex_wall_breaker_ready=non_ex_ready,
        active_damage_blocked_by_crustle=active_blocked,
        defense_buys_tempo=buys_tempo,
        expected_delay_turns=1 if buys_tempo else 0,
        recommended_defense=recommended,
        reasons=tuple(reasons),
        summary=summary,
    )


def _threats_for_attacker(state: Any, slot: str, attacker: Any, is_active: bool) -> list[ThreatCandidate]:
    out: list[ThreatCandidate] = []
    usable = best_usable_attack(attacker)
    if usable is not None:
        out.append(_candidate_from_attack(state, slot, attacker, usable, is_active, timing="now" if is_active else "future", confidence="confirmed" if is_active else "likely"))

    next_attack = best_possible_attack_next_energy(attacker)
    if next_attack is not None and (usable is None or next_attack.damage > usable.damage or next_attack.bench_damage_counters > usable.bench_damage_counters):
        miss = missing_energy_to_attack(attacker, next_attack)
        if miss <= 1:
            out.append(_candidate_from_attack(state, slot, attacker, next_attack, is_active, timing="next_turn", confidence="likely" if is_active else "possible"))
    return out


def _candidate_from_attack(state: Any, slot: str, attacker: Any, attack: AttackProfile, is_active: bool, timing: str, confidence: str) -> ThreatCandidate:
    my_active = state.active
    raw = int(attack.damage)
    effective = stable_damage_to_defender(attacker, my_active, attack) if timing == "now" and is_active else raw
    blocked = bool(timing == "now" and is_active and damage_blocked_by_crustle_wall(attacker, my_active, attack))
    bench_damage = bench_counter_damage(attack)
    missing = missing_energy_to_attack(attacker, attack)

    active_hp = hp_remaining(my_active)
    can_ko_active = bool(effective >= active_hp and effective > 0)
    core_now, core_two_turn = _bench_core_ko_flags(state, bench_damage)

    bypass: list[str] = []
    if bench_damage > 0:
        bypass.append("bench_damage_effect")
    if not is_ex_card(attacker):
        bypass.append("non_ex_attacker")
    if blocked and bench_damage > 0:
        bypass.append("blocked_active_damage_but_bench_effect_remains")
    if not blocked and state.crustle_active and is_active:
        bypass.append("active_damage_not_blocked")
    if energy_count(attacker) >= 2:
        bypass.append("energy_ready")
    if not is_active:
        bypass.append("bench_attacker_route")

    severity = _severity_score(state, attacker, attack, timing, confidence, effective, bench_damage, can_ko_active, core_now, core_two_turn, blocked, bypass)
    return ThreatCandidate(
        source_slot=slot,
        source_card_id=getattr(attacker, "id", None),
        source_name_en=get_card_name_en(attacker),
        source_name_zh=get_card_name_zh(attacker),
        attack_name=attack.name,
        timing=timing,
        confidence=confidence,
        raw_damage_to_active=raw,
        effective_damage_to_active=effective,
        bench_damage=bench_damage,
        missing_energy=missing,
        can_ko_active=can_ko_active,
        can_ko_core_bench_now=core_now,
        can_ko_core_bench_two_turn=core_two_turn,
        blocked_by_crustle=blocked,
        bypass_reasons=tuple(bypass),
        severity=severity,
    )


def _bench_core_ko_flags(state: Any, bench_damage: int) -> tuple[bool, bool]:
    if bench_damage <= 0:
        return False, False
    now = False
    two_turn = False
    for view in state.bench_views:
        if view.card_id not in CORE_POKEMON:
            continue
        # Mist Energy prevents attack effects on that Pokemon.
        if CardIds.MIST_ENERGY in view.energy_ids:
            continue
        if view.hp <= bench_damage:
            now = True
        if view.hp <= bench_damage * 2:
            two_turn = True
    return now, two_turn


def _estimate_gust_prize_pressure(state: Any) -> bool:
    # Hidden gust cannot be known. Use public risk: opponent has a reasonably
    # large hand and there is a high-value or damaged bench target.
    if state.opponent_hand_count < 4:
        return False
    for view in state.bench_views:
        if view.card_id == CardIds.MEGA_KANGASKHAN_EX and view.hp <= 260:
            return True
        if view.card_id in CORE_POKEMON and view.hp <= 120:
            return True
    return False


def _severity_score(state: Any, attacker: Any, attack: AttackProfile, timing: str, confidence: str, effective: int, bench_damage: int, can_ko_active: bool, core_now: bool, core_two_turn: bool, blocked: bool, bypass: list[str]) -> float:
    value = 0.0
    if timing == "now":
        value += 250
    elif timing == "next_turn":
        value += 140
    else:
        value += 90
    if confidence == "confirmed":
        value += 80
    elif confidence == "likely":
        value += 40
    value += min(320, effective)
    value += bench_damage * 1.4
    if can_ko_active:
        value += 900
    if core_now:
        value += 850
    if core_two_turn:
        value += 420
    if "non_ex_attacker" in bypass and state.crustle_active:
        value += 220
    if "bench_damage_effect" in bypass:
        value += 240
    if blocked:
        value -= 260
    return value


def _recommended_defense(state: Any, immediate_prize: bool, two_turn_bench: bool, bench_damage: bool, gust_pressure: bool, non_ex_ready: bool, buys_tempo: bool) -> str:
    if state.active_view is not None and state.active_view.hp <= 100 and immediate_prize:
        return "heal_active"
    if bench_damage and (two_turn_bench or state.has_damaged_core_bench or state.has_low_hp_core_bench):
        return "protect_bench"
    if gust_pressure:
        return "disrupt_hand"
    if non_ex_ready:
        return "prize_or_gust_non_ex"
    if immediate_prize or state.opponent_active_energy_count >= 2:
        return "disrupt_energy"
    if buys_tempo:
        return "cash_tempo"
    return "none"
