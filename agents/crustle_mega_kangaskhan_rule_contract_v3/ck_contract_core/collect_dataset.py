from __future__ import annotations

import argparse
import json
import math
import random
import sys
from pathlib import Path


AGENT_DIR = Path(__file__).resolve().parent
ROOT = AGENT_DIR.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))

from battle_env.agents import load_agent_module, resolve_agent
from cg.api import to_observation_class
from cg.game import battle_finish, battle_select, battle_start
from .inference import (
    choose_ranked_actions,
    distribution_over_actions,
    estimate_state_value_from_export,
    sample_action_index,
    score_actions,
)
from main import MODEL_EXPORT_PATH, my_deck
from .deck_state import analyze_deck_state


def parse_args():
    parser = argparse.ArgumentParser(description="Collect distillation or PPO rollout data.")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--games", type=int, default=40)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--temperature", type=float, default=1.0)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--gamma", type=float, default=0.99)
    parser.add_argument("--gae-lambda", type=float, default=0.95)
    parser.add_argument(
        "--mode",
        choices=["distill", "ppo"],
        default="ppo",
    )
    parser.add_argument(
        "--opponents",
        nargs="+",
        default=["mega_lucario_beginner", "dragapult_rule_based"],
    )
    return parser.parse_args()


def _load_opponents(names: list[str]):
    return [(name, load_agent_module(resolve_agent(name))) for name in names]


def _compute_shaped_reward(previous_observation, next_observation, player_index: int) -> float:
    state = next_observation.current
    if state.result == 2:
        return 0.0
    if state.result == player_index:
        return 1.0
    if state.result in (0, 1) and state.result != -1 and state.result != player_index:
        return -1.0
    prev_state = previous_observation.current
    prev_my_state = prev_state.players[player_index]
    prev_op_state = prev_state.players[1 - player_index]
    my_state = state.players[player_index]
    op_state = state.players[1 - player_index]
    reward = 0.0
    reward += 0.08 * max(0, len(prev_op_state.prize) - len(op_state.prize))
    reward -= 0.08 * max(0, len(prev_my_state.prize) - len(my_state.prize))

    try:
        prev_deck_state = analyze_deck_state(previous_observation)
        next_deck_state = analyze_deck_state(next_observation)
    except Exception:
        return max(-0.10, min(0.10, reward))
    if not prev_deck_state.wall_online and next_deck_state.wall_online:
        reward += 0.03
    if not prev_deck_state.heal_prevents_ko and next_deck_state.heal_prevents_ko:
        reward += 0.04
    if not prev_deck_state.gust_for_win and next_deck_state.gust_for_win:
        reward += 0.03
    elif not prev_deck_state.gust_for_prize and next_deck_state.gust_for_prize:
        reward += 0.02
    if prev_deck_state.wall_online and not next_deck_state.wall_online and prev_deck_state.opponent_active_is_ex:
        reward -= 0.03
    return max(-0.10, min(0.10, reward))


def _finalize_advantages(trajectory: list[dict], gamma: float, gae_lambda: float):
    next_advantage = 0.0
    next_return = 0.0
    next_value = 0.0
    for step in reversed(trajectory):
        reward = float(step["reward"])
        done = bool(step["done"])
        value = float(step["value"])
        mask = 0.0 if done else 1.0
        delta = reward + gamma * next_value * mask - value
        advantage = delta + gamma * gae_lambda * next_advantage * mask
        ret = advantage + value
        step["advantage"] = advantage
        step["return"] = ret
        next_advantage = advantage
        next_return = ret
        next_value = value


def _play_one(
    opponent_name,
    opponent_module,
    temperature: float,
    top_k: int,
    gamma: float,
    gae_lambda: float,
    mode: str,
):
    your_index = random.randint(0, 1)
    decks = [list(my_deck), list(opponent_module.my_deck)]
    if your_index == 1:
        decks = [decks[1], decks[0]]
    obs, start_data = battle_start(decks[0], decks[1])
    if start_data.errorPlayer >= 0:
        raise RuntimeError(f"battle_start failed against {opponent_name}: errorType={start_data.errorType}")

    trajectory: list[dict] = []
    step_index = 0
    while True:
        observation = to_observation_class(obs)
        if observation.current.result >= 0:
            break
        current_index = observation.current.yourIndex
        if current_index == your_index:
            step_index += 1
            use_policy = mode == "ppo"
            scored = score_actions(observation, MODEL_EXPORT_PATH, use_policy=use_policy)
            obs_features = scored[0].observation_features if scored else []
            value = estimate_state_value_from_export(observation, MODEL_EXPORT_PATH if use_policy else None)
            action_indices, probs = distribution_over_actions(
                scored,
                top_k=top_k if mode == "ppo" else None,
                temperature=temperature,
            )
            if mode == "distill":
                chosen_rank = 0
                chosen_action_index = action_indices[0]
                old_logprob = 0.0
                selected = choose_ranked_actions(scored, observation.select.maxCount)
            else:
                chosen_action_index = sample_action_index(scored, top_k=top_k, temperature=temperature)
                chosen_rank = action_indices.index(chosen_action_index)
                old_logprob = 0.0 if not probs else math.log(max(1e-8, probs[chosen_rank]))
                selected = [chosen_action_index]
                for index in choose_ranked_actions(scored, observation.select.maxCount):
                    if index not in selected and len(selected) < max(1, observation.select.maxCount):
                        selected.append(index)

            next_obs = battle_select(selected)
            next_observation = to_observation_class(next_obs)
            reward = _compute_shaped_reward(observation, next_observation, your_index)
            done = next_observation.current.result != -1
            trajectory.append(
                {
                    "observation_features": obs_features,
                    "action_features": [item.action_features for item in scored],
                    "rule_logits": [item.rule_logit for item in scored],
                    "policy_logits": [item.policy_logit for item in scored],
                    "final_logits": [item.total_logit for item in scored],
                    "selected_rank": chosen_rank,
                    "selected_action_index": chosen_action_index,
                    "logprob": old_logprob,
                    "value": value,
                    "reward": reward,
                    "done": done,
                    "opponent_name": opponent_name,
                    "is_first_player": observation.current.firstPlayer == your_index,
                    "turn_index": observation.current.turn,
                    "step_index": step_index,
                    "diagnostic_tags": scored[chosen_rank].prior["reason_tags"] if scored else [],
                }
            )
            obs = next_obs
        else:
            obs = battle_select(opponent_module.agent(obs))
    battle_finish()
    _finalize_advantages(trajectory, gamma=gamma, gae_lambda=gae_lambda)
    result = to_observation_class(obs).current.result
    return trajectory, result == your_index

def main():
    args = parse_args()
    random.seed(args.seed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    opponents = _load_opponents(list(args.opponents))
    samples: list[dict] = []
    results = {name: {"games": 0, "wins": 0} for name, _ in opponents}
    for _ in range(args.games):
        opponent_name, opponent_module = random.choice(opponents)
        trajectory, won = _play_one(
            opponent_name,
            opponent_module,
            temperature=args.temperature,
            top_k=args.top_k,
            gamma=args.gamma,
            gae_lambda=args.gae_lambda,
            mode=args.mode,
        )
        samples.extend(trajectory)
        results[opponent_name]["games"] += 1
        if won:
            results[opponent_name]["wins"] += 1

    payload = {
        "config": {
            "games": args.games,
            "seed": args.seed,
            "temperature": args.temperature,
            "top_k": args.top_k,
            "gamma": args.gamma,
            "gae_lambda": args.gae_lambda,
            "mode": args.mode,
            "opponents": list(args.opponents),
        },
        "results": results,
        "samples": samples,
    }
    args.output.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
