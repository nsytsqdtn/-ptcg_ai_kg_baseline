from __future__ import annotations

from turn_plan import build_state_view, build_turn_plan


def analyze_deck_state(obs, deck_knowledge=None):
    snapshot, plan = build_turn_plan(obs, deck_knowledge=deck_knowledge)
    return build_state_view(snapshot, plan, deck_knowledge=deck_knowledge)
