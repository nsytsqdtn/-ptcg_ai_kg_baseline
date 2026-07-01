from __future__ import annotations

import argparse
from collections import Counter
import json
import math
import random
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
except Exception:  # pragma: no cover
    torch = None
    nn = None
    F = None


AGENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = AGENT_DIR.parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))

import main as rl_agent
from battle_env.agents import load_agent_module, resolve_agent
from battle_env.recording import normalize_for_json
from cg.api import search_begin, search_end, search_release, search_step, to_observation_class
from cg.game import battle_finish, battle_select, battle_start, visualize_data


DEFAULT_OPPONENTS = [
    "alakazam_rule_based",
    "alakazam_rule_rl_numeric_v4",
    "archaludon_rule_based",
    "crustle_mega_kangaskhan_rule_contract_v1",
    "day2_beater_rule_based",
    "dragapult_rule_based",
    "lucario_anti_crustle_lab",
    "lucario_baseline_1084_5",
    "mega_lucario_beginner",
    "mega_lucario_ex_v63",
    "multiply_agent_best_940",
]
KEY_BRANCH_CONTEXTS = {"TO_HAND", "DISCARD", "DISCARD_CARD_OR_ATTACHED_CARD", "SWITCH", "TO_ACTIVE", "HEAL", "MAIN"}
RESOURCE_CONTEXTS = {"TO_HAND", "DISCARD", "DISCARD_CARD_OR_ATTACHED_CARD"}
SAFE_TRAIN_CONTEXTS = {"HEAL", "SWITCH", "TO_ACTIVE", "EVOLVE", "EVOLVES_TO", "EVOLVES_FROM", "ATTACH_TO", "ATTACH_FROM"}
RESOURCE_MAIN_CARD_IDS = {rl_agent.EXPLORER, rl_agent.LILLIE, rl_agent.POKEGEAR}


if torch is not None:
    class ResidualPolicyValue(nn.Module):
        def __init__(self, feature_dim: int = rl_agent.FEATURE_DIM, state_dim: int = 96):
            super().__init__()
            self.fc1 = nn.Linear(feature_dim, 128)
            self.fc2 = nn.Linear(128, 64)
            self.delta = nn.Linear(64, 1)
            self.value = nn.Sequential(
                nn.Linear(state_dim, 64),
                nn.ReLU(),
                nn.Linear(64, 1),
            )
            nn.init.zeros_(self.delta.weight)
            nn.init.zeros_(self.delta.bias)

        def forward_delta(self, features: torch.Tensor) -> torch.Tensor:
            h = F.relu(self.fc1(features))
            h = F.relu(self.fc2(h))
            return torch.tanh(self.delta(h)).squeeze(-1)

        def forward_value(self, state_features: torch.Tensor) -> torch.Tensor:
            return self.value(state_features).squeeze(-1)
else:
    ResidualPolicyValue = None


class NumpyResidualPolicyValue:
    def __init__(self, feature_dim: int = rl_agent.FEATURE_DIM, seed: int = 0):
        rng = np.random.default_rng(seed)
        self.w1 = rng.normal(0.0, 0.02, size=(128, feature_dim)).astype(np.float32)
        self.b1 = np.zeros((128,), dtype=np.float32)
        self.w2 = rng.normal(0.0, 0.02, size=(64, 128)).astype(np.float32)
        self.b2 = np.zeros((64,), dtype=np.float32)
        self.w_delta = np.zeros((1, 64), dtype=np.float32)
        self.b_delta = np.zeros((1,), dtype=np.float32)
        self.value_w1 = np.zeros((64, 96), dtype=np.float32)
        self.value_b1 = np.zeros((64,), dtype=np.float32)
        self.value_w2 = np.zeros((1, 64), dtype=np.float32)
        self.value_b2 = np.zeros((1,), dtype=np.float32)

    def hidden(self, features: np.ndarray) -> np.ndarray:
        h1 = np.maximum(0.0, features @ self.w1.T + self.b1)
        return np.maximum(0.0, h1 @ self.w2.T + self.b2)

    def delta(self, features: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        h2 = self.hidden(features)
        raw = h2 @ self.w_delta.T + self.b_delta
        return np.tanh(raw[:, 0]), h2


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def append_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def load_opponents(names: list[str]):
    return [(name, load_agent_module(resolve_agent(name))) for name in names]


def build_opponent_schedule(opponents: list[str], games: int, seed: int) -> list[str]:
    rng = random.Random(seed)
    schedule = [name for name in opponents for _ in range(games)]
    rng.shuffle(schedule)
    return schedule


def normalize_context_name(value) -> str:
    if hasattr(value, "name"):
        return value.name
    try:
        if isinstance(value, str) and value.isdigit():
            value = int(value)
        return rl_agent.SelectContext(value).name
    except Exception:
        return str(value)


def _decision_row_card_ids(decision_row: dict[str, Any] | None) -> set[int]:
    ids: set[int] = set()
    for opt in (decision_row or {}).get("options", []):
        card_id = opt.get("card_id")
        if card_id is None:
            continue
        ids.add(int(card_id))
    return ids


def is_resource_decision_row(decision_row: dict[str, Any] | None) -> bool:
    context = normalize_context_name((decision_row or {}).get("context"))
    if context in RESOURCE_CONTEXTS:
        return True
    if context == "MAIN" and _decision_row_card_ids(decision_row) & RESOURCE_MAIN_CARD_IDS:
        return True
    return False


def training_row_weight(row: dict[str, Any]) -> float:
    context = normalize_context_name(row.get("context"))
    if context in SAFE_TRAIN_CONTEXTS:
        return 1.0
    if context == "MAIN":
        return 0.0
    return 0.0


def branch_rollout_steps_for_row(row: dict[str, Any], default_steps: int) -> int:
    if is_resource_decision_row(row):
        return max(int(default_steps), 80)
    return max(int(default_steps), 40)


def shaped_reward(prev_obs, next_obs, player_index: int, decision_row: dict[str, Any] | None = None) -> float:
    prev = prev_obs.current
    nxt = next_obs.current
    resource_row = is_resource_decision_row(decision_row)
    me = nxt.players[player_index]
    deck_count = int(getattr(me, "deckCount", 99))
    deck_penalty = 0.0
    if deck_count <= 12:
        deck_penalty -= 0.01
    if deck_count <= 8:
        deck_penalty -= 0.03
    if deck_count <= 5:
        deck_penalty -= 0.08
    if deck_count <= 3:
        deck_penalty -= 0.15
    if resource_row:
        deck_penalty *= 1.5
    if nxt.result == player_index:
        return 1.0 + deck_penalty
    if nxt.result in (0, 1) and nxt.result != player_index:
        loss_penalty = -1.0 + deck_penalty
        if deck_count <= 0:
            loss_penalty -= 0.50
        return loss_penalty
    if nxt.result == 2:
        return deck_penalty
    prev_me, prev_opp = prev.players[player_index], prev.players[1 - player_index]
    opp = nxt.players[1 - player_index]
    reward = 0.0
    reward += 0.20 * max(0, len(prev_opp.prize or []) - len(opp.prize or []))
    reward -= 0.25 * max(0, len(prev_me.prize or []) - len(me.prize or []))
    reward += deck_penalty
    return max(-2.0, min(1.25, reward))


def finalize_returns(decisions: list[dict[str, Any]], gamma: float, gae_lambda: float) -> None:
    next_advantage = 0.0
    next_value = 0.0
    for row in reversed(decisions):
        reward = float(row.get("reward_after", 0.0))
        done = bool(row.get("terminal", False))
        value = float(row.get("value", 0.0))
        mask = 0.0 if done else 1.0
        delta = reward + gamma * next_value * mask - value
        advantage = delta + gamma * gae_lambda * next_advantage * mask
        row["advantage"] = advantage
        row["return"] = advantage + value
        next_advantage = advantage
        next_value = value


def mark_branch_candidates(row: dict[str, Any]) -> None:
    context = normalize_context_name(row.get("context"))
    row["context"] = context
    if context not in KEY_BRANCH_CONTEXTS:
        row["branch_candidate"] = False
        return
    options = [opt for opt in row.get("options", []) if float(opt.get("rule_score", 0.0)) > -9000]
    if len(options) < 2:
        row["branch_candidate"] = False
        return
    options.sort(key=lambda item: float(item.get("final_score", item.get("rule_score", 0.0))), reverse=True)
    row["branch_candidate"] = True
    row["branch_options"] = [int(opt["option_index"]) for opt in options[:5]]


def _card_ids(cards: list[dict[str, Any]] | None) -> list[int]:
    ids: list[int] = []
    for card in cards or []:
        card_id = card.get("id")
        if card_id is not None:
            ids.append(int(card_id))
    return ids


def _backfill_hidden_lists(
    player_view: dict[str, Any],
    *,
    deck_count: int,
    prize_count: int,
    full_deck: list[int] | None,
) -> tuple[list[int], list[int]]:
    deck_ids = _card_ids(player_view.get("deck", []))
    prize_ids = _card_ids(player_view.get("prize", []))
    if full_deck is None:
        return deck_ids, prize_ids
    pool = Counter(int(card_id) for card_id in full_deck)
    for zone_name in ("hand", "active", "bench", "discard"):
        for card_id in _card_ids(player_view.get(zone_name, [])):
            if pool[card_id] > 0:
                pool[card_id] -= 1
    for card_id in deck_ids + prize_ids:
        if pool[card_id] > 0:
            pool[card_id] -= 1
    remainder: list[int] = []
    remainder_pool = pool.copy()
    for card_id in full_deck:
        card_id = int(card_id)
        if remainder_pool[card_id] > 0:
            remainder.append(card_id)
            remainder_pool[card_id] -= 1
    missing_deck = max(0, deck_count - len(deck_ids))
    deck_fill = remainder[:missing_deck]
    remainder = remainder[missing_deck:]
    missing_prize = max(0, prize_count - len(prize_ids))
    prize_fill = remainder[:missing_prize]
    deck_result = deck_ids + deck_fill
    prize_result = prize_ids + prize_fill
    if len(deck_result) < deck_count:
        deck_result.extend(int(card_id) for card_id in full_deck[: deck_count - len(deck_result)])
    if len(prize_result) < prize_count:
        prize_result.extend(int(card_id) for card_id in full_deck[: prize_count - len(prize_result)])
    return deck_result[:deck_count], prize_result[:prize_count]


def hidden_from_visualize(
    obs,
    visualize_frames: list[dict[str, Any]],
    *,
    your_full_deck: list[int] | None = None,
    opponent_full_deck: list[int] | None = None,
) -> dict[str, list[int]]:
    if not visualize_frames:
        raise ValueError("visualize_data returned no frames")
    current = visualize_frames[-1]["current"]
    yi = obs.current.yourIndex
    your = current["players"][yi]
    opp = current["players"][1 - yi]
    your_state = obs.current.players[yi]
    opp_state = obs.current.players[1 - yi]
    your_deck, your_prize = _backfill_hidden_lists(
        your,
        deck_count=getattr(your_state, "deckCount", len(your.get("deck", []))),
        prize_count=len(getattr(your_state, "prize", []) or []),
        full_deck=your_full_deck,
    )
    opp_deck, opp_prize = _backfill_hidden_lists(
        opp,
        deck_count=getattr(opp_state, "deckCount", len(opp.get("deck", []))),
        prize_count=len(getattr(opp_state, "prize", []) or []),
        full_deck=opponent_full_deck,
    )
    obs_opp_active = obs.current.players[1 - yi].active
    if obs_opp_active and obs_opp_active[0] is None:
        opponent_active = _card_ids(opp.get("active", []))
    else:
        opponent_active = []
    return {
        "your_deck": your_deck,
        "your_prize": your_prize,
        "opponent_deck": opp_deck,
        "opponent_prize": opp_prize,
        "opponent_hand": _card_ids(opp.get("hand", [])),
        "opponent_active": opponent_active,
    }


def build_branch_option_lists(row: dict[str, Any], max_branch_options: int) -> list[list[int]]:
    branch_options = [int(idx) for idx in row.get("branch_options", [])[:max_branch_options]]
    min_count = int(row.get("min_count", 1) or 1)
    max_count = int(row.get("max_count", 1) or 1)
    base_selected = [int(idx) for idx in row.get("selected", [])[:max_count]]
    if not branch_options:
        return []
    if max_count <= 1:
        return [[idx] for idx in branch_options]
    if len(base_selected) < min_count:
        return []
    combos: list[list[int]] = []
    seen: set[tuple[int, ...]] = set()
    for idx in branch_options:
        if idx in base_selected:
            combo = list(base_selected)
        else:
            anchor = list(base_selected[: max(0, max_count - 1)])
            combo = anchor + [idx]
        combo = combo[:max_count]
        if len(combo) < min_count:
            continue
        key = tuple(sorted(combo))
        if key not in seen:
            seen.add(key)
            combos.append(combo)
    return combos


def make_branch_root(obs_dict, *, your_full_deck: list[int] | None, opponent_full_deck: list[int] | None) -> tuple[Any, dict[str, list[int]]]:
    obs = to_observation_class(obs_dict)
    visualize_frames = json.loads(visualize_data())
    hidden = hidden_from_visualize(
        obs,
        visualize_frames,
        your_full_deck=your_full_deck,
        opponent_full_deck=opponent_full_deck,
    )
    root = search_begin(
        obs,
        your_deck=hidden["your_deck"],
        your_prize=hidden["your_prize"],
        opponent_deck=hidden["opponent_deck"],
        opponent_prize=hidden["opponent_prize"],
        opponent_hand=hidden["opponent_hand"],
        opponent_active=hidden["opponent_active"],
        manual_coin=False,
    )
    return root, hidden


def rollout_search_state(search_state, agent_side: int, policy_agent, opponent_agent, max_steps: int) -> dict[str, Any]:
    state = search_state
    steps = 0
    total_reward = 0.0
    while steps < max_steps and state.observation.current.result == -1:
        obs = state.observation
        player_index = obs.current.yourIndex
        selected = policy_agent(obs) if player_index == agent_side else opponent_agent(obs)
        next_state = search_step(state.searchId, selected)
        total_reward += shaped_reward(obs, next_state.observation, agent_side)
        state = next_state
        steps += 1
    winner = state.observation.current.result
    if winner == agent_side:
        total_reward += 1.0
    elif winner in (0, 1) and winner != agent_side:
        total_reward -= 1.0
    return {
        "winner": winner,
        "steps": steps,
        "return": total_reward,
    }


def evaluate_counterfactual_branching(
    *,
    obs_dict,
    row: dict[str, Any],
    agent_side: int,
    policy_agent,
    opponent_agent,
    max_branch_options: int,
    rollout_max_steps: int,
    your_full_deck: list[int] | None = None,
    opponent_full_deck: list[int] | None = None,
) -> dict[str, Any]:
    if not row.get("branch_candidate"):
        return {"counterfactual_branching": False}
    branch_option_lists = build_branch_option_lists(row, max_branch_options)
    if not branch_option_lists:
        return {"counterfactual_branching": False}
    root = None
    allocated_ids: list[int] = []
    try:
        root, hidden = make_branch_root(
            obs_dict,
            your_full_deck=your_full_deck,
            opponent_full_deck=opponent_full_deck,
        )
        allocated_ids.append(root.searchId)
        branch_returns: list[float] = []
        branch_winners: list[int] = []
        branch_horizon_steps: list[int] = []
        for option_list in branch_option_lists:
            child = search_step(root.searchId, option_list)
            allocated_ids.append(child.searchId)
            rollout_steps = branch_rollout_steps_for_row(row, rollout_max_steps)
            rollout = rollout_search_state(
                child,
                agent_side=agent_side,
                policy_agent=policy_agent,
                opponent_agent=opponent_agent,
                max_steps=rollout_steps,
            )
            branch_returns.append(float(rollout["return"]))
            branch_winners.append(int(rollout["winner"]))
            branch_horizon_steps.append(int(rollout["steps"]))
        return {
            "counterfactual_branching": True,
            "branch_root_context": normalize_context_name(row.get("context")),
            "branch_option_lists": branch_option_lists,
            "branch_returns": branch_returns,
            "branch_winners": branch_winners,
            "branch_horizon_steps": branch_horizon_steps,
            "hidden_sizes": {key: len(value) for key, value in hidden.items()},
        }
    finally:
        for search_id in reversed(allocated_ids):
            try:
                search_release(search_id)
            except Exception:
                pass
        try:
            search_end()
        except Exception:
            pass


def module_policy(module):
    if hasattr(module, "choose_options"):
        return lambda obs: list(module.choose_options(obs))
    return lambda obs: list(module.agent(normalize_for_json(obs)))


def play_training_game(
    agent_side: int,
    opponent_name: str,
    opponent_module,
    gamma: float,
    gae_lambda: float,
    branch_top_k: int,
    branch_rollout_steps: int,
) -> tuple[list[dict[str, Any]], int]:
    decks = [list(rl_agent.my_deck), list(opponent_module.my_deck)]
    if agent_side == 1:
        decks = [decks[1], decks[0]]
    obs_dict, start_data = battle_start(decks[0], decks[1])
    if not start_data.battlePtr:
        raise RuntimeError(f"battle_start failed against {opponent_name}: errorType={start_data.errorType}")

    decisions: list[dict[str, Any]] = []
    try:
        while True:
            obs = to_observation_class(obs_dict)
            if obs.current.result != -1:
                winner = obs.current.result
                break
            player_index = obs.current.yourIndex
            if player_index == agent_side:
                selected = rl_agent.choose_options_train(obs)
                new_rows = rl_agent.consume_training_decisions()
                next_obs_dict = battle_select(selected)
                next_obs = to_observation_class(next_obs_dict)
                terminal = next_obs.current.result != -1
                for row in new_rows:
                    row["game_player_index"] = agent_side
                    row["opponent"] = opponent_name
                    row["train_weight"] = training_row_weight(row)
                    reward = shaped_reward(obs, next_obs, agent_side, decision_row=row)
                    row["reward_after"] = reward
                    row["terminal"] = terminal
                    row["winner"] = next_obs.current.result if terminal else None
                    row["value"] = 0.0
                    mark_branch_candidates(row)
                    if row.get("branch_candidate"):
                        try:
                            row.update(
                                evaluate_counterfactual_branching(
                                    obs_dict=obs_dict,
                                    row=row,
                                    agent_side=agent_side,
                                    policy_agent=rl_agent.choose_options,
                                    opponent_agent=module_policy(opponent_module),
                                    max_branch_options=branch_top_k,
                                    rollout_max_steps=branch_rollout_steps,
                                    your_full_deck=list(rl_agent.my_deck),
                                    opponent_full_deck=list(opponent_module.my_deck),
                                )
                            )
                        except Exception as exc:
                            row["counterfactual_branching"] = False
                            row["branch_error"] = f"{type(exc).__name__}: {exc}"
                decisions.extend(new_rows)
                obs_dict = next_obs_dict
            else:
                obs_dict = battle_select(opponent_module.agent(obs_dict))
    finally:
        battle_finish()
    finalize_returns(decisions, gamma=gamma, gae_lambda=gae_lambda)
    return decisions, winner


def collect_dataset(args, run_dir: Path) -> list[dict[str, Any]]:
    random.seed(args.seed)
    opponents = {name: module for name, module in load_opponents(args.opponents)}
    schedule = build_opponent_schedule(args.opponents, args.games_per_opponent, args.seed)
    all_rows: list[dict[str, Any]] = []
    results = {name: {"games": 0, "wins": 0, "losses": 0, "draws": 0} for name in args.opponents}
    total_games = len(schedule)
    for game_id, opponent_name in enumerate(schedule):
        opponent_module = opponents[opponent_name]
        side = random.randint(0, 1)
        rows, winner = play_training_game(
            side,
            opponent_name,
            opponent_module,
            args.gamma,
            args.gae_lambda,
            args.branch_top_k,
            args.branch_rollout_steps,
        )
        for step_id, row in enumerate(rows):
            row["game_id"] = game_id
            row["step_id"] = step_id
        all_rows.extend(rows)
        results[opponent_name]["games"] += 1
        if winner == 2:
            results[opponent_name]["draws"] += 1
        elif winner == side:
            results[opponent_name]["wins"] += 1
        else:
            results[opponent_name]["losses"] += 1
        if (game_id + 1) % max(1, args.progress_every) == 0:
            print(f"collected {game_id + 1}/{total_games} games, decisions={len(all_rows)}", flush=True)
    append_jsonl(run_dir / "training_logs" / "decisions.jsonl", all_rows)
    write_json(
        run_dir / "training_logs" / "collection_summary.json",
        {"results": results, "decisions": len(all_rows), "games_per_opponent": args.games_per_opponent, "total_games": total_games},
    )
    return all_rows


def _plackett_luce_loss(logits: torch.Tensor, selected_positions: list[int], advantage: torch.Tensor) -> torch.Tensor:
    if not selected_positions:
        return torch.tensor(0.0, device=logits.device)
    remaining = torch.ones_like(logits, dtype=torch.bool)
    loss = torch.tensor(0.0, device=logits.device)
    for pos in selected_positions:
        if pos < 0 or pos >= logits.numel():
            continue
        masked = logits.masked_fill(~remaining, -1e9)
        loss = loss - advantage.detach() * F.log_softmax(masked, dim=0)[pos]
        remaining[pos] = False
    return loss


def _softmax_np(logits: np.ndarray) -> np.ndarray:
    shifted = logits - np.max(logits)
    exp = np.exp(np.clip(shifted, -50.0, 50.0))
    return exp / max(float(exp.sum()), 1e-8)


def branch_target_probs(branch_returns: list[float], temperature: float) -> list[float]:
    if not branch_returns:
        return []
    scale = max(float(temperature), 1e-6)
    values = np.array(branch_returns, dtype=np.float32) / scale
    probs = _softmax_np(values)
    return [float(v) for v in probs]


def branch_combo_logits(logits, branch_option_lists: list[list[int]], option_rows: list[dict[str, Any]]) -> list[float]:
    index_to_pos = {int(opt["option_index"]): pos for pos, opt in enumerate(option_rows)}
    combo_scores: list[float] = []
    for option_list in branch_option_lists:
        score = 0.0
        for option_index in option_list:
            pos = index_to_pos.get(int(option_index))
            if pos is not None:
                score += float(logits[pos])
        combo_scores.append(score)
    return combo_scores


def branch_loss_weight(row: dict[str, Any]) -> float:
    if float(row.get("train_weight", 1.0)) <= 0.0:
        return 0.0
    returns = [float(v) for v in row.get("branch_returns", [])]
    if not row.get("counterfactual_branching") or len(returns) < 2:
        return 0.0
    spread = max(returns) - min(returns)
    return max(0.0, min(1.0, spread))


def branch_policy_loss_np(logits: np.ndarray, row: dict[str, Any], temperature: float) -> tuple[float, np.ndarray | None]:
    if not row.get("counterfactual_branching"):
        return 0.0, None
    combos = row.get("branch_option_lists") or []
    returns = row.get("branch_returns") or []
    if len(combos) < 2 or len(combos) != len(returns):
        return 0.0, None
    target = np.array(branch_target_probs(returns, temperature), dtype=np.float32)
    combo_logits = np.array(branch_combo_logits(logits, combos, row["options"]), dtype=np.float32)
    combo_probs = _softmax_np(combo_logits)
    combo_grad = combo_probs - target
    option_grad = np.zeros_like(logits)
    index_to_pos = {int(opt["option_index"]): pos for pos, opt in enumerate(row["options"])}
    for combo_idx, option_list in enumerate(combos):
        for option_index in option_list:
            pos = index_to_pos.get(int(option_index))
            if pos is not None:
                option_grad[pos] += combo_grad[combo_idx]
    loss = float(-(target * np.log(np.clip(combo_probs, 1e-8, 1.0))).sum())
    return loss, option_grad


def branch_policy_loss_torch(logits: torch.Tensor, row: dict[str, Any], temperature: float) -> torch.Tensor:
    if not row.get("counterfactual_branching"):
        return torch.tensor(0.0, device=logits.device)
    combos = row.get("branch_option_lists") or []
    returns = row.get("branch_returns") or []
    if len(combos) < 2 or len(combos) != len(returns):
        return torch.tensor(0.0, device=logits.device)
    index_to_pos = {int(opt["option_index"]): pos for pos, opt in enumerate(row["options"])}
    combo_scores = []
    for option_list in combos:
        positions = [index_to_pos[int(option_index)] for option_index in option_list if int(option_index) in index_to_pos]
        if not positions:
            combo_scores.append(torch.tensor(0.0, device=logits.device))
        else:
            combo_scores.append(logits[positions].sum())
    combo_logits = torch.stack(combo_scores)
    target = torch.tensor(branch_target_probs(returns, temperature), dtype=torch.float32, device=logits.device)
    log_probs = F.log_softmax(combo_logits, dim=0)
    return -(target * log_probs).sum()


def train_model_numpy(rows: list[dict[str, Any]], args) -> NumpyResidualPolicyValue:
    model = NumpyResidualPolicyValue(seed=args.seed)
    usable = [row for row in rows if row.get("options")]
    if not usable:
        return model
    returns = np.array([float(row.get("return", 0.0)) for row in usable], dtype=np.float32)
    ret_mean = float(returns.mean())
    ret_std = float(max(returns.std(), 1e-6))
    for epoch in range(args.epochs):
        random.shuffle(usable)
        total_loss = 0.0
        for row in usable:
            row_weight = float(row.get("train_weight", 1.0))
            if row_weight <= 0.0:
                continue
            state_features = np.array(row["state_features"], dtype=np.float32)
            option_only = np.array([opt["option_features"] for opt in row["options"]], dtype=np.float32)
            option_features = np.concatenate(
                [np.repeat(state_features.reshape(1, -1), option_only.shape[0], axis=0), option_only],
                axis=1,
            )
            rule_scores = np.array([float(opt["rule_score"]) for opt in row["options"]], dtype=np.float32)
            selected_positions = [pos for pos, opt in enumerate(row["options"]) if opt.get("selected")]
            if not selected_positions:
                continue
            advantage = (float(row.get("return", 0.0)) - ret_mean) / ret_std
            delta, h2 = model.delta(option_features)
            logits = rule_scores / args.score_scale + delta
            probs = _softmax_np(logits)
            target = np.zeros_like(probs)
            for pos in selected_positions:
                target[pos] = 1.0 / len(selected_positions)
            grad_delta = (probs - target) * advantage * row_weight
            branch_ce, branch_grad = branch_policy_loss_np(logits, row, args.branch_return_temperature)
            if branch_grad is not None:
                grad_delta += args.branch_loss_weight * branch_loss_weight(row) * branch_grad * row_weight
            grad_delta = grad_delta * (1.0 - delta * delta)
            grad_w = grad_delta.reshape(1, -1) @ h2
            grad_b = np.array([grad_delta.sum()], dtype=np.float32)
            model.w_delta -= args.lr * grad_w.astype(np.float32)
            model.b_delta -= args.lr * grad_b
            total_loss += float(-advantage * np.log(max(1e-8, probs[selected_positions[0]]))) * row_weight
            total_loss += args.branch_loss_weight * branch_loss_weight(row) * branch_ce * row_weight
        print(f"epoch={epoch + 1} mean_loss={total_loss / max(1, len(usable)):.4f} backend=numpy", flush=True)
    return model


def train_model(rows: list[dict[str, Any]], args):
    if torch is None:
        return train_model_numpy(rows, args)
    model = ResidualPolicyValue()
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)
    usable = [row for row in rows if row.get("options")]
    if not usable:
        return model
    returns = torch.tensor([float(row.get("return", 0.0)) for row in usable], dtype=torch.float32)
    ret_mean = returns.mean()
    ret_std = returns.std().clamp_min(1e-6)
    for epoch in range(args.epochs):
        random.shuffle(usable)
        total_loss = 0.0
        for row in usable:
            row_weight = float(row.get("train_weight", 1.0))
            if row_weight <= 0.0:
                continue
            state = torch.tensor(row["state_features"], dtype=torch.float32).unsqueeze(0)
            option_features = torch.tensor(
                [row["state_features"] + opt["option_features"] for opt in row["options"]],
                dtype=torch.float32,
            )
            rule_scores = torch.tensor([float(opt["rule_score"]) for opt in row["options"]], dtype=torch.float32)
            selected_indices = [int(opt["option_index"]) for opt in row["options"] if opt.get("selected")]
            index_to_pos = {int(opt["option_index"]): pos for pos, opt in enumerate(row["options"])}
            selected_positions = [index_to_pos[idx] for idx in selected_indices if idx in index_to_pos]
            ret = torch.tensor(float(row.get("return", 0.0)), dtype=torch.float32)
            advantage = (ret - ret_mean) / ret_std
            delta = model.forward_delta(option_features)
            logits = rule_scores / args.score_scale + delta
            policy_loss = _plackett_luce_loss(logits, selected_positions, advantage)
            branch_loss = branch_policy_loss_torch(logits, row, args.branch_return_temperature)
            value = model.forward_value(state)[0]
            value_loss = 0.5 * (value - ret).pow(2)
            probs = F.softmax(logits, dim=0)
            entropy = -(probs * torch.log(probs.clamp_min(1e-8))).sum()
            loss = (
                row_weight * policy_loss
                + row_weight * args.branch_loss_weight * branch_loss_weight(row) * branch_loss
                + row_weight * args.value_weight * value_loss
                - row_weight * args.entropy_weight * entropy
            )
            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
            optimizer.step()
            total_loss += float(loss.detach())
        print(f"epoch={epoch + 1} mean_loss={total_loss / max(1, len(usable)):.4f}", flush=True)
    return model


def export_weights(model, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(model, NumpyResidualPolicyValue):
        np.savez(
            output,
            w1=model.w1,
            b1=model.b1,
            w2=model.w2,
            b2=model.b2,
            w_delta=model.w_delta,
            b_delta=model.b_delta,
            value_w1=model.value_w1,
            value_b1=model.value_b1,
            value_w2=model.value_w2,
            value_b2=model.value_b2,
            feature_dim=np.array([rl_agent.FEATURE_DIM], dtype=np.int64),
        )
        return
    np.savez(
        output,
        w1=model.fc1.weight.detach().cpu().numpy(),
        b1=model.fc1.bias.detach().cpu().numpy(),
        w2=model.fc2.weight.detach().cpu().numpy(),
        b2=model.fc2.bias.detach().cpu().numpy(),
        w_delta=model.delta.weight.detach().cpu().numpy(),
        b_delta=model.delta.bias.detach().cpu().numpy(),
        value_w1=model.value[0].weight.detach().cpu().numpy(),
        value_b1=model.value[0].bias.detach().cpu().numpy(),
        value_w2=model.value[2].weight.detach().cpu().numpy(),
        value_b2=model.value[2].bias.detach().cpu().numpy(),
        feature_dim=np.array([rl_agent.FEATURE_DIM], dtype=np.int64),
    )


def parse_args():
    parser = argparse.ArgumentParser(description="Train Archaludon residual RL ranker.")
    parser.add_argument("--opponents", nargs="+", default=DEFAULT_OPPONENTS)
    parser.add_argument("--games-per-opponent", type=int, default=100)
    parser.add_argument("--seed", type=int, default=20260630)
    parser.add_argument("--gamma", type=float, default=0.995)
    parser.add_argument("--gae-lambda", type=float, default=0.95)
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--weight-decay", type=float, default=1e-4)
    parser.add_argument("--score-scale", type=float, default=10000.0)
    parser.add_argument("--value-weight", type=float, default=0.5)
    parser.add_argument("--entropy-weight", type=float, default=0.01)
    parser.add_argument("--branch-loss-weight", type=float, default=0.5)
    parser.add_argument("--branch-return-temperature", type=float, default=0.25)
    parser.add_argument("--progress-every", type=int, default=5)
    parser.add_argument("--branch-top-k", type=int, default=3)
    parser.add_argument("--branch-rollout-steps", type=int, default=40)
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--weights-out", type=Path, default=AGENT_DIR / "rl_weights.npz")
    return parser.parse_args()


def main():
    args = parse_args()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    run_dir = args.run_dir or (AGENT_DIR / "training_logs" / stamp)
    run_dir.mkdir(parents=True, exist_ok=True)
    write_json(run_dir / "config.json", vars(args) | {"run_dir": str(run_dir), "weights_out": str(args.weights_out)})
    rows = collect_dataset(args, run_dir)
    model = train_model(rows, args)
    export_weights(model, args.weights_out)
    write_json(run_dir / "summary.json", {"decisions": len(rows), "weights_out": str(args.weights_out)})
    print(f"wrote {args.weights_out}", flush=True)


if __name__ == "__main__":
    main()
