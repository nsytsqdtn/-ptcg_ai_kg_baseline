from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

AGENT_DIR = Path(__file__).resolve().parent
DEFAULT_AGENT_NAME = AGENT_DIR.name
DEFAULT_OPPONENTS = [
    "crustle_aware_fighting_agent",
    "dragapult_rule_based",
    "mega_lucario_beginner",
    "multiply_agent_best_940",
]
HISTORY_PATH = AGENT_DIR / "compare_eval_history.jsonl"


def _add_project_root() -> None:
    candidates = [AGENT_DIR, *AGENT_DIR.parents]
    for root in candidates:
        if (root / "battle_env").is_dir():
            if str(root) not in sys.path:
                sys.path.insert(0, str(root))
            return
    if len(AGENT_DIR.parents) >= 2:
        root = AGENT_DIR.parents[1]
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))


_add_project_root()

from battle_env.runner import play_match


def parse_args():
    parser = argparse.ArgumentParser(description="Evaluate the Alakazam rule-based agent.")
    parser.add_argument("--agent", type=str, default=DEFAULT_AGENT_NAME)
    parser.add_argument("--games", type=int, default=50)
    parser.add_argument("--output", type=Path, default=AGENT_DIR / "eval_report.json")
    parser.add_argument("--label", type=str, default=DEFAULT_AGENT_NAME)
    parser.add_argument("--progress-every", type=int, default=5)
    parser.add_argument("--opponents", type=str, default=",".join(DEFAULT_OPPONENTS))
    return parser.parse_args()


def append_eval_history(path: Path, run_record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(run_record, ensure_ascii=False) + "\n")


def _run_match(agent_name: str, opponent: str, game_index: int):
    use_swap = game_index % 2 == 1
    left = opponent if use_swap else agent_name
    right = agent_name if use_swap else opponent
    result = play_match(left, right, verbose=False, capture_details=False)
    won = (
        result["status"] == "success"
        and result["winner"] in (0, 1)
        and (result["agent_a"] if result["winner"] == 0 else result["agent_b"]) == agent_name
    )
    return result, won


def _build_game_record(result: dict, agent_name: str, opponent: str, game_index: int, label: str) -> dict:
    if result["status"] == "success" and result["winner"] in (0, 1):
        winner_name = result["agent_a"] if result["winner"] == 0 else result["agent_b"]
        score = 1.0 if winner_name == agent_name else 0.0
        outcome = "win" if score == 1.0 else "loss"
    elif result["winner"] == 2:
        score = 0.5
        outcome = "draw"
    else:
        score = 0.0
        outcome = "error"
    return {
        "label": label,
        "played_at": datetime.now(UTC).isoformat(),
        "opponent": opponent,
        "game_index": game_index + 1,
        "agent_a": result["agent_a"],
        "agent_b": result["agent_b"],
        "winner": result["winner"],
        "outcome": outcome,
        "score": score,
        "steps": result["steps"],
        "turn": result["turn"],
        "status": result["status"],
        "termination": result.get("termination", {"reason_key": "unknown", "reason_code": None}),
    }


def run_evaluation(
    agent_name: str,
    games: int,
    label: str,
    output: Path | None = None,
    progress_every: int = 5,
    opponents: list[str] | None = None,
) -> dict:
    run_at = datetime.now(UTC).isoformat()
    matchups = {}
    game_records = []
    if opponents is None:
        opponents = list(DEFAULT_OPPONENTS)
    for opponent in opponents:
        wins = 0
        total_steps = 0
        total_turns = 0
        reason_counts: dict[str, int] = {}
        opponent_start = time.perf_counter()
        for game_index in range(games):
            game_start = time.perf_counter()
            result, won = _run_match(agent_name, opponent, game_index)
            game_record = _build_game_record(result, agent_name, opponent, game_index, label)
            game_records.append(game_record)
            total_steps += result["steps"]
            total_turns += result["turn"]
            if won:
                wins += 1
            reason_key = game_record["termination"].get("reason_key", "unknown")
            reason_counts[reason_key] = reason_counts.get(reason_key, 0) + 1
            if (game_index + 1) % max(1, progress_every) == 0 or game_index + 1 == games:
                print(
                    f"eval_progress label={label} agent={agent_name} opponent={opponent} "
                    f"games={game_index + 1}/{games} wins={wins} "
                    f"last_game_sec={time.perf_counter() - game_start:.2f} "
                    f"avg_game_sec={(time.perf_counter() - opponent_start) / (game_index + 1):.2f}",
                    flush=True,
                )
        matchups[opponent] = {
            "wins": wins,
            "games": games,
            "win_rate": wins / float(games),
            "average_steps": total_steps / float(games),
            "average_turns": total_turns / float(games),
            "termination_reasons": reason_counts,
        }
        print(f"eval_done label={label} agent={agent_name} opponent={opponent} wins={wins}/{games}", flush=True)
    report = {"run_at": run_at, "label": label, "agent": agent_name, "matchups": matchups, "games": game_records}
    append_eval_history(HISTORY_PATH, report)
    if output is not None:
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main():
    args = parse_args()
    opponents = [name.strip() for name in args.opponents.split(",") if name.strip()]
    report = run_evaluation(
        args.agent,
        args.games,
        args.label,
        args.output,
        progress_every=args.progress_every,
        opponents=opponents,
    )
    print(json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
