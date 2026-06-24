from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from cg.api import OptionType

from line_evaluator import build_line_states, evaluate_lines
from matchup_profile import MatchupProfile, detect_matchup_profile
from runtime import CardIds, count_ids, damage_taken, energy_count, get_card_name, is_basic_pokemon, is_ex_card, prize_count


@dataclass
class DeckState:
    phase: str
    primary_plan: str
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
    close_game: bool
    close_pressure: bool
    direct_win_available: bool
    can_make_crustle_wall_this_turn: bool
    can_run_errand_or_attack: bool
    current_attack_damage: int
    plan_scores: dict[str, float]
    line_states: list[object]
    state_tags: list[str]


def _count_field(cards) -> Counter[int]:
    return count_ids([card for card in cards if card is not None])


def _estimate_opponent_damage(opponent_active, matchup: MatchupProfile) -> int:
    if opponent_active is None:
        return 0
    damage = 50 + 30 * energy_count(opponent_active)
    if is_ex_card(opponent_active):
        damage += 20
    if matchup.name == "dragapult_ex":
        damage += 20
    return damage


def _estimate_current_attack_damage(active) -> int:
    if active is None:
        return 0
    active_id = getattr(active, "id", None)
    attached = energy_count(active)
    if active_id == CardIds.CRUSTLE:
        return 120 if attached >= 1 else 0
    if active_id == CardIds.MEGA_KANGASKHAN_EX:
        return 200 if attached >= 3 else 0
    if active_id == CardIds.DWEBBLE:
        return 0
    return 30 + attached * 30 if attached > 0 else 0


def _gust_window_flags(opponent_bench, can_attack_now: bool, my_prizes_left: int, current_attack_damage: int) -> tuple[bool, bool, bool, bool]:
    if not can_attack_now:
        return False, False, False, False
    gust_for_win = False
    gust_for_prize = False
    gust_for_stall = False
    for card in opponent_bench:
        if card is None:
            continue
        hp = getattr(card, "hp", 999)
        can_ko = current_attack_damage >= hp > 0
        if can_ko and prize_count(card) >= my_prizes_left:
            gust_for_win = True
        if can_ko and (prize_count(card) >= 2 or hp <= 120):
            gust_for_prize = True
        if hp > current_attack_damage and hp > 120 and energy_count(card) == 0:
            gust_for_stall = True
    gust_window = gust_for_win or gust_for_prize or gust_for_stall
    return gust_window, gust_for_win, gust_for_prize, gust_for_stall


def _has_dragapult_bench_risk(bench, matchup: MatchupProfile) -> bool:
    if not matchup.values_bench_protection:
        return False
    for card in bench:
        if card is None:
            continue
        if getattr(card, "id", None) in {CardIds.DWEBBLE, CardIds.CRUSTLE, CardIds.MEGA_KANGASKHAN_EX} and getattr(card, "hp", 999) <= 60:
            return True
    return False


def _has_direct_attack_win(can_attack_now: bool, current_attack_damage: int, my_prizes_left: int, opponent_active, opponent_bench) -> bool:
    if not can_attack_now or my_prizes_left <= 0:
        return False
    targets = [opponent_active] + list(opponent_bench or [])
    for card in targets:
        if card is None:
            continue
        hp = getattr(card, "hp", 999)
        if current_attack_damage >= hp > 0 and prize_count(card) >= my_prizes_left:
            return True
    return False


def analyze_deck_state(obs, deck_knowledge=None) -> DeckState:
    state = obs.current
    my_index = state.yourIndex
    my_state = state.players[my_index]
    op_state = state.players[1 - my_index]
    matchup = detect_matchup_profile(obs)

    field = [card for card in my_state.active + my_state.bench if card is not None]
    field_counts: Counter[int] = _count_field(field)
    bench_cards = [card for card in my_state.bench if card is not None]
    active = my_state.active[0] if my_state.active else None
    opponent_active = op_state.active[0] if op_state.active else None
    field_count = len(field)

    active_id = None if active is None else active.id
    active_name = None if active is None else get_card_name(active)
    active_energy = energy_count(active)
    active_damage = damage_taken(active)
    active_remaining_hp = 0 if active is None else getattr(active, "hp", 0)
    dwebble_in_play = field_counts[CardIds.DWEBBLE]
    crustle_in_play = field_counts[CardIds.CRUSTLE]
    kangaskhan_in_play = field_counts[CardIds.MEGA_KANGASKHAN_EX]
    setup_missing_crustle = crustle_in_play == 0
    setup_missing_kangaskhan = kangaskhan_in_play == 0
    needs_setup = setup_missing_crustle or setup_missing_kangaskhan
    can_attack_now = any(option.type == OptionType.ATTACK for option in obs.select.option)
    opponent_active_is_ex = is_ex_card(opponent_active)
    my_prizes_left = len(my_state.prize)
    opponent_prizes_left = len(op_state.prize)
    prize_diff = my_prizes_left - opponent_prizes_left
    bench_space = max(0, 5 - len(bench_cards))
    field_basic_count = sum(1 for card in field if is_basic_pokemon(card))
    bench_basic_count = sum(1 for card in bench_cards if is_basic_pokemon(card))
    empty_bench = len(bench_cards) == 0
    only_one_pokemon_in_play = len(field) == 1
    active_is_crustle = active_id == CardIds.CRUSTLE
    active_is_kangaskhan = active_id == CardIds.MEGA_KANGASKHAN_EX
    active_is_dwebble = active_id == CardIds.DWEBBLE
    wall_is_valid = active_is_crustle and opponent_active_is_ex
    wall_online = active_is_crustle and (opponent_active_is_ex or matchup.prefers_crustle_wall)
    bench_risk = _has_dragapult_bench_risk(my_state.bench, matchup)
    opponent_estimated_damage = _estimate_opponent_damage(opponent_active, matchup)
    current_attack_damage = _estimate_current_attack_damage(active)
    if active_is_crustle and opponent_active_is_ex and matchup.prefers_crustle_wall:
        opponent_estimated_damage = 0
    active_under_ko_threat = active is not None and opponent_estimated_damage >= active_remaining_hp > 0
    early_game = getattr(state, "turn", 0) <= 5
    active_prizes = prize_count(active)
    opponent_can_win_by_active_ko = opponent_prizes_left <= active_prizes
    no_backup_loss = field_count <= 1
    want_second_backup = bench_space > 0 and early_game and field_count < 3
    must_bench_basic = not wall_is_valid and bench_space > 0 and (
        no_backup_loss
        or active_under_ko_threat
        or opponent_can_win_by_active_ko
        or want_second_backup
    )
    heal_prevents_ko = active is not None and active_remaining_hp <= opponent_estimated_damage < (active_remaining_hp + 80)
    jumbo_prevents_ko = active is not None and active_energy >= 3 and heal_prevents_ko
    jumbo_heal_option = jumbo_prevents_ko
    bianca_prevents_ko = active is not None and getattr(active, "hp", 999) <= 30 and opponent_estimated_damage >= getattr(active, "hp", 999)
    heal_window = jumbo_prevents_ko or bianca_prevents_ko
    bianca_window = bianca_prevents_ko
    has_effective_heal = jumbo_prevents_ko or bianca_prevents_ko
    disruption_window = getattr(op_state, "handCount", 0) >= 5
    gust_window, gust_for_win, gust_for_prize, gust_for_stall = _gust_window_flags(
        op_state.bench,
        can_attack_now,
        my_prizes_left,
        current_attack_damage,
    )
    prevent_loss = active_under_ko_threat and my_prizes_left > 1
    direct_win_available = _has_direct_attack_win(can_attack_now, current_attack_damage, my_prizes_left, opponent_active, op_state.bench)
    close_pressure = my_prizes_left <= 2
    close_game = direct_win_available
    can_make_crustle_wall_this_turn = active_is_dwebble or (crustle_in_play > 0 and not active_is_crustle)
    can_run_errand_or_attack = active_is_kangaskhan

    temp_state = type("TempState", (), {
        "wall_online": wall_online,
        "dwebble_in_play": dwebble_in_play,
        "setup_missing_crustle": setup_missing_crustle,
        "crustle_in_play": crustle_in_play,
        "kangaskhan_in_play": kangaskhan_in_play,
        "active_is_kangaskhan": active_is_kangaskhan,
        "active_energy": active_energy,
        "bench_risk": bench_risk,
        "heal_prevents_ko": heal_prevents_ko,
        "bianca_window": bianca_window,
        "disruption_window": disruption_window,
        "gust_for_win": gust_for_win,
        "gust_for_prize": gust_for_prize,
        "my_prizes_left": my_prizes_left,
        "can_attack_now": can_attack_now,
        "must_bench_basic": must_bench_basic,
        "active_is_crustle": active_is_crustle,
    })()
    line_scores = evaluate_lines(deck_state=temp_state, matchup=matchup, active=active, opponent_active=opponent_active)
    line_states = build_line_states(
        deck_state=temp_state,
        matchup=matchup,
        active=active,
        opponent_active=opponent_active,
        deck_knowledge=deck_knowledge,
    )
    wall_plan_score = line_scores.crustle_wall_line + line_scores.disruption_line * 0.5
    if setup_missing_crustle and not wall_online:
        wall_plan_score -= 0.45
    plan_scores = {
        "close_game": line_scores.close_game_line + (1.0 if close_game else 0.0),
        "prevent_loss": (1.2 if prevent_loss else 0.0) + line_scores.heal_escape_line + (0.35 if bench_risk else 0.0),
        "wall_and_tax": max(0.0, wall_plan_score),
        "tank_and_heal": line_scores.kang_tank_line + line_scores.heal_escape_line,
        "setup_crustle": (
            1.15 if setup_missing_crustle and (matchup.prefers_crustle_wall or opponent_active_is_ex) else 0.0
        ) + (0.2 if matchup.values_bench_protection and dwebble_in_play == 0 else 0.0) + (0.3 if bench_risk else 0.0),
        "setup_kangaskhan": (0.9 if setup_missing_kangaskhan and not wall_online else 0.0),
        "disruption_loop": line_scores.disruption_line,
        "stabilize": 0.4 + line_scores.attack_continuity_line * 0.2,
    }
    if direct_win_available and plan_scores["close_game"] > 0.0:
        primary_plan = "close_game"
    elif matchup.name == "dragapult_ex" and bench_risk:
        primary_plan = "protect_bench_vs_dragapult"
    elif must_bench_basic:
        primary_plan = "survival_setup"
    elif prevent_loss and has_effective_heal and plan_scores["prevent_loss"] > 0.0:
        primary_plan = "prevent_loss"
    elif wall_online and wall_is_valid:
        primary_plan = "wall_and_tax"
    elif can_make_crustle_wall_this_turn and setup_missing_crustle and matchup.prefers_crustle_wall:
        primary_plan = "setup_crustle_wall_now"
    elif active_is_kangaskhan and can_run_errand_or_attack:
        primary_plan = "tank_and_heal"
    elif setup_missing_crustle and (matchup.prefers_crustle_wall or opponent_active_is_ex):
        primary_plan = "setup_crustle"
    elif setup_missing_kangaskhan and not wall_online:
        primary_plan = "setup_kangaskhan"
    elif close_pressure:
        primary_plan = "close_pressure"
    elif disruption_window and not needs_setup:
        primary_plan = "disruption_loop"
    else:
        primary_plan = max(plan_scores, key=plan_scores.get)
    if primary_plan in {"setup_crustle", "setup_kangaskhan", "setup_crustle_wall_now", "survival_setup"}:
        phase = "setup"
    elif primary_plan == "close_game":
        phase = "close_game"
    elif primary_plan == "prevent_loss":
        phase = "prevent_loss"
    elif primary_plan == "wall_and_tax":
        phase = "wall_lock"
    elif primary_plan == "tank_and_heal":
        phase = "tank_cycle"
    elif primary_plan == "disruption_loop":
        phase = "disruption"
    else:
        phase = "midgame"

    state_tags: list[str] = []
    if setup_missing_crustle:
        state_tags.append("crustle_not_online")
    if wall_online:
        state_tags.append("wall_online")
    if active_is_kangaskhan:
        state_tags.append("kang_active")
    if heal_prevents_ko:
        state_tags.append("heal_prevents_ko")
    if bench_risk:
        state_tags.append("bench_risk")
    if gust_for_win:
        state_tags.append("gust_for_win")
    if must_bench_basic:
        state_tags.append("must_bench_basic")
    if matchup.name == "dragapult_ex" and bench_risk:
        state_tags.append("protect_bench_vs_dragapult")
    if matchup.values_mist_energy:
        state_tags.append("mist_matchup")
    state_tags.extend(matchup.tags)

    return DeckState(
        phase=phase,
        primary_plan=primary_plan,
        matchup=matchup,
        opponent_active_is_ex=opponent_active_is_ex,
        active_id=active_id,
        active_name=active_name,
        active_energy=active_energy,
        active_damage=active_damage,
        active_remaining_hp=active_remaining_hp,
        opponent_estimated_damage=opponent_estimated_damage,
        dwebble_in_play=dwebble_in_play,
        crustle_in_play=crustle_in_play,
        kangaskhan_in_play=kangaskhan_in_play,
        needs_setup=needs_setup,
        can_attack_now=can_attack_now,
        my_prizes_left=my_prizes_left,
        opponent_prizes_left=opponent_prizes_left,
        prize_diff=prize_diff,
        bench_space=bench_space,
        field_count=field_count,
        field_basic_count=field_basic_count,
        bench_basic_count=bench_basic_count,
        empty_bench=empty_bench,
        only_one_pokemon_in_play=only_one_pokemon_in_play,
        must_bench_basic=must_bench_basic,
        setup_missing_crustle=setup_missing_crustle,
        setup_missing_kangaskhan=setup_missing_kangaskhan,
        wall_is_valid=wall_is_valid,
        active_is_crustle=active_is_crustle,
        active_is_kangaskhan=active_is_kangaskhan,
        active_is_dwebble=active_is_dwebble,
        wall_online=wall_online,
        bench_risk=bench_risk,
        active_under_ko_threat=active_under_ko_threat,
        heal_window=heal_window,
        heal_prevents_ko=heal_prevents_ko,
        jumbo_heal_option=jumbo_heal_option,
        jumbo_prevents_ko=jumbo_prevents_ko,
        bianca_prevents_ko=bianca_prevents_ko,
        has_effective_heal=has_effective_heal,
        bianca_window=bianca_window,
        disruption_window=disruption_window,
        gust_window=gust_window,
        gust_for_win=gust_for_win,
        gust_for_prize=gust_for_prize,
        gust_for_stall=gust_for_stall,
        prevent_loss=prevent_loss,
        close_game=close_game,
        close_pressure=close_pressure,
        direct_win_available=direct_win_available,
        can_make_crustle_wall_this_turn=can_make_crustle_wall_this_turn,
        can_run_errand_or_attack=can_run_errand_or_attack,
        current_attack_damage=current_attack_damage,
        plan_scores=plan_scores,
        line_states=line_states,
        state_tags=state_tags,
    )
