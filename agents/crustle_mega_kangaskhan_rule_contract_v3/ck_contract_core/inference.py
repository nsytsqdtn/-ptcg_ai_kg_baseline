from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Any

from .action_encoder import encode_action
from .observation_builder import build_observation_features
from .policy import load_exported_policy
from .runtime import CardIds
from .action_classifier import ClassifiedAction
from .search_routes import resolve_search_route, RouteStatus


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


def _add(breakdown: dict[str, float], tags: list[str], name: str, value: float, tag: str | None = None):
    breakdown[name] = breakdown.get(name, 0.0) + float(value)
    if tag:
        tags.append(tag)


def _search_value(action: ClassifiedAction, plan, obligations, deck_knowledge) -> tuple[float, str]:
    if "play_search" not in action.tags or action.card_id is None:
        return 0.0, ""
    route = resolve_search_route(action.card_id, plan, obligations, deck_knowledge)
    if route.status == RouteStatus.CONFIRMED:
        return float(route.value), f"search_confirmed_{route.reason}"
    if route.status == RouteStatus.POSSIBLE:
        return float(route.value), f"search_possible_{route.reason}"
    return -1000.0, f"search_dead_{route.reason}"


def _score_by_objective(action: ClassifiedAction, snapshot, obligations, plan, deck_knowledge) -> dict[str, Any]:
    objective = getattr(plan, "objective", getattr(plan, "mode", "stabilize"))
    tags_set = action.tags
    breakdown: dict[str, float] = {}
    tags: list[str] = [objective, *sorted(tags_set)]

    def add(name: str, value: float, tag: str | None = None):
        _add(breakdown, tags, name, value, tag)

    # Baselines: choose meaningful game actions over no-op-like options.
    if "bench_basic" in tags_set:
        add("board", 180, "bench_basic")
    if "evolve_crustle" in tags_set:
        add("wall", 260, "evolve_crustle")
    if "attach_energy" in tags_set:
        add("energy", 90, "attach_energy")
    if "heal" in tags_set:
        add("survival", 70, "heal")
    if "disruption" in tags_set:
        add("control", 90, "disruption")
    if "gust" in tags_set:
        add("tempo", 70, "gust")
    if "attack" in tags_set:
        add("attack", 55, "attack")

    route_value, route_tag = _search_value(action, plan, obligations, deck_knowledge)
    if route_tag:
        add("search_route", route_value, route_tag)

    if getattr(obligations, "must_add_backup", False):
        if "bench_basic" in tags_set:
            add("obligation", 1100, "must_add_backup_bench")
        if "backup_route" in tags_set:
            add("obligation", 850, "must_add_backup_route")
        if "play_search" in tags_set:
            add("obligation", 450, "must_add_backup_search")

    if getattr(obligations, "must_not_draw", False) and "draw_deck" in tags_set:
        add("deck", -2000, "low_deck_no_draw")

    if objective == "finish":
        if "attack" in tags_set:
            add("finish", 1600, "finish_attack")
        if "gust" in tags_set:
            add("finish", 1300, "finish_gust")
        if "play_search" in tags_set:
            add("finish", 450, "finish_search")

    elif objective == "setup_backup":
        if "bench_basic" in tags_set:
            add("setup_backup", 1200, "setup_backup_bench")
        if "backup_route" in tags_set:
            add("setup_backup", 950, "setup_backup_route")
        if "search_basic" in tags_set or "search_pokemon" in tags_set:
            add("setup_backup", 500, "setup_backup_search")

    elif objective == "prevent_loss":
        if "heal" in tags_set:
            add("prevent_loss", 900, "prevent_loss_heal")
        if "switch" in tags_set:
            add("prevent_loss", 550, "prevent_loss_switch")
        if "attach_spiky" in tags_set or "attach_mist" in tags_set:
            add("prevent_loss", 350, "prevent_loss_energy")
        if "play_search" in tags_set:
            add("prevent_loss", 260, "prevent_loss_search")

    elif objective == "setup_crustle_wall":
        if "evolve_crustle" in tags_set or "switch_to_crustle" in tags_set:
            add("setup_wall", 1150, "setup_wall_now")
        if "wall_preserve" in tags_set:
            add("setup_wall", 650, "setup_wall_preserve")
        if "attach_growing_grass" in tags_set or "attach_basic_grass" in tags_set:
            add("setup_wall", 520, "setup_wall_energy")
        if "search_pokemon" in tags_set or "search_energy" in tags_set:
            add("setup_wall", 330, "setup_wall_search")
        if "bench_basic" in tags_set:
            add("setup_wall", 240, "setup_wall_basic")

    elif objective == "protect_bench_core":
        has_prize_counter = bool(getattr(snapshot, "can_ko_active", False) or getattr(snapshot, "best_gust_ko_target", None) is not None)
        if has_prize_counter:
            if "gust" in tags_set:
                add("bench_protect", 1250, "counter_spread_gust_ko")
            if "attack" in tags_set:
                add("bench_protect", 1150, "counter_spread_attack_ko")
            if "disruption" in tags_set:
                add("bench_protect", 760, "counter_spread_disrupt")
            if "attach_mist_core" in tags_set and "attach_to_bench" in tags_set:
                add("bench_protect", 620, "mist_bench_core_after_counter")
            elif "attach_mist" in tags_set:
                add("bench_protect", 420, "mist_after_counter")
        else:
            if "attach_mist_core" in tags_set and "attach_to_bench" in tags_set:
                add("bench_protect", 1250, "mist_bench_core")
            elif "attach_mist" in tags_set:
                add("bench_protect", 760, "mist_generic")
            if "disruption" in tags_set or "gust" in tags_set:
                add("bench_protect", 650, "counter_spread")
            if "attack" in tags_set:
                add("bench_protect", 420, "attack_spread_source")
        if "wall_preserve" in tags_set or "evolve_crustle" in tags_set:
            add("bench_protect", 580, "protect_wall")
        if "play_search" in tags_set:
            add("bench_protect", 280, "protect_search")

    elif objective == "wall_control":
        can_pressure = bool(getattr(snapshot, "can_ko_active", False) or getattr(snapshot, "best_gust_ko_target", None) is not None)
        op_energy = 0
        try:
            from .runtime import energy_count as _energy_count
            op_energy = _energy_count(getattr(snapshot, "opponent_active", None))
        except Exception:
            op_energy = 0
        if can_pressure:
            if "gust" in tags_set:
                add("wall_control", 1180, "wall_control_pressure_gust")
            if "attack" in tags_set:
                add("wall_control", 1040, "wall_control_pressure_attack")
            if "disruption" in tags_set:
                add("wall_control", 760, "wall_control_disrupt_after_pressure")
        else:
            if "disruption" in tags_set:
                # Energy/resource denial is most valuable when the opponent is already close to attacking.
                if action.card_id in {CardIds.XEROSIC, CardIds.HANDHELD_FAN} and op_energy >= 2:
                    add("wall_control", 1240, "wall_control_energy_denial")
                else:
                    add("wall_control", 980, "wall_control_disrupt")
            if "gust" in tags_set:
                add("wall_control", 560, "wall_control_gust")
            if "attack" in tags_set:
                add("wall_control", 460, "wall_control_attack")
        if "heal" in tags_set:
            add("wall_control", 620, "wall_control_heal")
        if "attach_spiky" in tags_set or "attach_mist" in tags_set:
            add("wall_control", 520, "wall_control_energy")
        if "play_search" in tags_set:
            add("wall_control", 260, "wall_control_search")

    elif objective in {"pressure_prize", "take_prize"}:
        if "attack" in tags_set:
            add("prize", 1200, "prize_attack")
        if "gust" in tags_set:
            add("prize", 1050, "prize_gust")
        if "switch" in tags_set:
            add("prize", 250, "prize_switch")
        if "play_search" in tags_set:
            add("prize", 180, "prize_search")

    elif objective == "resource_lock":
        if "disruption" in tags_set:
            add("resource_lock", 1150, "lock_disruption")
        if "play_search" in tags_set:
            add("resource_lock", 450, "lock_search")
        if "gust" in tags_set:
            add("resource_lock", 360, "lock_gust")
        if "attack" in tags_set:
            add("resource_lock", 220, "lock_attack")

    elif objective == "kang_engine":
        if "draw_deck" in tags_set:
            add("kang", 680, "kang_draw")
        if "attach_spiky" in tags_set or "attach_mist" in tags_set:
            add("kang", 520, "kang_energy")
        if "search_pokemon" in tags_set or "search_energy" in tags_set:
            add("kang", 210, "kang_search")

    else:
        if "play_search" in tags_set:
            add("stabilize", 260, "stabilize_search")
        if "bench_basic" in tags_set or "wall_preserve" in tags_set:
            add("stabilize", 300, "stabilize_board")
        if "disruption" in tags_set:
            add("stabilize", 210, "stabilize_disrupt")

    total = sum(breakdown.values())
    return {"total_logit": total, "breakdown": breakdown, "reason_tags": tags}


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
    policy = load_exported_policy(model_export_path) if use_policy and model_export_path else None
    use_policy_head = policy is not None and abs(getattr(policy, "beta", 0.0)) > 1e-8
    observation_features = build_observation_features(obs) if use_policy_head else []

    if allowed is None:
        if allowed_indices is None:
            allowed_indices = list(range(len(obs.select.option)))
        allowed = [ClassifiedAction(index=i, option=obs.select.option[i]) for i in allowed_indices]

    scored: list[ScoredAction] = []
    for action in allowed:
        prior = _score_by_objective(action, snapshot, obligations, plan, deck_knowledge)
        rule_logit = float(prior["total_logit"])
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
        from .value import estimate_state_value
        return estimate_state_value(observation_features)
    policy = load_exported_policy(model_export_path)
    if policy is None:
        from .value import estimate_state_value
        return estimate_state_value(observation_features)
    return float(policy.value(observation_features))


def distribution_over_actions(scored_actions: list[ScoredAction], top_k: int | None = None, temperature: float = 1.0) -> tuple[list[int], list[float]]:
    if not scored_actions:
        return [], []
    limited = scored_actions if top_k is None else scored_actions[: max(1, min(top_k, len(scored_actions)))]
    logits = [item.total_logit / max(1e-6, temperature) for item in limited]
    return [item.index for item in limited], _softmax(logits)
