from __future__ import annotations

from dataclasses import dataclass

from .runtime import get_card_name


@dataclass(frozen=True)
class ThreatProfile:
    has_fast_prize_pressure: bool = False
    has_bench_spread: bool = False
    has_gust_pressure: bool = False
    has_non_ex_wall_breaker: bool = False
    requires_mist_on_core: bool = False
    threatens_active_ko_fast: bool = False


@dataclass
class MatchupProfile:
    name: str
    prefers_crustle_wall: bool
    values_mist_energy: bool
    values_bench_protection: bool
    values_disruption: bool
    values_gust_on_setup_targets: bool
    tags: list[str]
    threat: ThreatProfile


def detect_matchup_profile(obs) -> MatchupProfile:
    state = obs.current
    my_index = state.yourIndex
    op_state = state.players[1 - my_index]
    visible_cards = [card for card in op_state.active + op_state.bench + getattr(op_state, "discard", []) if card is not None]
    names = " | ".join(get_card_name(card).lower() for card in visible_cards)

    if "dragapult" in names or "dreepy" in names or "drakloak" in names:
        threat = ThreatProfile(
            has_bench_spread=True,
            has_gust_pressure=True,
            requires_mist_on_core=True,
        )
        return MatchupProfile(
            name="dragapult_ex",
            prefers_crustle_wall=True,
            values_mist_energy=True,
            values_bench_protection=True,
            values_disruption=True,
            values_gust_on_setup_targets=True,
            tags=["bench_damage_threat", "effect_damage_threat", "gust_setup_targets", "wall_plus_mist_matchup"],
            threat=threat,
        )
    if "lucario" in names or "hariyama" in names or "makuhita" in names:
        threat = ThreatProfile(
            has_fast_prize_pressure=True,
            has_non_ex_wall_breaker=True,
            threatens_active_ko_fast=True,
        )
        return MatchupProfile(
            name="mega_lucario",
            prefers_crustle_wall=True,
            values_mist_energy=False,
            values_bench_protection=False,
            values_disruption=True,
            values_gust_on_setup_targets=False,
            tags=["ex_pressure", "wall_matchup", "fast_prize_pressure"],
            threat=threat,
        )
    return MatchupProfile(
        name="unknown",
        prefers_crustle_wall=False,
        values_mist_energy=False,
        values_bench_protection=False,
        values_disruption=False,
        values_gust_on_setup_targets=False,
        tags=["unknown_matchup", "stable_default"],
        threat=ThreatProfile(),
    )
