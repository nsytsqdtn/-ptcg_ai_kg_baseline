from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Any

from action_encoder import encode_action
from observation_builder import build_observation_features
from policy import load_exported_policy
from rule_prior import score_option, score_option_for_plan
from cg.api import AreaType
from turn_plan import build_state_view, build_turn_plan


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


def normalize_rule_logits(raw_rule_scores: list[float], use_policy: bool) -> list[float]:
    if not raw_rule_scores:
        return []
    if not use_policy:
        return [float(score) for score in raw_rule_scores]
    if len(raw_rule_scores) == 1:
        return [0.0]
    mean = sum(raw_rule_scores) / float(len(raw_rule_scores))
    variance = sum((score - mean) ** 2 for score in raw_rule_scores) / float(len(raw_rule_scores))
    std = max(variance**0.5, 1e-6)
    return [max(-3.0, min(3.0, (score - mean) / std)) for score in raw_rule_scores]


def score_actions(obs, model_export_path, use_policy: bool = True, deck_knowledge=None, deck_state=None, snapshot=None, plan=None) -> list[ScoredAction]:
    observation_features = build_observation_features(
        obs,
        deck_state=deck_state,
        snapshot=snapshot,
        plan=plan,
        deck_knowledge=deck_knowledge,
    )
    policy = load_exported_policy(model_export_path) if use_policy else None
    use_policy_head = policy is not None and abs(policy.beta) > 1e-8
    if snapshot is not None and plan is not None:
        priors = [score_option_for_plan(obs, option, snapshot, plan, deck_knowledge=deck_knowledge) for option in obs.select.option]
    else:
        priors = [score_option(obs, option, deck_knowledge=deck_knowledge) for option in obs.select.option]
    normalized_rule_logits = normalize_rule_logits([float(prior["total_logit"]) for prior in priors], use_policy=use_policy_head)
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
    if deck_state is None:
        if snapshot is not None and plan is not None:
            deck_state = build_state_view(snapshot, plan, deck_knowledge=deck_knowledge)
        else:
            snapshot, plan = build_turn_plan(obs, deck_knowledge=deck_knowledge)
            deck_state = build_state_view(snapshot, plan, deck_knowledge=deck_knowledge)
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
