from __future__ import annotations

from dataclasses import dataclass

from runtime import prize_count


@dataclass(frozen=True)
class Obligations:
    must_keep_pokemon_in_play: bool = False
    must_add_backup: bool = False
    must_not_end_turn: bool = False
    must_not_attack: bool = False
    must_not_retreat: bool = False
    must_not_draw: bool = False
    must_preserve_wall: bool = False
    must_preserve_deck: bool = False
    must_preserve_supporter: bool = False


def _opponent_can_win_by_active_ko(snapshot) -> bool:
    active_prizes = prize_count(snapshot.active) if snapshot.active is not None else 1
    return snapshot.opponent_prizes_left <= active_prizes


def build_obligations(snapshot, deck_knowledge=None) -> Obligations:
    """Build hard, global obligations before choosing a plan.

    These are not scoring hints. If an obligation applies, the contract layer
    must filter actions that violate it unless no legal alternative remains.
    """
    field_count = int(getattr(snapshot, "field_count", 0) or 0)
    turn = int(getattr(getattr(snapshot, "state", None), "turn", 0) or 0)
    bench_space = int(getattr(snapshot, "bench_space", 0) or 0)
    only_one = field_count <= 1
    early_low_field = turn <= 5 and field_count < 3 and bench_space > 0
    active_threat = bool(getattr(snapshot, "active_under_ko_threat", False))
    opponent_win_by_active = _opponent_can_win_by_active_ko(snapshot)
    wall_valid = bool(getattr(snapshot, "wall_valid", False))
    can_win_now = bool(getattr(snapshot, "can_win_now", False))
    safe_draws = int(getattr(snapshot, "safe_draws", 0) or 0)
    supporter_available = not bool(getattr(getattr(snapshot, "state", None), "supporterPlayed", False))

    # A valid Crustle wall can relax backup urgency, but only if it is actually
    # blocking the opponent's active ex. Otherwise keep the early-field contract.
    must_add_backup = (
        (only_one and bench_space > 0)
        or early_low_field
        or (active_threat and field_count < 3 and bench_space > 0)
        or (opponent_win_by_active and field_count < 3 and bench_space > 0)
    )
    if wall_valid and field_count >= 2:
        must_add_backup = False

    must_not_end_turn = (
        (only_one and bench_space > 0)
        or (active_threat and field_count < 2)
        or (opponent_win_by_active and field_count < 2)
    )
    if wall_valid and field_count >= 2:
        must_not_end_turn = False

    must_not_draw = safe_draws <= 0 and not can_win_now

    return Obligations(
        must_keep_pokemon_in_play=only_one or (active_threat and field_count < 3),
        must_add_backup=must_add_backup,
        must_not_end_turn=must_not_end_turn,
        must_not_attack=must_not_end_turn,
        must_not_retreat=field_count <= 1,
        must_not_draw=must_not_draw,
        must_preserve_wall=bool(getattr(snapshot, "wall_online", False)),
        must_preserve_deck=must_not_draw,
        must_preserve_supporter=must_add_backup and supporter_available,
    )
