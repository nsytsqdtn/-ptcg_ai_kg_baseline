from __future__ import annotations

import argparse
from pathlib import Path

from battle_env.recording import (
    build_log_paths,
    build_replay_path,
    save_human_log,
    save_match_record,
    save_replay_html,
    save_summary_log,
)
from battle_env.runner import play_match, play_series


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a local PTCG battle environment.")
    parser.add_argument("--agent-a", default="dragapult_rule_based", help="Agent name or explicit agent.py path.")
    parser.add_argument("--agent-b", default="mega_lucario_beginner", help="Agent name or explicit agent.py path.")
    parser.add_argument("--record-file", default="", help="Optional path to save the full match record as JSON.")
    parser.add_argument("--log-file", default="", help="Optional base path to save human-readable logs.")
    parser.add_argument("--replay-file", default="", help="Optional path to save the replay HTML page.")
    parser.add_argument("--verbose", action="store_true", help="Print step-by-step action and log summaries.")
    parser.add_argument("--games", type=int, default=1, help="Number of games to run.")
    parser.add_argument("--swap-sides", action="store_true", help="Alternate seating between games.")
    args = parser.parse_args(argv)

    if args.games == 1:
        result = play_match(args.agent_a, args.agent_b, verbose=args.verbose)
    else:
        result = play_series(
            args.agent_a,
            args.agent_b,
            games=args.games,
            swap_sides=args.swap_sides,
            verbose=args.verbose,
        )
    if args.record_file:
        save_match_record(result, Path(args.record_file))
    summary_log_path = None
    detail_log_path = None
    replay_path = None
    if args.verbose or args.log_file:
        summary_log_path, detail_log_path = build_log_paths(args.record_file, args.log_file, args.games)
        save_summary_log(result, summary_log_path)
        save_human_log(result, detail_log_path)
    if args.games == 1 and (args.verbose or args.log_file or args.replay_file):
        replay_path = build_replay_path(args.record_file, args.replay_file, args.log_file, args.games)
        save_replay_html(result, replay_path)
    if args.games == 1:
        print(
            f"{result['agent_a']} vs {result['agent_b']}: "
            f"winner={result['winner']} turn={result['turn']} steps={result['steps']}"
        )
    else:
        print(
            f"series games={result['games']} swap_sides={result['swap_sides']} "
            f"wins={result['wins_by_agent']} draws={result['draws']} "
            f"avg_turns={result['average_turns']:.2f} avg_steps={result['average_steps']:.2f}"
        )
    if args.record_file:
        print(f"record_file={Path(args.record_file).resolve()}")
    if summary_log_path is not None:
        print(f"summary_log_file={summary_log_path.resolve()}")
        print(f"detail_log_file={detail_log_path.resolve()}")
    if replay_path is not None:
        print(f"replay_file={replay_path.resolve()}")
    return 0
