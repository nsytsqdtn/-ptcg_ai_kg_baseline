from __future__ import annotations

from dataclasses import dataclass

from runtime import get_card_name


@dataclass
class MatchupProfile:
    name: str
    prefers_crustle_wall: bool
    values_mist_energy: bool
    values_bench_protection: bool
    values_disruption: bool
    values_gust_on_setup_targets: bool
    tags: list[str]


def detect_matchup_profile(obs) -> MatchupProfile:
    state = obs.current
    my_index = state.yourIndex
    op_state = state.players[1 - my_index]
    visible_cards = [card for card in op_state.active + op_state.bench + getattr(op_state, "discard", []) if card is not None]
    names = " | ".join(get_card_name(card).lower() for card in visible_cards)

    if "dragapult" in names:
        return MatchupProfile(
            name="dragapult_ex",
            prefers_crustle_wall=True,
            values_mist_energy=True,
            values_bench_protection=True,
            values_disruption=True,
            values_gust_on_setup_targets=True,
            tags=["bench_damage_threat", "effect_damage_threat", "gust_setup_targets", "wall_plus_mist_matchup"],
        )
    if "lucario" in names:
        return MatchupProfile(
            name="mega_lucario",
            prefers_crustle_wall=True,
            values_mist_energy=False,
            values_bench_protection=False,
            values_disruption=True,
            values_gust_on_setup_targets=False,
            tags=["ex_pressure", "wall_matchup"],
        )
    return MatchupProfile(
        name="unknown",
        prefers_crustle_wall=False,
        values_mist_energy=False,
        values_bench_protection=False,
        values_disruption=False,
        values_gust_on_setup_targets=False,
        tags=["unknown_matchup", "stable_default"],
    )
