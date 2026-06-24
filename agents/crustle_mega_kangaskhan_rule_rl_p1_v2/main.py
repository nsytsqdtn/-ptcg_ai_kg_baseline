from __future__ import annotations

import os
import sys
from pathlib import Path

AGENT_DIR = Path(__file__).resolve().parent
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))

from cg.api import to_observation_class

from context_chooser import choose_by_plan
from deck_knowledge import DeckKnowledgeTracker
from debug_logger import log_rule_decision
from emergency_gate import filter_emergency_actions
from finish_search import try_finish_search
from runtime import choose_safe_action, load_deck_from_csv, safe_fallback
from inference import score_actions
from turn_plan import build_state_view, build_turn_plan

DECK_PATH = AGENT_DIR / "deck.csv"
MODEL_EXPORT_PATH = AGENT_DIR / "model_export.json"
my_deck = load_deck_from_csv(DECK_PATH)
deck_knowledge = DeckKnowledgeTracker(my_deck)


def agent(obs_dict: dict) -> list[int]:
    if obs_dict.get("select") is None:
        deck_knowledge.reset()
        return my_deck
    try:
        obs = to_observation_class(obs_dict)
        if obs.select is None or not obs.select.option:
            return []
        deck_knowledge.update(obs, obs_dict=obs_dict)
        snapshot, plan = build_turn_plan(obs, deck_knowledge=deck_knowledge)
        selected = try_finish_search(obs, snapshot, plan, deck_knowledge=deck_knowledge)
        if selected:
            return selected
        state_view = build_state_view(snapshot, plan, deck_knowledge=deck_knowledge)
        # Pure rules for this refactor stage. PPO/policy residual is intentionally not used by main.py.
        scored = score_actions(
            obs,
            MODEL_EXPORT_PATH,
            use_policy=False,
            deck_knowledge=deck_knowledge,
            deck_state=state_view,
            snapshot=snapshot,
            plan=plan,
        )
        scored = filter_emergency_actions(obs, scored, snapshot, plan)
        if not scored:
            return choose_safe_action(len(obs.select.option))
        selected = choose_by_plan(obs, scored, snapshot, plan, deck_knowledge)
        n = len(obs.select.option)
        selected = [i for i in selected if isinstance(i, int) and 0 <= i < n]
        if selected and os.getenv("RULE_DEBUG") == "1":
            log_rule_decision(obs, snapshot, plan, scored, selected)
        if not selected:
            return choose_safe_action(n)
        return selected
    except Exception:
        return safe_fallback(obs_dict)
