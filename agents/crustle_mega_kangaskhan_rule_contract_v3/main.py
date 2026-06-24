from __future__ import annotations

import sys
from pathlib import Path

AGENT_DIR = Path(__file__).resolve().parent
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))

from cg.api import to_observation_class

from action_classifier import classify_actions
from context_chooser import choose_by_plan
from deck_knowledge import DeckKnowledgeTracker
from decision_contract import apply_decision_contract
from finish_search import try_finish_search_if_applicable
from inference import score_actions
from obligations import build_obligations
from runtime import choose_safe_action, load_deck_from_csv
from turn_plan import BoardSnapshot, build_turn_plan, build_state_view

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
        snapshot = BoardSnapshot.from_obs(obs, deck_knowledge)
        obligations = build_obligations(snapshot, deck_knowledge)
        plan = build_turn_plan(snapshot, obligations, deck_knowledge)

        legal_indices = list(range(len(obs.select.option)))
        classified = classify_actions(obs, legal_indices, snapshot, obligations, plan, deck_knowledge)
        allowed = apply_decision_contract(obs, classified, snapshot, obligations, plan, deck_knowledge)
        allowed_indices = [action.index for action in allowed]

        finish = try_finish_search_if_applicable(obs, snapshot, obligations, plan, deck_knowledge, allowed_indices)
        if finish:
            return finish

        deck_state = build_state_view(snapshot, plan, deck_knowledge)
        scored = score_actions(
            obs,
            MODEL_EXPORT_PATH,
            use_policy=False,
            deck_knowledge=deck_knowledge,
            deck_state=deck_state,
            snapshot=snapshot,
            plan=plan,
            obligations=obligations,
            allowed=allowed,
        )
        if not scored:
            return choose_safe_action(len(obs.select.option))

        selected = choose_by_plan(obs, scored, snapshot, plan, deck_knowledge=deck_knowledge, obligations=obligations)
        n = len(obs.select.option)
        selected = [i for i in selected if isinstance(i, int) and 0 <= i < n]
        if not selected:
            return choose_safe_action(n)
        return selected
    except Exception:
        try:
            obs = to_observation_class(obs_dict)
            return choose_safe_action(len(obs.select.option) if obs.select is not None else 0)
        except Exception:
            return [0]
