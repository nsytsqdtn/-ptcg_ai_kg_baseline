from __future__ import annotations

import sys
from pathlib import Path


AGENT_DIR = Path(__file__).resolve().parent
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))

from cg.api import to_observation_class

from context_chooser import choose_actions_by_context
from deck_knowledge import DeckKnowledgeTracker
from deck_state import analyze_deck_state
from runtime import choose_safe_action, load_deck_from_csv
from inference import choose_ranked_actions, score_actions


DECK_PATH = AGENT_DIR / "deck.csv"
MODEL_EXPORT_PATH = AGENT_DIR / "model_export.json"
my_deck = load_deck_from_csv(DECK_PATH)
deck_knowledge = DeckKnowledgeTracker(my_deck)


def agent(obs_dict: dict) -> list[int]:
    if obs_dict.get("select") is None:
        return my_deck
    obs = to_observation_class(obs_dict)
    if obs.select is None or not obs.select.option:
        return []
    deck_knowledge.update(obs, obs_dict=obs_dict)
    deck_state = analyze_deck_state(obs, deck_knowledge=deck_knowledge)
    scored = score_actions(obs, MODEL_EXPORT_PATH, use_policy=True, deck_knowledge=deck_knowledge)
    if not scored:
        return choose_safe_action(len(obs.select.option))
    return choose_actions_by_context(obs, scored, deck_state, deck_knowledge)
