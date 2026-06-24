from __future__ import annotations

import math
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from action_encoder import encode_action
from observation_builder import build_observation_features
from policy import load_exported_policy
from rule_prior import score_option
from runtime import CardIds, make_rule_prior_result
from action_classifier import ClassifiedAction


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


def _score_contract_bonus(action: ClassifiedAction, snapshot, obligations, plan) -> tuple[float, list[str]]:
    objective = getattr(plan, "objective", getattr(plan, "mode", ""))
    tags = action.tags
    bonus = 0.0
    reasons: list[str] = []

    if getattr(obligations, "must_add_backup", False):
        if "bench_basic" in tags:
            bonus += 900.0; reasons.append("contract_bench_basic")
        if "backup_route" in tags:
            bonus += 650.0; reasons.append("contract_backup_route")
        if "play_search" in tags:
            bonus += 400.0; reasons.append("contract_search_backup")

    if objective == "setup_crustle_wall":
        if "evolve_crustle" in tags or "wall_preserve" in tags:
            bonus += 600.0; reasons.append("contract_setup_wall")
        if "attach_growing_grass" in tags or "attach_basic_grass" in tags:
            bonus += 300.0; reasons.append("contract_wall_energy")
    elif objective == "preserve_wall":
        if "wall_preserve" in tags:
            bonus += 450.0; reasons.append("contract_preserve_wall")
        if "disruption" in tags or "heal" in tags:
            bonus += 220.0; reasons.append("contract_wall_tax")
    elif objective == "protect_bench_core":
        if "attach_mist" in tags:
            bonus += 500.0; reasons.append("contract_mist_core")
        if "backup_route" in tags or "wall_preserve" in tags:
            bonus += 300.0; reasons.append("contract_bench_core")
    elif objective == "kang_engine":
        if "draw_deck" in tags and not getattr(obligations, "must_not_draw", False):
            bonus += 180.0; reasons.append("contract_kang_resource")
        if "attach_spiky" in tags or "attach_mist" in tags:
            bonus += 160.0; reasons.append("contract_kang_energy")
    elif objective == "finish":
        if "attack" in tags or "gust" in tags:
            bonus += 500.0; reasons.append("contract_prize_route")

    if getattr(obligations, "must_not_draw", False) and "draw_deck" in tags:
        bonus -= 1000.0; reasons.append("contract_low_deck_no_draw")

    return bonus, reasons


def _prior_for_action(obs, action: ClassifiedAction, deck_knowledge=None, snapshot=None, obligations=None, plan=None) -> dict[str, Any]:
    option = obs.select.option[action.index]
    try:
        prior = score_option(obs, option, deck_knowledge=deck_knowledge)
    except TypeError:
        prior = score_option(obs, option)
    except Exception:
        prior = make_rule_prior_result(0.0, {}, [])

    total = float(prior.get("total_logit", 0.0))
    tags = list(prior.get("reason_tags", []))
    breakdown = dict(prior.get("breakdown", {}))
    bonus, reasons = _score_contract_bonus(action, snapshot, obligations, plan)
    if bonus:
        total += bonus
        breakdown["contract"] = breakdown.get("contract", 0.0) + bonus
        tags.extend(reasons)
    tags.extend(sorted(action.tags))
    prior["total_logit"] = total
    prior["breakdown"] = breakdown
    prior["reason_tags"] = tags
    return prior


def score_actions(
    obs,
    model_export_path=None,
    use_policy: bool = True,
    deck_knowledge=None,
    deck_state=None,
    snapshot=None,
    plan=None,
    obligations=None,
    allowed: list[ClassifiedAction] | None = None,
    allowed_indices: list[int] | None = None,
) -> list[ScoredAction]:
    observation_features = build_observation_features(obs)
    policy = load_exported_policy(model_export_path) if use_policy and model_export_path else None
    use_policy_head = policy is not None and abs(getattr(policy, "beta", 0.0)) > 1e-8

    if allowed is None:
        if allowed_indices is None:
            allowed_indices = list(range(len(obs.select.option)))
        allowed = [ClassifiedAction(index=i, option=obs.select.option[i]) for i in allowed_indices]

    priors = [_prior_for_action(obs, action, deck_knowledge, snapshot, obligations, plan) for action in allowed]
    normalized_rule_logits = normalize_rule_logits([float(prior["total_logit"]) for prior in priors])
    scored: list[ScoredAction] = []
    for local_idx, action in enumerate(allowed):
        prior = priors[local_idx]
        rule_logit = normalized_rule_logits[local_idx]
        option = obs.select.option[action.index]
        action_features = encode_action(obs, option, prior=prior)
        policy_logit = 0.0
        total = rule_logit
        if use_policy_head:
            policy_logit = float(policy.score(observation_features, action_features, rule_logit))
            total += policy.beta * policy_logit
        scored.append(
            ScoredAction(
                index=action.index,
                total_logit=total,
                rule_logit=rule_logit,
                policy_logit=policy_logit,
                observation_features=observation_features,
                action_features=action_features,
                prior=prior,
            )
        )
    scored.sort(key=lambda item: item.total_logit, reverse=True)
    return scored


def choose_ranked_actions(scored_actions: list[ScoredAction], max_count: int) -> list[int]:
    return [item.index for item in scored_actions[: max(1, max_count)]]


def sample_action_index(scored_actions: list[ScoredAction], top_k: int = 5, temperature: float = 1.0) -> int:
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


def distribution_over_actions(scored_actions: list[ScoredAction], top_k: int | None = None, temperature: float = 1.0) -> tuple[list[int], list[float]]:
    if not scored_actions:
        return [], []
    limited = scored_actions if top_k is None else scored_actions[: max(1, min(top_k, len(scored_actions)))]
    logits = [item.total_logit / max(1e-6, temperature) for item in limited]
    return [item.index for item in limited], _softmax(logits)
