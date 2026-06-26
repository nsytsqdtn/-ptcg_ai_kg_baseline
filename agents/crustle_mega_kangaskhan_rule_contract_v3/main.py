from __future__ import annotations

import json
import os
import sys
from pathlib import Path

AGENT_DIR = Path(__file__).resolve().parent
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))

from cg.api import to_observation_class

from ck_contract_core.action_classifier import classify_actions
from ck_contract_core.context_chooser import choose_by_plan
from ck_contract_core.deck_knowledge import DeckKnowledgeTracker
from ck_contract_core.decision_contract import apply_decision_contract
from ck_contract_core.finish_search import try_finish_search_if_applicable
from ck_contract_core.inference import score_actions
from ck_contract_core.obligations import build_obligations
from ck_contract_core.runtime import choose_safe_action, load_deck_from_csv, get_card_name
from ck_contract_core.turn_plan import BoardSnapshot, build_turn_plan, build_state_view

DECK_PATH = AGENT_DIR / "deck.csv"
MODEL_EXPORT_PATH = AGENT_DIR / "model_export.json"
my_deck = load_deck_from_csv(DECK_PATH)
deck_knowledge = DeckKnowledgeTracker(my_deck)
RULE_DEBUG = os.environ.get("RULE_DEBUG") == "1"
DEBUG_PATH = Path(os.environ.get("RULE_DEBUG_PATH", str(AGENT_DIR / "rule_debug.jsonl")))


def _action_label(obs, idx: int) -> str:
    try:
        option = obs.select.option[idx]
        t = getattr(option, "type", None)
        parts = [str(t).split(".")[-1]]
        card = None
        if hasattr(option, "index"):
            if t.name == "PLAY":
                card = obs.current.players[obs.current.yourIndex].hand[option.index]
            elif t.name == "ATTACH":
                card = obs.current.players[obs.current.yourIndex].hand[option.index]
            elif t.name == "EVOLVE":
                card = obs.current.players[obs.current.yourIndex].hand[option.index]
        if card is not None:
            parts.append(get_card_name(card))
        return " ".join(parts)
    except Exception:
        return f"idx:{idx}"


def _debug_write(obs, snapshot, obligations, plan, classified, allowed, scored, selected):
    if not RULE_DEBUG:
        return
    try:
        allowed_set = {a.index for a in allowed}
        blocked = [a for a in classified if a.index not in allowed_set]
        rec = {
            "turn": getattr(snapshot.state, "turn", None),
            "context": str(getattr(obs.select, "context", "")),
            "objective": plan.objective,
            "reasons": list(plan.reasons),
            "obligations": getattr(obligations, "__dict__", {}),
            "blocked_top": [
                {"index": a.index, "action": _action_label(obs, a.index), "tags": sorted(a.tags), "reason": list(a.reason)}
                for a in blocked[:8]
            ],
            "allowed_top": [
                {"index": a.index, "action": _action_label(obs, a.index), "tags": sorted(a.tags)}
                for a in allowed[:8]
            ],
            "scored_top": [
                {"index": s.index, "action": _action_label(obs, s.index), "score": s.total_logit, "tags": s.prior.get("reason_tags", [])[:12]}
                for s in scored[:8]
            ],
            "selected": selected,
            "selected_labels": [_action_label(obs, i) for i in selected],
        }
        with DEBUG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        return


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

        finish = try_finish_search_if_applicable(obs, snapshot, obligations, plan, deck_knowledge, allowed_indices, allowed)
        if finish:
            _debug_write(obs, snapshot, obligations, plan, classified, allowed, [], finish)
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
        # Normalize against minCount/maxCount. Context resolvers may return fewer
        # than minCount when exact route targets collapse to the same option.
        minc = max(0, min(getattr(obs.select, "minCount", 1), n))
        maxc = max(minc, min(getattr(obs.select, "maxCount", 1), n))
        clean = []
        seen = set()
        for i in selected:
            if isinstance(i, int) and 0 <= i < n and i not in seen:
                clean.append(i); seen.add(i)
            if len(clean) >= maxc:
                break
        if len(clean) < minc:
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
        selected = clean[:maxc] if clean else choose_safe_action(n)
        _debug_write(obs, snapshot, obligations, plan, classified, allowed, scored, selected)
        return selected
    except Exception:
        if os.environ.get("RULE_RAISE") == "1":
            raise
        try:
            obs = to_observation_class(obs_dict)
            n = len(obs.select.option) if obs.select is not None else 0
            minc = max(0, min(getattr(obs.select, "minCount", 1), n)) if obs.select is not None else 0
            return list(range(minc if minc > 0 else min(1, n)))
        except Exception:
            return [0]
