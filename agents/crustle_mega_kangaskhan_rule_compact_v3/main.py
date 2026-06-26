from __future__ import annotations

import os
import sys
from pathlib import Path

AGENT_DIR = Path(__file__).resolve().parent
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))

from cg.api import to_observation_class

from ck_compact_core.actions import classify_actions
from ck_compact_core.context import choose_context_action
from ck_compact_core.debug import write_debug
from ck_compact_core.deck_knowledge import DeckKnowledgeTracker
from ck_compact_core.plan_select import choose_plan
from ck_compact_core.prize_plan import build_prize_plan
from ck_compact_core.runtime import choose_safe_action, load_deck_from_csv
from ck_compact_core.score import choose_best, score_actions
from ck_compact_core.setup_plan import build_setup_plan
from ck_compact_core.state import CompactState
from ck_compact_core.tempo_plan import build_tempo_plan

DECK_PATH = AGENT_DIR / "deck.csv"
DEBUG_PATH = Path(os.environ.get("RULE_DEBUG_PATH", str(AGENT_DIR / "compact_v3_debug.jsonl")))

my_deck = load_deck_from_csv(DECK_PATH)
deck_knowledge = DeckKnowledgeTracker(my_deck)
_fallback_count = 0


def _normalize_selection(obs, selected: list[int], scored=None) -> list[int]:
    n = len(getattr(obs.select, "option", []) or [])
    if n <= 0:
        return []
    minc = max(0, min(int(getattr(obs.select, "minCount", 1) or 0), n))
    maxc = max(minc, min(int(getattr(obs.select, "maxCount", 1) or 1), n))
    clean: list[int] = []
    seen = set()
    for i in selected or []:
        if isinstance(i, int) and 0 <= i < n and i not in seen:
            clean.append(i); seen.add(i)
        if len(clean) >= maxc:
            break
    if len(clean) < minc and scored:
        for item in scored:
            i = item.index
            if 0 <= i < n and i not in seen:
                clean.append(i); seen.add(i)
            if len(clean) >= minc:
                break
    if len(clean) < minc:
        for i in range(n):
            if i not in seen:
                clean.append(i); seen.add(i)
            if len(clean) >= minc:
                break
    if not clean and maxc > 0:
        clean = [0]
    return clean[:maxc]


def get_deck() -> list[int]:
    return list(my_deck)


def get_fallback_count() -> int:
    return _fallback_count


def reset_fallback_count() -> None:
    global _fallback_count
    _fallback_count = 0


def agent(obs_dict: dict, configuration=None) -> list[int]:
    if obs_dict.get("select") is None:
        deck_knowledge.reset()
        return get_deck()

    try:
        obs = to_observation_class(obs_dict)
        if getattr(obs, "select", None) is None or not getattr(obs.select, "option", None):
            return []

        deck_knowledge.update(obs, obs_dict=obs_dict)
        state = CompactState.from_obs(obs, deck_knowledge)
        actions = classify_actions(obs, state)
        setup_plan = build_setup_plan(state)
        prize_plan = build_prize_plan(state, actions)
        tempo_plan = build_tempo_plan(state, setup_plan, prize_plan)
        selected_plan = choose_plan(state, setup_plan, tempo_plan, prize_plan)
        scored = score_actions(actions, state, selected_plan, setup_plan, tempo_plan, prize_plan)

        if state.phase == "SELECT":
            selected = choose_context_action(obs, state, actions, selected_plan, setup_plan, tempo_plan, prize_plan, scored=scored)
        else:
            selected = choose_best(scored, state)

        selected = _normalize_selection(obs, selected, scored)
        write_debug(DEBUG_PATH, obs, state, setup_plan, tempo_plan, prize_plan, selected_plan, scored, selected)
        return selected
    except Exception:
        if os.environ.get("RULE_RAISE") == "1":
            raise
        try:
            global _fallback_count
            obs = to_observation_class(obs_dict)
            n = len(getattr(obs.select, "option", []) or []) if getattr(obs, "select", None) is not None else 0
            _fallback_count += 1
            return choose_safe_action(n)
        except Exception:
            return [0]
