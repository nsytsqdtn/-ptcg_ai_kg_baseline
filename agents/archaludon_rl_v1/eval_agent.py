from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


AGENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = AGENT_DIR.parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from battle_env.runner import play_match


DEFAULT_AGENT_NAME = "archaludon_rl_v1"
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


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _empty_matchup() -> dict[str, Any]:
    return {
        "games": 0,
        "wins": 0,
        "losses": 0,
        "draws": 0,
        "errors": 0,
        "win_rate": 0.0,
        "termination": {},
        "fallback_total": 0,
        "average_steps": 0.0,
        "average_turns": 0.0,
        "average_prizes_taken": 0.0,
        "average_prizes_lost": 0.0,
    }


def _agent_prize_metrics(result: dict[str, Any], agent_is_left: bool) -> tuple[float, float]:
    metrics = result.get("metrics") or {}
    prizes = metrics.get("prizes") or {}
    if agent_is_left:
        return float(prizes.get("agent_a_taken", 0.0)), float(prizes.get("agent_b_taken", 0.0))
    return float(prizes.get("agent_b_taken", 0.0)), float(prizes.get("agent_a_taken", 0.0))


def run_evaluation(agent_name: str, opponents: list[str], games_per_opponent: int, swap_sides: bool, progress_every: int) -> dict[str, Any]:
    report = {
        "agent": agent_name,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "games_per_opponent": games_per_opponent,
        "swap_sides": swap_sides,
        "matchups": {},
        "overall": _empty_matchup(),
    }
    for opponent in opponents:
        matchup = _empty_matchup()
        for game_index in range(games_per_opponent):
            use_swap = swap_sides and game_index % 2 == 1
            left = opponent if use_swap else agent_name
            right = agent_name if use_swap else opponent
            result = play_match(left, right, capture_details=False)
            agent_is_left = not use_swap
            matchup["games"] += 1
            if result.get("status") != "success":
                matchup["errors"] += 1
            else:
                winner = result.get("winner")
                if winner == 2:
                    matchup["draws"] += 1
                elif (winner == 0 and agent_is_left) or (winner == 1 and not agent_is_left):
                    matchup["wins"] += 1
                elif winner in (0, 1):
                    matchup["losses"] += 1
                term = (result.get("termination") or {}).get("reason_key", "unknown")
                matchup["termination"][term] = matchup["termination"].get(term, 0) + 1
                fallback_counts = result.get("fallback_counts") or {}
                key = "agent_a" if agent_is_left else "agent_b"
                matchup["fallback_total"] += int(fallback_counts.get(key, 0) or 0)
                matchup["average_steps"] += float(result.get("steps", 0))
                matchup["average_turns"] += float(result.get("turn", 0))
                taken, lost = _agent_prize_metrics(result, agent_is_left)
                matchup["average_prizes_taken"] += taken
                matchup["average_prizes_lost"] += lost
            if progress_every and (game_index + 1) % progress_every == 0:
                print(f"{agent_name} vs {opponent}: {game_index + 1}/{games_per_opponent}", flush=True)
        denom = max(1, matchup["games"] - matchup["errors"])
        matchup["win_rate"] = matchup["wins"] / denom
        for key in ("average_steps", "average_turns", "average_prizes_taken", "average_prizes_lost"):
            matchup[key] = matchup[key] / max(1, matchup["games"])
        report["matchups"][opponent] = matchup
        for key in ("games", "wins", "losses", "draws", "errors", "fallback_total"):
            report["overall"][key] += matchup[key]
        for term, count in matchup["termination"].items():
            report["overall"]["termination"][term] = report["overall"]["termination"].get(term, 0) + count
        for key in ("average_steps", "average_turns", "average_prizes_taken", "average_prizes_lost"):
            report["overall"][key] += matchup[key] * matchup["games"]
    overall_denom = max(1, report["overall"]["games"] - report["overall"]["errors"])
    report["overall"]["win_rate"] = report["overall"]["wins"] / overall_denom
    for key in ("average_steps", "average_turns", "average_prizes_taken", "average_prizes_lost"):
        report["overall"][key] = report["overall"][key] / max(1, report["overall"]["games"])
    return report


def parse_args():
    parser = argparse.ArgumentParser(description="Evaluate Archaludon residual RL agent.")
    parser.add_argument("--agent", default=DEFAULT_AGENT_NAME)
    parser.add_argument("--opponents", nargs="+", default=DEFAULT_OPPONENTS)
    parser.add_argument("--games-per-opponent", type=int, default=100)
    parser.add_argument("--swap-sides", action="store_true")
    parser.add_argument("--progress-every", type=int, default=10)
    parser.add_argument("--output", type=Path, default=AGENT_DIR / "training_logs" / "eval_report.json")
    return parser.parse_args()


def main():
    args = parse_args()
    report = run_evaluation(args.agent, args.opponents, args.games_per_opponent, args.swap_sides, args.progress_every)
    write_json(args.output, report)
    print(json.dumps(report["overall"], ensure_ascii=False, indent=2), flush=True)
    print(f"wrote {args.output}", flush=True)


if __name__ == "__main__":
    main()
