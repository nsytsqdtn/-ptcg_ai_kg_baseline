from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from cg.api import OptionType

from .line_evaluator import build_line_states
from .matchup_profile import MatchupProfile
from .runtime import CardIds, damage_taken, energy_count, get_card_name, is_basic_pokemon, prize_count
from .turn_plan import build_turn_plan, BoardSnapshot


@dataclass
class DeckState:
    phase: str
    objective: str
    matchup: MatchupProfile
    opponent_active_is_ex: bool
    active_id: int | None
    active_name: str | None
    active_energy: int
    active_damage: int
    active_remaining_hp: int
    opponent_estimated_damage: int
    dwebble_in_play: int
    crustle_in_play: int
    kangaskhan_in_play: int
    needs_setup: bool
    can_attack_now: bool
    my_prizes_left: int
    opponent_prizes_left: int
    prize_diff: int
    bench_space: int
    field_count: int
    field_basic_count: int
    bench_basic_count: int
    empty_bench: bool
    only_one_pokemon_in_play: bool
    must_bench_basic: bool
    setup_missing_crustle: bool
    setup_missing_kangaskhan: bool
    wall_is_valid: bool
    active_is_crustle: bool
    active_is_kangaskhan: bool
    active_is_dwebble: bool
    wall_online: bool
    bench_risk: bool
    active_under_ko_threat: bool
    heal_window: bool
    heal_prevents_ko: bool
    jumbo_heal_option: bool
    jumbo_prevents_ko: bool
    bianca_prevents_ko: bool
    has_effective_heal: bool
    bianca_window: bool
    disruption_window: bool
    gust_window: bool
    gust_for_win: bool
    gust_for_prize: bool
    gust_for_stall: bool
    prevent_loss: bool
    is_finish: bool
    direct_win_available: bool
    can_make_crustle_wall_this_turn: bool
    can_run_errand_or_attack: bool
    current_attack_damage: int
    plan_scores: dict[str, float]
    line_states: list[Any]
    state_tags: list[str]
    turn_plan: Any | None = None


def _phase_for_plan(plan: str) -> str:
    if plan == "finish":
        return "finish"
    if plan in {"setup_backup", "setup_crustle_wall"}:
        return "setup"
    if plan == "prevent_loss":
        return "prevent_loss"
    if plan == "wall_control":
        return "wall_lock"
    if plan == "kang_engine":
        return "tank_cycle"
    if plan in {"resource_lock", "pressure_prize"}:
        return "disruption"
    return "midgame"


def _gust_flags(snapshot) -> tuple[bool, bool, bool, bool]:
    if not snapshot.can_attack_now:
        return False, False, False, False
    gust_for_win = False
    gust_for_prize = False
    gust_for_stall = False
    for target in snapshot.opponent_bench:
        hp = getattr(target, "hp", 999)
        can_ko = snapshot.current_attack_damage >= hp > 0
        if can_ko and prize_count(target) >= snapshot.my_prizes_left:
            gust_for_win = True
        if can_ko and (prize_count(target) >= 2 or hp <= 120):
            gust_for_prize = True
        if not can_ko and hp > 120 and energy_count(target) == 0:
            gust_for_stall = True
    return gust_for_win or gust_for_prize or gust_for_stall, gust_for_win, gust_for_prize, gust_for_stall


def _bench_risk(snapshot) -> bool:
    if not snapshot.matchup.values_bench_protection:
        return False
    for card in snapshot.bench:
        if getattr(card, "id", None) in {CardIds.DWEBBLE, CardIds.CRUSTLE, CardIds.MEGA_KANGASKHAN_EX} and getattr(card, "hp", 999) <= 80:
            return True
    return False


def analyze_deck_state(obs, deck_knowledge=None) -> DeckState:
    snapshot = BoardSnapshot.from_obs(obs, deck_knowledge)
    from .obligations import build_obligations
    obligations = build_obligations(snapshot, deck_knowledge)
    plan = build_turn_plan(snapshot, obligations, deck_knowledge)
    active = snapshot.active
    active_id = snapshot.active_id
    setup_missing_crustle = snapshot.crustle_in_play == 0
    setup_missing_kangaskhan = snapshot.kang_in_play == 0
    needs_setup = setup_missing_crustle or setup_missing_kangaskhan
    bench_basic_count = sum(1 for c in snapshot.bench if is_basic_pokemon(c))
    field_basic_count = sum(1 for c in snapshot.field if is_basic_pokemon(c))
    empty_bench = len(snapshot.bench) == 0
    only_one = snapshot.field_count <= 1
    active_prizes = prize_count(active)
    opponent_can_win_by_active_ko = snapshot.opponent_prizes_left <= active_prizes
    prevent_loss = snapshot.active_under_ko_threat and (only_one or opponent_can_win_by_active_ko)
    heal_prevents = active is not None and snapshot.active_hp <= snapshot.opponent_estimated_damage < snapshot.active_hp + 80
    jumbo = active is not None and snapshot.active_energy >= 3 and heal_prevents
    bianca = active is not None and getattr(active, "hp", 999) <= 30 and snapshot.opponent_estimated_damage >= getattr(active, "hp", 999)
    heal_window = jumbo or bianca
    disruption_window = getattr(snapshot.op_state, "handCount", 0) >= 5 or (snapshot.wall_online and snapshot.matchup.values_disruption)
    gust_window, gust_for_win, gust_for_prize, gust_for_stall = _gust_flags(snapshot)
    bench_risk = _bench_risk(snapshot)

    plan_scores = {
        "finish": 100.0 if plan.objective == "finish" else 0.0,
        "setup_backup": 95.0 if plan.objective == "setup_backup" else 0.0,
        "prevent_loss": 90.0 if plan.objective == "prevent_loss" else 0.0,
        "setup_crustle_wall": 84.0 if plan.objective == "setup_crustle_wall" else 0.0,
        "protect_bench_core": 86.0 if plan.objective == "protect_bench_core" else 0.0,
        "wall_control": 80.0 if plan.objective == "wall_control" else 0.0,
        "pressure_prize": 68.0 if plan.objective == "pressure_prize" else 0.0,
        "resource_lock": 62.0 if plan.objective == "resource_lock" else 0.0,
        "kang_engine": 58.0 if plan.objective == "kang_engine" else 0.0,
        "stabilize": 40.0 if plan.objective == "stabilize" else 0.0,
    }

    temp = type("TempState", (), {
        "wall_online": snapshot.wall_online,
        "dwebble_in_play": snapshot.dwebble_in_play,
        "setup_missing_crustle": setup_missing_crustle,
        "crustle_in_play": snapshot.crustle_in_play,
        "kangaskhan_in_play": snapshot.kang_in_play,
        "active_is_kangaskhan": snapshot.active_is_kang,
        "active_energy": snapshot.active_energy,
        "bench_risk": bench_risk,
        "heal_prevents_ko": heal_prevents,
        "bianca_window": bianca,
        "disruption_window": disruption_window,
        "gust_for_win": gust_for_win,
        "gust_for_prize": gust_for_prize,
        "my_prizes_left": snapshot.my_prizes_left,
        "can_attack_now": snapshot.can_attack_now,
        "must_bench_basic": plan.must_prevent_no_active,
        "active_is_crustle": snapshot.active_is_crustle,
    })()
    line_states = build_line_states(temp, snapshot.matchup, active, snapshot.opponent_active, deck_knowledge=deck_knowledge)

    tags = [plan.objective] + list(plan.reasons) + snapshot.matchup.tags
    if setup_missing_crustle:
        tags.append("crustle_not_online")
    if snapshot.wall_online:
        tags.append("wall_online")
    if snapshot.active_is_kang:
        tags.append("kang_active")
    if heal_prevents:
        tags.append("heal_prevents_ko")
    if bench_risk:
        tags.append("bench_risk")
    if plan.must_prevent_no_active:
        tags.append("must_bench_basic")
    if snapshot.matchup.values_mist_energy:
        tags.append("mist_matchup")

    return DeckState(
        phase=_phase_for_plan(plan.objective),
        objective=plan.objective,
        matchup=snapshot.matchup,
        opponent_active_is_ex=snapshot.opponent_active_is_ex,
        active_id=active_id,
        active_name=get_card_name(active) if active is not None else None,
        active_energy=snapshot.active_energy,
        active_damage=damage_taken(active),
        active_remaining_hp=snapshot.active_hp,
        opponent_estimated_damage=snapshot.opponent_estimated_damage,
        dwebble_in_play=snapshot.dwebble_in_play,
        crustle_in_play=snapshot.crustle_in_play,
        kangaskhan_in_play=snapshot.kang_in_play,
        needs_setup=needs_setup,
        can_attack_now=snapshot.can_attack_now,
        my_prizes_left=snapshot.my_prizes_left,
        opponent_prizes_left=snapshot.opponent_prizes_left,
        prize_diff=snapshot.my_prizes_left - snapshot.opponent_prizes_left,
        bench_space=snapshot.bench_space,
        field_count=snapshot.field_count,
        field_basic_count=field_basic_count,
        bench_basic_count=bench_basic_count,
        empty_bench=empty_bench,
        only_one_pokemon_in_play=only_one,
        must_bench_basic=plan.must_prevent_no_active,
        setup_missing_crustle=setup_missing_crustle,
        setup_missing_kangaskhan=setup_missing_kangaskhan,
        wall_is_valid=snapshot.wall_valid,
        active_is_crustle=snapshot.active_is_crustle,
        active_is_kangaskhan=snapshot.active_is_kang,
        active_is_dwebble=snapshot.active_is_dwebble,
        wall_online=snapshot.wall_online,
        bench_risk=bench_risk,
        active_under_ko_threat=snapshot.active_under_ko_threat,
        heal_window=heal_window,
        heal_prevents_ko=heal_prevents,
        jumbo_heal_option=jumbo,
        jumbo_prevents_ko=jumbo,
        bianca_prevents_ko=bianca,
        has_effective_heal=heal_window,
        bianca_window=bianca,
        disruption_window=disruption_window,
        gust_window=gust_window,
        gust_for_win=gust_for_win,
        gust_for_prize=gust_for_prize,
        gust_for_stall=gust_for_stall,
        prevent_loss=prevent_loss,
        is_finish=plan.objective == "finish",
        direct_win_available=plan.direct_win_available,
        can_make_crustle_wall_this_turn=plan.can_make_crustle_wall_this_turn,
        can_run_errand_or_attack=snapshot.active_is_kang,
        current_attack_damage=snapshot.current_attack_damage,
        plan_scores=plan_scores,
        line_states=line_states,
        state_tags=tags,
        turn_plan=plan,
    )
