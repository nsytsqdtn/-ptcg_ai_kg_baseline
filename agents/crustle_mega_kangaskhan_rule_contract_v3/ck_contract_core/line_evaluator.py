from __future__ import annotations

from dataclasses import dataclass

from .runtime import CardIds, energy_count


@dataclass
class LineState:
    name: str
    priority: float
    is_online: bool
    missing: set[str]
    blocked: bool
    block_reasons: list[str]
    tag_solves_missing: dict[str, set[str]]
    blocking_risks: set[str]


@dataclass
class LineScores:
    crustle_wall_line: float
    kang_tank_line: float
    heal_escape_line: float
    disruption_line: float
    finish_pressure_line: float
    attack_continuity_line: float

    @property
    def primary_line(self) -> str:
        scores = {
            "crustle_wall_line": self.crustle_wall_line,
            "kang_tank_line": self.kang_tank_line,
            "heal_escape_line": self.heal_escape_line,
            "disruption_line": self.disruption_line,
            "finish_pressure_line": self.finish_pressure_line,
            "attack_continuity_line": self.attack_continuity_line,
        }
        return max(scores, key=scores.get)


def _deck_has(deck_knowledge, card_id: int):
    if deck_knowledge is None:
        return None
    return deck_knowledge.deck_has(card_id)


def build_line_states(deck_state, matchup, active, opponent_active, deck_knowledge=None) -> list[LineState]:
    active_id = getattr(active, "id", None)
    crustle_online = deck_state.wall_online
    crustle_missing: set[str] = set()
    crustle_blocked = False
    crustle_block_reasons: list[str] = []
    if deck_state.crustle_in_play == 0:
        crustle_has = _deck_has(deck_knowledge, CardIds.CRUSTLE)
        if crustle_has is False:
            crustle_blocked = True
            crustle_block_reasons.append("crustle_not_in_deck")
        else:
            crustle_missing.add("crustle")
    if deck_state.dwebble_in_play == 0 and deck_state.crustle_in_play == 0:
        dwebble_has = _deck_has(deck_knowledge, CardIds.DWEBBLE)
        if dwebble_has is False:
            crustle_blocked = True
            crustle_block_reasons.append("dwebble_not_in_deck")
        else:
            crustle_missing.add("dwebble")
    if deck_state.crustle_in_play == 0:
        grow_has = _deck_has(deck_knowledge, CardIds.GROW_GRASS_ENERGY)
        basic_has = _deck_has(deck_knowledge, CardIds.BASIC_GRASS)
        if grow_has is False and basic_has is False:
            crustle_missing.add("grass_energy_hard")
        else:
            crustle_missing.add("grass_energy")
    if getattr(deck_state, "must_bench_basic", False):
        crustle_missing.add("bench_basic")
    kang_missing: set[str] = set()
    kang_blocked = False
    kang_block_reasons: list[str] = []
    if deck_state.kangaskhan_in_play == 0:
        kang_has = _deck_has(deck_knowledge, CardIds.MEGA_KANGASKHAN_EX)
        if kang_has is False:
            kang_blocked = True
            kang_block_reasons.append("kang_not_in_deck")
        else:
            kang_missing.add("kang")
    if deck_state.active_energy < 2:
        kang_missing.add("kang_energy")
    drag_missing: set[str] = set()
    if matchup.name == "dragapult_ex" and deck_state.bench_risk:
        mist_has = _deck_has(deck_knowledge, CardIds.MIST_ENERGY)
        if mist_has is not False:
            drag_missing.add("mist")
    return [
        LineState(
            name="crustle_wall",
            priority=1.35 if matchup.prefers_crustle_wall else 0.8,
            is_online=crustle_online,
            missing=crustle_missing,
            blocked=crustle_blocked,
            block_reasons=crustle_block_reasons,
            tag_solves_missing={
                "bench_dwebble": {"dwebble", "bench_basic"},
                "bench_kang": {"bench_basic"},
                "poffin_target_dwebble": {"dwebble", "bench_basic"},
                "poffin_target_kang": {"bench_basic"},
                "hilda_target_dwebble": {"dwebble", "bench_basic"},
                "hilda_target_crustle": {"crustle"},
                "hilda_target_growing_grass": {"grass_energy"},
                "hilda_target_basic_grass": {"grass_energy"},
                "ultra_ball_target_crustle": {"crustle"},
                "ultra_ball_target_dwebble": {"dwebble", "bench_basic"},
                "ascension": {"crustle"},
                "evolve_crustle": {"crustle"},
                "switch_crustle": set(),
            },
            blocking_risks={"delay_bench_basic", "bad_gust_target"},
        ),
        LineState(
            name="kang_tank",
            priority=1.1 if deck_state.active_is_kangaskhan else 0.7,
            is_online=deck_state.active_is_kangaskhan and deck_state.active_energy >= 2,
            missing=kang_missing,
            blocked=kang_blocked,
            block_reasons=kang_block_reasons,
            tag_solves_missing={
                "bench_kang": {"kang"},
                "poffin_target_kang": {"kang"},
                "hilda_target_kang": {"kang"},
                "ultra_ball_target_kang": {"kang"},
                "attach_kang_energy": {"kang_energy"},
                "spiky_active": set(),
                "jumbo_heal": set(),
                "bianca_heal": set(),
            },
            blocking_risks={"delay_bench_basic"},
        ),
        LineState(
            name="dragapult_protect",
            priority=1.25 if matchup.name == "dragapult_ex" else 0.2,
            is_online=matchup.name != "dragapult_ex" or not deck_state.bench_risk,
            missing=drag_missing,
            blocked=False,
            block_reasons=[],
            tag_solves_missing={
                "hilda_target_mist": {"mist"},
                "mist_protect": {"mist"},
                "evolve_crustle": set(),
                "gust_setup_basic": set(),
            },
            blocking_risks={"delay_bench_basic"},
        ),
    ]


def evaluate_lines(deck_state, matchup, active, opponent_active) -> LineScores:
    crustle_wall_line = 0.0
    if deck_state.wall_online:
        crustle_wall_line += 1.2
    elif matchup.prefers_crustle_wall and deck_state.setup_missing_crustle:
        crustle_wall_line += 0.8
    elif matchup.prefers_crustle_wall and deck_state.crustle_in_play > 0:
        crustle_wall_line += 0.5

    kang_tank_line = 0.0
    if deck_state.active_is_kangaskhan:
        kang_tank_line += 0.8
        kang_tank_line += min(0.4, deck_state.active_energy * 0.1)
    elif deck_state.kangaskhan_in_play > 0 and not deck_state.wall_online:
        kang_tank_line += 0.5
    if deck_state.heal_prevents_ko:
        kang_tank_line += 0.3

    heal_escape_line = 0.6 if deck_state.heal_prevents_ko else 0.0
    if deck_state.bianca_window:
        heal_escape_line += 0.2

    disruption_line = 0.0
    if deck_state.disruption_window:
        disruption_line += 0.5
    if matchup.values_disruption:
        disruption_line += 0.2
    if deck_state.wall_online and deck_state.disruption_window:
        disruption_line += 0.3

    finish_pressure_line = 0.0
    if deck_state.gust_for_win:
        finish_pressure_line += 1.5
    elif deck_state.gust_for_prize:
        finish_pressure_line += 0.8

    attack_continuity_line = 0.0
    if deck_state.can_attack_now:
        attack_continuity_line += 0.8
    if active is not None:
        if active.id == CardIds.CRUSTLE and energy_count(active) >= 1:
            attack_continuity_line += 0.3
        if active.id == CardIds.MEGA_KANGASKHAN_EX and energy_count(active) >= 3:
            attack_continuity_line += 0.4
    if opponent_active is not None and getattr(opponent_active, "hp", 999) <= 120:
        attack_continuity_line += 0.2

    return LineScores(
        crustle_wall_line=crustle_wall_line,
        kang_tank_line=kang_tank_line,
        heal_escape_line=heal_escape_line,
        disruption_line=disruption_line,
        finish_pressure_line=finish_pressure_line,
        attack_continuity_line=attack_continuity_line,
    )


def score_line_progress(action_tags: set[str], line_states: list[LineState]) -> float:
    total = 0.0
    for line in line_states:
        if line.blocked and line.missing:
            continue
        solved_missing: set[str] = set()
        for tag in action_tags:
            solved_missing.update(line.tag_solves_missing.get(tag, set()) & line.missing)
        if solved_missing:
            total += 34.0 * line.priority * max(1, len(solved_missing))
        elif line.is_online and action_tags & set(line.tag_solves_missing.keys()):
            total += 18.0 * line.priority
        if action_tags & line.blocking_risks:
            total -= 24.0 * line.priority
    return total
