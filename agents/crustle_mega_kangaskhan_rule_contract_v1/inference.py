from __future__ import annotations

import json
import math
import os
import random
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from action_encoder import encode_action
from deck_state import analyze_deck_state
from observation_builder import build_observation_features
from policy import load_exported_policy
from rule_prior import score_option
from runtime import CardIds, get_card_name
from cg.api import AreaType, OptionType


@dataclass
class ScoredAction:
    index: int
    total_logit: float
    rule_logit: float
    policy_logit: float
    observation_features: list[float]
    action_features: list[float]
    prior: dict[str, Any]


def _softmax(logits: list[float]) -> list[float]:
    if not logits:
        return []
    max_logit = max(logits)
    weights = [math.exp(logit - max_logit) for logit in logits]
    total = sum(weights)
    return [weight / total for weight in weights]


def normalize_rule_logits(raw_rule_scores: list[float]) -> list[float]:
    if not raw_rule_scores:
        return []
    if len(raw_rule_scores) == 1:
        return [0.0]
    mean = sum(raw_rule_scores) / float(len(raw_rule_scores))
    variance = sum((score - mean) ** 2 for score in raw_rule_scores) / float(len(raw_rule_scores))
    std = max(variance**0.5, 1e-6)
    return [max(-3.0, min(3.0, (score - mean) / std)) for score in raw_rule_scores]


def _card_for_option(obs, option):
    state = obs.current
    yi = state.yourIndex
    if option.type == OptionType.PLAY:
        return state.players[yi].hand[option.index]
    if option.type == OptionType.CARD:
        if option.area == AreaType.HAND:
            return state.players[option.playerIndex].hand[option.index]
        if option.area == AreaType.DECK:
            return obs.select.deck[option.index]
        if option.area == AreaType.ACTIVE:
            return state.players[option.playerIndex].active[option.index]
        if option.area == AreaType.BENCH:
            return state.players[option.playerIndex].bench[option.index]
    return None


def _context_name(obs) -> str | None:
    context = getattr(getattr(obs, "select", None), "context", None)
    if context is None:
        return None
    return getattr(context, "name", None) or str(context)


def _describe_option(obs, option) -> str:
    card = _card_for_option(obs, option)
    card_name = get_card_name(card) if card is not None else None
    option_name = getattr(option.type, "name", str(option.type))
    if option.type == OptionType.PLAY and card_name:
        return f"PLAY {card_name}"
    if option.type == OptionType.ATTACH and card_name:
        area = getattr(getattr(option, "inPlayArea", None), "name", str(getattr(option, "inPlayArea", "")))
        return f"ATTACH {card_name} -> {area}:{getattr(option, 'inPlayIndex', 0)}"
    if option.type == OptionType.CARD and card_name:
        area = getattr(getattr(option, "area", None), "name", str(getattr(option, "area", "")))
        return f"CARD {card_name} [{area}]"
    if option.type in {OptionType.ATTACK, OptionType.ABILITY, OptionType.END, OptionType.RETREAT, OptionType.EVOLVE}:
        return option_name
    if card_name:
        return f"{option_name} {card_name}"
    return option_name


def _summarize_deck_knowledge(deck_knowledge) -> dict[str, Any] | None:
    if deck_knowledge is None:
        return None
    summary = {
        "has_full_deck_info": getattr(deck_knowledge, "known_deck", None) is not None,
        "has_prize_info": getattr(deck_knowledge, "known_prized", None) is not None,
        "deck_has_dwebble": deck_knowledge.deck_has(CardIds.DWEBBLE),
        "deck_has_crustle": deck_knowledge.deck_has(CardIds.CRUSTLE),
        "deck_has_kangaskhan": deck_knowledge.deck_has(CardIds.MEGA_KANGASKHAN_EX),
        "deck_has_growing_grass": deck_knowledge.deck_has(CardIds.GROW_GRASS_ENERGY),
        "crustle_prized": deck_knowledge.is_prized(CardIds.CRUSTLE),
        "dwebble_prized": deck_knowledge.is_prized(CardIds.DWEBBLE),
    }
    return summary


def is_emergency_setup_action(obs, option, deck_state) -> bool:
    if not getattr(deck_state, "must_bench_basic", False):
        return False
    card = _card_for_option(obs, option)
    if option.type == OptionType.PLAY and card is not None:
        if getattr(card, "id", None) in {
            CardIds.DWEBBLE, CardIds.MEGA_KANGASKHAN_EX, CardIds.BUDDY_BUDDY_POFFIN, CardIds.HILDA, CardIds.ULTRA_BALL,
        }:
            return True
    if option.type == OptionType.CARD and card is not None:
        if getattr(card, "id", None) in {CardIds.DWEBBLE, CardIds.MEGA_KANGASKHAN_EX}:
            return True
    return False


def filter_scored_actions_for_emergency_setup(obs, scored_actions: list[ScoredAction], deck_state) -> list[ScoredAction]:
    if not getattr(deck_state, "must_bench_basic", False):
        return scored_actions
    emergency = [
        item for item in scored_actions
        if is_emergency_setup_action(obs, obs.select.option[item.index], deck_state)
    ]
    return emergency or scored_actions


def score_actions(obs, model_export_path, use_policy: bool = True, deck_knowledge=None) -> list[ScoredAction]:
    observation_features = build_observation_features(obs)
    policy = load_exported_policy(model_export_path) if use_policy else None
    use_policy_head = policy is not None and abs(policy.beta) > 1e-8
    priors = [score_option(obs, option, deck_knowledge=deck_knowledge) for option in obs.select.option]
    normalized_rule_logits = normalize_rule_logits([float(prior["total_logit"]) for prior in priors])
    scored: list[ScoredAction] = []
    for index, option in enumerate(obs.select.option):
        prior = priors[index]
        rule_logit = normalized_rule_logits[index]
        action_features = encode_action(obs, option, prior=prior)
        policy_logit = 0.0
        total = rule_logit
        if use_policy_head:
            policy_logit = float(policy.score(observation_features, action_features, rule_logit))
            total += policy.beta * policy_logit
        scored.append(
            ScoredAction(
                index=index,
                total_logit=total,
                rule_logit=rule_logit,
                policy_logit=policy_logit,
                observation_features=observation_features,
                action_features=action_features,
                prior=prior,
            )
        )
    scored.sort(key=lambda item: item.total_logit, reverse=True)
    deck_state = analyze_deck_state(obs, deck_knowledge=deck_knowledge)
    scored = filter_scored_actions_for_emergency_setup(obs, scored, deck_state)
    if os.getenv("RULE_DEBUG") == "1":
        debug_path = Path(os.getenv("RULE_DEBUG_PATH", Path(__file__).resolve().parent / "rule_debug.jsonl"))
        debug_path.parent.mkdir(parents=True, exist_ok=True)
        state = obs.current
        my_state = state.players[state.yourIndex]
        active = my_state.active[0] if my_state.active else None
        bench = [get_card_name(card) for card in my_state.bench if card is not None]
        primary_plan = next((
            tag for tag in (priors[0].get("reason_tags", []) if priors else [])
            if tag in {
                "close_game",
                "prevent_loss",
                "survival_setup",
                "setup_crustle_wall_now",
                "protect_bench_vs_dragapult",
                "wall_and_tax",
                "tank_and_heal",
                "setup_crustle",
                "setup_kangaskhan",
                "disruption_loop",
                "stabilize",
            }
        ), None)
        payload = {
            "logged_at": datetime.now(UTC).isoformat(),
            "turn": getattr(state, "turn", None),
            "step": getattr(state, "step", None),
            "context": _context_name(obs),
            "primary_plan": primary_plan,
            "state_tags": priors[0].get("reason_tags", []) if priors else [],
            "state_flags": {
                "must_bench_basic": getattr(deck_state, "must_bench_basic", False),
                "field_count": getattr(deck_state, "field_count", None),
                "wall_online": getattr(deck_state, "wall_online", False),
                "active_under_ko_threat": getattr(deck_state, "active_under_ko_threat", False),
                "bench_risk": getattr(deck_state, "bench_risk", False),
                "direct_win_available": getattr(deck_state, "direct_win_available", False),
                "close_pressure": getattr(deck_state, "close_pressure", False),
            },
            "deck_knowledge": _summarize_deck_knowledge(deck_knowledge),
            "active": get_card_name(active) if active is not None else None,
            "bench": bench,
            "top_actions": [
                {
                    "rank": rank + 1,
                    "index": item.index,
                    "action": _describe_option(obs, obs.select.option[item.index]),
                    "score": item.total_logit,
                    "rule_logit": item.rule_logit,
                    "policy_logit": item.policy_logit,
                    "tags": item.prior.get("reason_tags", []),
                    "breakdown": item.prior.get("breakdown", {}),
                }
                for rank, item in enumerate(scored[:5])
            ],
            "selected": {
                "index": scored[0].index,
                "score": scored[0].total_logit,
                "tags": scored[0].prior.get("reason_tags", []),
            } if scored else None,
            "selected_action": _describe_option(obs, obs.select.option[scored[0].index]) if scored else None,
        }
        with debug_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return scored


def choose_ranked_actions(scored_actions: list[ScoredAction], max_count: int) -> list[int]:
    return [item.index for item in scored_actions[: max(1, max_count)]]


def sample_action_index(
    scored_actions: list[ScoredAction],
    top_k: int = 5,
    temperature: float = 1.0,
) -> int:
    if not scored_actions:
        return 0
    limited = scored_actions[: max(1, min(top_k, len(scored_actions)))]
    if temperature <= 0:
        return limited[0].index
    logits = [item.total_logit / temperature for item in limited]
    max_logit = max(logits)
    weights = [math.exp(logit - max_logit) for logit in logits]
    return random.choices([item.index for item in limited], weights=weights, k=1)[0]

def estimate_state_value_from_export(obs, model_export_path) -> float:
    observation_features = build_observation_features(obs)
    if model_export_path is None:
        from value import estimate_state_value

        return estimate_state_value(observation_features)
    policy = load_exported_policy(model_export_path)
    if policy is None:
        from value import estimate_state_value

        return estimate_state_value(observation_features)
    return float(policy.value(observation_features))


def distribution_over_actions(
    scored_actions: list[ScoredAction],
    top_k: int | None = None,
    temperature: float = 1.0,
) -> tuple[list[int], list[float]]:
    if not scored_actions:
        return [], []
    limited = scored_actions if top_k is None else scored_actions[: max(1, min(top_k, len(scored_actions)))]
    logits = [item.total_logit / max(1e-6, temperature) for item in limited]
    return [item.index for item in limited], _softmax(logits)
