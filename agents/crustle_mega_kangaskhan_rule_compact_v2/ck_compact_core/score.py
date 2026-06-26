from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .actions import ActionView
from .runtime import CardIds, get_card_name_en


@dataclass
class ScoredAction:
    action: ActionView
    score: float
    reasons: list[str]

    @property
    def index(self) -> int:
        return self.action.index


def score_actions(actions: list[ActionView], state, selected_plan: str, setup, wall, prize) -> list[ScoredAction]:
    scored: list[ScoredAction] = []
    for action in actions:
        score, reasons = score_action(action, state, selected_plan, setup, wall, prize)
        scored.append(ScoredAction(action=action, score=score, reasons=reasons))
    scored.sort(key=lambda x: x.score, reverse=True)
    return scored


def score_action(action: ActionView, state, selected_plan: str, setup, wall, prize) -> tuple[float, list[str]]:
    score = 0.0
    reasons: list[str] = []

    s, r = safety_score(action, state)
    score += s; reasons += r

    if selected_plan == "setup":
        s, r = score_setup(action, state, setup)
    elif selected_plan == "wall":
        s, r = score_wall(action, state, wall, prize)
    elif selected_plan == "prize":
        s, r = score_prize(action, state, prize)
    else:
        s, r = 0.0, []
    score += s; reasons += r

    s, r = small_general_score(action, state)
    score += s; reasons += r

    return score, reasons


def add(score: float, reasons: list[str], value: float, reason: str) -> float:
    reasons.append(reason)
    return score + value


def safety_score(action: ActionView, state) -> tuple[float, list[str]]:
    score = 0.0
    reasons: list[str] = []
    if state.deck_danger and action.has("draw"):
        score = add(score, reasons, -1200, "block_draw_deck_danger")
    if state.field_count <= 1 and action.has("attack"):
        score = add(score, reasons, -1200, "avoid_attack_single_pokemon")
    if state.field_count <= 1 and action.has("end_turn"):
        score = add(score, reasons, -1000, "avoid_end_single_pokemon")
    if state.active_under_threat and state.field_count <= 2 and action.has("end_turn") and not action.has("attack"):
        score = add(score, reasons, -360, "avoid_pass_under_active_threat")
    if action.has("ascension_attack") and state.field_count <= 1:
        score = add(score, reasons, -1400, "avoid_ascension_no_backup")
    if state.wall_status == "online" and state.crustle_active and (action.has("retreat") or action.has("switch")):
        score = add(score, reasons, -450, "preserve_online_crustle_wall")
    if action.has("draw") and state.safe_draws <= 2:
        score = add(score, reasons, -180, "low_safe_draws")
    return score, reasons


def score_setup(action: ActionView, state, setup) -> tuple[float, list[str]]:
    score = 0.0
    reasons: list[str] = []
    cid = action.card_id

    if setup.need_backup:
        if action.has("bench_basic") and cid == CardIds.DWEBBLE:
            score = add(score, reasons, 1050, "setup_backup_play_dwebble")
        elif action.has("bench_basic") and cid == CardIds.MEGA_KANGASKHAN_EX:
            score = add(score, reasons, 760, "setup_backup_play_kang")
        if cid == CardIds.BUDDY_BUDDY_POFFIN:
            score = add(score, reasons, 930, "setup_backup_poffin")
        if cid == CardIds.ULTRA_BALL:
            score = add(score, reasons, 680, "setup_backup_ultra_ball")
        if cid == CardIds.HILDA:
            score = add(score, reasons, 620, "setup_backup_hilda")
        if cid == CardIds.PETREL:
            score = add(score, reasons, 530, "setup_backup_petrel")
        if cid == CardIds.POKEGEAR:
            score = add(score, reasons, 360, "setup_backup_pokegear")
        if action.has("attack") or action.has("end_turn"):
            score = add(score, reasons, -900, "setup_backup_no_end_turn")

    if setup.need_dwebble:
        if action.has("bench_basic") and cid == CardIds.DWEBBLE:
            score = add(score, reasons, 900, "need_dwebble_play")
        if cid == CardIds.BUDDY_BUDDY_POFFIN:
            score = add(score, reasons, 820, "need_dwebble_poffin")
        if cid in {CardIds.ULTRA_BALL, CardIds.PETREL, CardIds.POKEGEAR}:
            score = add(score, reasons, 380, "need_dwebble_search_route")

    if setup.need_crustle:
        if action.has("evolve_crustle"):
            score = add(score, reasons, 1150, "need_crustle_evolve")
        if cid == CardIds.HILDA:
            score = add(score, reasons, 850, "need_crustle_hilda")
        if cid == CardIds.ULTRA_BALL:
            score = add(score, reasons, 730, "need_crustle_ultra_ball")
        if cid == CardIds.PETREL:
            score = add(score, reasons, 520, "need_crustle_petrel")
        if action.has("ascension_attack") and setup.allow_ascension:
            score = add(score, reasons, 840, "safe_dwebble_ascension")
        if action.has("ascension_attack") and not setup.allow_ascension:
            score = add(score, reasons, -1200, "unsafe_dwebble_ascension")

    if setup.need_crustle_active:
        if action.has("switch"):
            score = add(score, reasons, 880, "need_crustle_active_switch")
        if action.has("evolve_crustle"):
            score = add(score, reasons, 720, "need_crustle_active_evolve")

    if setup.need_energy_for_crustle:
        if action.has("attach_growing_grass") and (action.has("target_dwebble") or action.has("target_crustle")):
            score = add(score, reasons, 650, "prepare_crustle_growing_grass")
        elif action.has("attach_basic_grass") and (action.has("target_dwebble") or action.has("target_crustle")):
            score = add(score, reasons, 540, "prepare_crustle_basic_grass")
        elif action.has("attach_mist") and (action.has("target_dwebble") or action.has("target_crustle")):
            score = add(score, reasons, 360, "prepare_crustle_mist")

    return score, reasons


def score_prize(action: ActionView, state, prize) -> tuple[float, list[str]]:
    score = 0.0
    reasons: list[str] = []
    if not prize.available:
        return score, reasons
    if prize.wins_game:
        score = add(score, reasons, 1800, "prize_wins_game")
    if action.has("attack") and prize.attacker_slot == "active" and not prize.need_energy:
        score = add(score, reasons, 1200, "prize_attack")
    if prize.need_energy and action.has("attach_energy") and action.target_id == prize.attacker_card_id:
        score = add(score, reasons, 980, "prize_attach_to_enable_attack")
    if prize.route == "boss" and action.card_id == CardIds.BOSS_ORDERS:
        score = add(score, reasons, 1120, "prize_boss")
    if prize.route == "lisia" and action.card_id == CardIds.LISIA:
        score = add(score, reasons, 1040, "prize_lisia")
    if prize.route == "petrel_to_boss" and action.card_id == CardIds.PETREL:
        score = add(score, reasons, 720 if prize.confidence == "confirmed" else 420, "prize_petrel_to_gust")
    if prize.need_switch and action.has("switch"):
        score = add(score, reasons, 830, "prize_switch_attacker")
    if not prize.need_energy and action.has("attach_energy") and action.target_id == prize.attacker_card_id:
        score = add(score, reasons, 300, "prize_prepare_attacker")
    return score, reasons


def score_wall(action: ActionView, state, wall, prize) -> tuple[float, list[str]]:
    score = 0.0
    reasons: list[str] = []
    cid = action.card_id

    # A confirmed non-breaking prize remains a useful secondary pressure, but it
    # does not replace the wall plan unless plan_select chose PrizePlan.
    if prize.available and prize.confidence == "confirmed" and not prize.breaks_wall:
        if action.has("attack") and prize.attacker_slot == "active":
            score = add(score, reasons, 430, "wall_small_confirmed_prize_attack")
        if action.has("gust") and prize.route in {"boss", "lisia"}:
            score = add(score, reasons, 360, "wall_small_confirmed_gust")

    if wall.preferred_response == "heal":
        if cid == CardIds.JUMBO_ICE_CREAM:
            score = add(score, reasons, 940, "wall_heal_jumbo")
        if cid == CardIds.BIANCA_DEVOTION:
            score = add(score, reasons, 900, "wall_heal_bianca")
        if cid == CardIds.HERO_CAPE:
            score = add(score, reasons, 690, "wall_heal_hero_cape")
        if action.has("switch"):
            score = add(score, reasons, 360, "wall_heal_switch")

    elif wall.preferred_response == "energy_disrupt":
        if cid == CardIds.XEROSIC:
            score = add(score, reasons, 850, "wall_energy_xerosic")
        if cid == CardIds.HANDHELD_FAN:
            score = add(score, reasons, 730, "wall_energy_fan")
        if action.has("gust"):
            score = add(score, reasons, 470, "wall_energy_gust_stall")
        if cid == CardIds.PETREL:
            score = add(score, reasons, 420, "wall_energy_petrel")

    elif wall.preferred_response == "protect_core":
        if action.has("attach_mist") and action.has("target_core"):
            score = add(score, reasons, 800, "wall_protect_core_mist")
        if cid == CardIds.JUMBO_ICE_CREAM:
            score = add(score, reasons, 600, "wall_protect_core_heal")
        if action.has("switch"):
            score = add(score, reasons, 450, "wall_protect_core_switch")
        if action.has("disruption"):
            score = add(score, reasons, 360, "wall_protect_core_disruption")

    elif wall.preferred_response == "hand_disrupt":
        if cid == CardIds.ERI:
            score = add(score, reasons, 850, "wall_hand_eri")
        if cid == CardIds.HAND_TRIMMER:
            score = add(score, reasons, 760, "wall_hand_trimmer")
        if cid == CardIds.XEROSIC:
            score = add(score, reasons, 700, "wall_hand_xerosic")
        if cid == CardIds.PETREL:
            score = add(score, reasons, 420, "wall_hand_petrel")

    else:
        if cid == CardIds.PETREL:
            score = add(score, reasons, 520, "wall_wait_petrel")
        if cid == CardIds.POKEGEAR:
            score = add(score, reasons, 360, "wall_wait_pokegear")
        if action.has("attach_spiky") and (action.has("target_crustle") or action.has("target_kang")):
            score = add(score, reasons, 340, "wall_wait_spiky")
        if action.has("attach_mist") and action.has("target_core"):
            score = add(score, reasons, 260, "wall_wait_mist_core")
        if prize.pressure_available:
            if action.has("attack") and prize.pressure_attacker_card_id == state.active_id and not prize.pressure_need_energy:
                score = add(score, reasons, 520, "wall_wait_pressure_attack")
            if prize.pressure_need_energy and action.has("attach_energy") and action.target_id == prize.pressure_attacker_card_id:
                score = add(score, reasons, 500, "wall_wait_pressure_attach")
        if action.has("attack"):
            score = add(score, reasons, 300, "wall_wait_attack")

    return score, reasons


def small_general_score(action: ActionView, state) -> tuple[float, list[str]]:
    score = 0.0
    reasons: list[str] = []
    if action.has("bench_basic"):
        score = add(score, reasons, 70, "general_bench_basic")
    if action.has("evolve_crustle"):
        score = add(score, reasons, 120, "general_evolve_crustle")
    if action.has("attach_energy"):
        score = add(score, reasons, 35, "general_attach_energy")
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
    n = len(scored)
    # Prefer the best non-catastrophic action if available.
    non_bad = [s for s in scored if s.score > -800]
    selected = non_bad[0] if non_bad else scored[0]
    return [selected.index]
