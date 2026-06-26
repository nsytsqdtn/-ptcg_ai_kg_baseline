from __future__ import annotations

from dataclasses import dataclass, field

from .actions import ActionView
from .runtime import CardIds


@dataclass
class ScoredAction:
    index: int
    action: ActionView
    score: float
    reasons: list[str] = field(default_factory=list)


def add(score: float, reasons: list[str], value: float, reason: str) -> float:
    if value:
        reasons.append(f"{reason}:{value:+.0f}")
    return score + value


def score_actions(actions: list[ActionView], state, selected_plan: str, setup, tempo, prize) -> list[ScoredAction]:
    scored: list[ScoredAction] = []
    for action in actions:
        score, reasons = safety_score(action, state)
        s, r = score_setup(action, state, setup)
        # Setup is always a secondary need, but full setup weight only when selected.
        if selected_plan == "setup":
            score += s; reasons += r
        else:
            score += s * 0.18; reasons += ["secondary_" + x for x in r[:3]]

        if selected_plan in {"win_prize", "prize", "tempo_prize"}:
            s, r = score_prize(action, state, prize)
            score += s; reasons += r
        elif prize.available and prize.confidence == "confirmed":
            s, r = score_prize(action, state, prize)
            score += s * 0.25; reasons += ["secondary_" + x for x in r[:3]]

        s, r = score_tempo(action, state, tempo, prize)
        if selected_plan.startswith("tempo_") or selected_plan in {"pressure", "stabilize"}:
            score += s; reasons += r
        else:
            score += s * 0.12; reasons += ["secondary_" + x for x in r[:3]]

        s, r = small_general_score(action, state)
        score += s; reasons += r
        scored.append(ScoredAction(action.index, action, score, reasons))
    scored.sort(key=lambda x: (x.score, -x.index), reverse=True)
    return scored


def safety_score(action: ActionView, state) -> tuple[float, list[str]]:
    score = 0.0
    reasons: list[str] = []
    if state.deck_danger and action.has("draw"):
        score = add(score, reasons, -1400, "avoid_deckout_draw")
    if state.field_count <= 1 and action.has("attack"):
        score = add(score, reasons, -1300, "avoid_attack_with_no_backup")
    if state.field_count <= 1 and action.has("end_turn"):
        score = add(score, reasons, -1200, "avoid_end_turn_with_no_backup")
    if state.opponent_threat.immediate_prize_threat and state.field_count <= 2 and action.has("end_turn") and not action.has("attack"):
        score = add(score, reasons, -520, "avoid_pass_under_prize_threat")
    if action.has("ascension_attack") and state.field_count <= 1:
        score = add(score, reasons, -1500, "avoid_ascension_no_backup")
    if state.current_active_damage_blocked and state.crustle_active and (action.has("retreat") or action.has("switch")) and not state.opponent_threat.non_ex_wall_breaker_ready:
        score = add(score, reasons, -260, "avoid_wasting_crustle_block")
    if action.has("draw") and state.safe_draws <= 2:
        score = add(score, reasons, -220, "low_safe_draws")
    return score, reasons


def score_setup(action: ActionView, state, setup) -> tuple[float, list[str]]:
    score = 0.0; reasons: list[str] = []
    cid = action.card_id
    if setup.need_backup:
        if action.has("bench_basic") and cid == CardIds.DWEBBLE:
            score = add(score, reasons, 1080, "setup_backup_play_dwebble")
        elif action.has("bench_basic") and cid == CardIds.MEGA_KANGASKHAN_EX:
            score = add(score, reasons, 780, "setup_backup_play_kang")
        if cid == CardIds.BUDDY_BUDDY_POFFIN:
            score = add(score, reasons, 950, "setup_backup_poffin")
        if cid == CardIds.ULTRA_BALL:
            score = add(score, reasons, 700, "setup_backup_ultra_ball")
        if cid == CardIds.HILDA:
            score = add(score, reasons, 620, "setup_backup_hilda")
        if cid == CardIds.PETREL:
            score = add(score, reasons, 530, "setup_backup_petrel")
        if cid == CardIds.POKEGEAR:
            score = add(score, reasons, 360, "setup_backup_pokegear")
        if action.has("attack") or action.has("end_turn"):
            score = add(score, reasons, -950, "setup_backup_no_end")
    if setup.need_dwebble:
        if action.has("bench_basic") and cid == CardIds.DWEBBLE:
            score = add(score, reasons, 900, "need_dwebble_play")
        if cid == CardIds.BUDDY_BUDDY_POFFIN:
            score = add(score, reasons, 830, "need_dwebble_poffin")
        if cid in {CardIds.ULTRA_BALL, CardIds.PETREL, CardIds.POKEGEAR}:
            score = add(score, reasons, 390, "need_dwebble_search")
    if setup.need_crustle:
        if action.has("evolve_crustle"):
            score = add(score, reasons, 1160, "need_crustle_evolve")
        if cid == CardIds.HILDA:
            score = add(score, reasons, 860, "need_crustle_hilda")
        if cid == CardIds.ULTRA_BALL:
            score = add(score, reasons, 730, "need_crustle_ultra")
        if cid == CardIds.PETREL:
            score = add(score, reasons, 520, "need_crustle_petrel")
        if action.has("ascension_attack") and setup.allow_ascension:
            score = add(score, reasons, 820, "safe_dwebble_ascension")
        if action.has("ascension_attack") and not setup.allow_ascension:
            score = add(score, reasons, -1250, "unsafe_dwebble_ascension")
    if setup.need_crustle_active:
        if action.has("switch"):
            score = add(score, reasons, 760, "need_crustle_active_switch")
        if action.has("evolve_crustle"):
            score = add(score, reasons, 680, "need_crustle_active_evolve")
    if setup.need_energy_for_crustle:
        if action.has("attach_growing_grass") and (action.has("target_dwebble") or action.has("target_crustle")):
            score = add(score, reasons, 650, "prepare_crustle_growing_grass")
        elif action.has("attach_basic_grass") and (action.has("target_dwebble") or action.has("target_crustle")):
            score = add(score, reasons, 550, "prepare_crustle_basic_grass")
        elif action.has("attach_mist") and (action.has("target_dwebble") or action.has("target_crustle")):
            score = add(score, reasons, 390, "prepare_crustle_mist")
    return score, reasons


def score_prize(action: ActionView, state, prize) -> tuple[float, list[str]]:
    score = 0.0; reasons: list[str] = []
    if not prize.available:
        return score, reasons
    if prize.wins_game:
        score = add(score, reasons, 2100, "prize_wins_game")
    if action.has("attack") and prize.attacker_slot == "active" and not prize.need_energy:
        score = add(score, reasons, 1250, "prize_attack")
    if prize.need_energy and action.has("attach_energy") and action.target_id == prize.attacker_card_id:
        score = add(score, reasons, 1050, "prize_attach_to_enable")
    if prize.route == "boss" and action.card_id == CardIds.BOSS_ORDERS:
        score = add(score, reasons, 1140, "prize_boss")
    if prize.route == "lisia" and action.card_id == CardIds.LISIA:
        score = add(score, reasons, 1040, "prize_lisia")
    if prize.need_switch and action.has("switch"):
        score = add(score, reasons, 850, "prize_switch_attacker")
    if not prize.need_energy and action.has("attach_energy") and action.target_id == prize.attacker_card_id:
        score = add(score, reasons, 300, "prize_prepare_attacker")
    return score, reasons


def score_tempo(action: ActionView, state, tempo, prize) -> tuple[float, list[str]]:
    score = 0.0; reasons: list[str] = []
    cid = action.card_id
    payoff = tempo.payoff
    if payoff == "heal":
        if cid == CardIds.JUMBO_ICE_CREAM:
            score = add(score, reasons, 980, "tempo_heal_jumbo")
        if cid == CardIds.BIANCA_DEVOTION:
            score = add(score, reasons, 920, "tempo_heal_bianca")
        if cid == CardIds.HERO_CAPE:
            score = add(score, reasons, 700, "tempo_heal_cape")
    elif payoff == "protect_bench":
        if action.has("attach_mist") and action.has("target_core"):
            score = add(score, reasons, 940, "tempo_protect_mist_core")
        if cid == CardIds.JUMBO_ICE_CREAM:
            score = add(score, reasons, 620, "tempo_protect_heal")
        if cid == CardIds.ERI:
            score = add(score, reasons, 560, "tempo_protect_eri")
        if cid == CardIds.HAND_TRIMMER:
            score = add(score, reasons, 520, "tempo_protect_hand_trimmer")
    elif payoff == "disrupt_energy":
        if cid == CardIds.XEROSIC:
            score = add(score, reasons, 920, "tempo_energy_xerosic")
        if cid == CardIds.HANDHELD_FAN:
            score = add(score, reasons, 790, "tempo_energy_fan")
        if action.has("gust"):
            score = add(score, reasons, 560, "tempo_energy_gust_stall")
        if cid == CardIds.PETREL:
            score = add(score, reasons, 500, "tempo_energy_petrel")
    elif payoff == "disrupt_hand":
        if cid == CardIds.ERI:
            score = add(score, reasons, 900, "tempo_hand_eri")
        if cid == CardIds.HAND_TRIMMER:
            score = add(score, reasons, 820, "tempo_hand_trimmer")
        if cid == CardIds.XEROSIC:
            score = add(score, reasons, 740, "tempo_hand_xerosic")
        if cid == CardIds.PETREL:
            score = add(score, reasons, 520, "tempo_hand_petrel")
    elif payoff == "build_attacker":
        if action.has("attach_energy") and (action.has("target_kang") or action.has("target_crustle")):
            score = add(score, reasons, 820, "tempo_build_attach_attacker")
        if cid == CardIds.HILDA:
            score = add(score, reasons, 780, "tempo_build_hilda")
        if cid in {CardIds.PETREL, CardIds.POKEGEAR}:
            score = add(score, reasons, 420, "tempo_build_search_support")
    elif payoff == "pressure":
        if prize.pressure_available:
            if action.has("attack") and prize.pressure_attacker_card_id == state.active_id and not prize.pressure_need_energy:
                score = add(score, reasons, 720, "tempo_pressure_attack")
            if prize.pressure_need_energy and action.has("attach_energy") and action.target_id == prize.pressure_attacker_card_id:
                score = add(score, reasons, 690, "tempo_pressure_attach")
        if action.has("attack"):
            score = add(score, reasons, 300, "tempo_pressure_generic_attack")
    elif payoff == "stabilize":
        if cid == CardIds.PETREL:
            score = add(score, reasons, 520, "stabilize_petrel")
        if cid == CardIds.POKEGEAR:
            score = add(score, reasons, 380, "stabilize_pokegear")
        if action.has("attach_spiky") and (action.has("target_crustle") or action.has("target_kang")):
            score = add(score, reasons, 360, "stabilize_spiky_tank")
        if action.has("draw") and not state.deck_danger:
            score = add(score, reasons, 200, "stabilize_draw")
    elif payoff == "prize":
        s, r = score_prize(action, state, prize)
        score += s; reasons += r
    return score, reasons


def small_general_score(action: ActionView, state) -> tuple[float, list[str]]:
    score = 0.0; reasons: list[str] = []
    if action.has("bench_basic"):
        score = add(score, reasons, 70, "general_bench_basic")
    if action.has("evolve_crustle"):
        score = add(score, reasons, 120, "general_evolve_crustle")
    if action.has("attach_energy"):
        score = add(score, reasons, 35, "general_attach")
    if action.card_id == CardIds.PETREL:
        score = add(score, reasons, 55, "general_petrel")
    if action.card_id == CardIds.POKEGEAR:
        score = add(score, reasons, 35, "general_pokegear")
    if action.has("draw") and not state.deck_danger:
        score = add(score, reasons, 25, "general_draw_safe")
    if action.has("stadium"):
        score = add(score, reasons, 15, "general_stadium")
    return score, reasons


def choose_best(scored: list[ScoredAction], state) -> list[int]:
    if not scored:
        return []
    non_bad = [s for s in scored if s.score > -900]
    selected = non_bad[0] if non_bad else scored[0]
    return [selected.index]
