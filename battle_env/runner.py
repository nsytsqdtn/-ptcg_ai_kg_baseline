from __future__ import annotations

import json
import traceback
from datetime import UTC, datetime
from pathlib import Path

from battle_env.agents import load_agent_module, resolve_agent
from battle_env.recording import (
    build_match_metrics,
    capture_board_snapshot,
    describe_logs,
    describe_option,
    format_step_log,
    normalize_for_json,
    save_human_log,
    save_match_record,
    save_summary_log,
    save_visualizer_json,
)
from cg.api import LogType, SelectContext, SelectType, to_observation_class
from cg.game import battle_finish, battle_select, battle_start, visualize_data


def build_error_result(
    *,
    phase: str,
    agent_a_path: Path,
    agent_b_path: Path,
    steps: int,
    history: list[dict],
    exc: Exception,
    player_index: int | None = None,
    step_record: dict | None = None,
) -> dict:
    turn = history[-1]["turn"] if history else 0
    result = {
        "status": "error",
        "winner": None,
        "turn": turn,
        "steps": steps,
        "agent_a": agent_a_path.parent.name,
        "agent_b": agent_b_path.parent.name,
        "agent_a_path": str(agent_a_path),
        "agent_b_path": str(agent_b_path),
        "recorded_at": datetime.now(UTC).isoformat(),
        "history": history,
        "steps_data": [],
        "summary": {
            "status": "error",
            "phase": phase,
            "steps": steps,
            "agent_a": agent_a_path.parent.name,
            "agent_b": agent_b_path.parent.name,
        },
        "termination": {
            "reason_code": None,
            "reason_key": "error",
            "winner": None,
        },
        "error": {
            "phase": phase,
            "player_index": player_index,
            "message": str(exc),
            "exception_type": type(exc).__name__,
            "traceback": traceback.format_exc(),
            "step_record": step_record,
        },
    }
    result["metrics"] = build_match_metrics(history, winner=None, turn=turn, steps=steps, status="error")
    return result


def print_step_log(step_record: dict) -> None:
    print(format_step_log(step_record))


def _enum_name(enum_cls, value) -> str:
    if hasattr(value, "name"):
        return value.name
    try:
        return enum_cls(value).name
    except Exception:
        return str(value)


def _termination_from_logs(logs) -> dict:
    reason_map = {
        1: "prize_out",
        2: "deck_out",
        3: "no_active",
        4: "card_effect",
    }
    for log in reversed(logs or []):
        if _enum_name(LogType, getattr(log, "type", None)) != "RESULT":
            continue
        code = getattr(log, "reason", None)
        return {
            "reason_code": code,
            "reason_key": reason_map.get(code, "unknown"),
            "winner": getattr(log, "result", None),
        }
    return {
        "reason_code": None,
        "reason_key": "unknown",
        "winner": None,
    }


def _sanitize_observation_snapshot(obs_dict) -> dict:
    snapshot = normalize_for_json(obs_dict)
    if isinstance(snapshot, dict):
        snapshot.pop("search_begin_input", None)
    return snapshot


def _build_visualizer_steps(raw_visualizer_steps: list[dict], obs_log: list, action_log: list) -> list[dict]:
    steps = []
    for index, frame in enumerate(raw_visualizer_steps):
        item = dict(frame)
        item["obs"] = obs_log[index] if index < len(obs_log) else ""
        item["action"] = [action_log[index], action_log[index]] if index < len(action_log) else [None, None]
        steps.append(item)
    return steps


def _module_fallback_count(module) -> int:
    getter = getattr(module, "get_fallback_count", None)
    if callable(getter):
        try:
            return int(getter())
        except Exception:
            return 0
    return 0


def play_match(
    agent_a_path: str | Path,
    agent_b_path: str | Path,
    verbose: bool = False,
    capture_details: bool = True,
) -> dict:
    agent_a_path = resolve_agent(agent_a_path)
    agent_b_path = resolve_agent(agent_b_path)
    try:
        agent_a = load_agent_module(agent_a_path)
        agent_b = load_agent_module(agent_b_path)
    except Exception as exc:
        return build_error_result(
            phase="load_agent",
            agent_a_path=agent_a_path,
            agent_b_path=agent_b_path,
            steps=0,
            history=[],
            exc=exc,
        )

    decks = [list(agent_a.my_deck), list(agent_b.my_deck)]
    agents = [agent_a, agent_b]
    history: list[dict] = []
    steps_data: list[dict] = []
    obs_log: list = [""]
    action_log: list = [None]

    obs, start_data = battle_start(decks[0], decks[1])
    if not start_data.battlePtr:
        exc = RuntimeError(
            f"BattleStart failed: errorPlayer={start_data.errorPlayer}, errorType={start_data.errorType}"
        )
        return build_error_result(
            phase="battle_start",
            agent_a_path=agent_a_path,
            agent_b_path=agent_b_path,
            steps=0,
            history=[],
            exc=exc,
            player_index=start_data.errorPlayer if start_data.errorPlayer >= 0 else None,
        )

    steps = 0
    previous_log_count = 0
    try:
        while True:
            steps += 1
            observation = to_observation_class(obs)
            state = observation.current
            if state is not None and state.result != -1:
                termination = _termination_from_logs(getattr(observation, "logs", []))
                if state.result == 2 and termination["reason_key"] == "unknown":
                    termination["reason_key"] = "draw"
                if capture_details:
                    steps_data = _build_visualizer_steps(json.loads(visualize_data()), obs_log, action_log)
                result = {
                    "status": "success",
                    "winner": state.result,
                    "turn": state.turn,
                    "steps": steps,
                    "agent_a": agent_a_path.parent.name,
                    "agent_b": agent_b_path.parent.name,
                    "agent_a_path": str(agent_a_path),
                    "agent_b_path": str(agent_b_path),
                    "recorded_at": datetime.now(UTC).isoformat(),
                    "history": history,
                    "steps_data": steps_data,
                    "summary": {
                        "winner": state.result,
                        "turn": state.turn,
                        "steps": steps,
                        "agent_a": agent_a_path.parent.name,
                        "agent_b": agent_b_path.parent.name,
                        "last_logs": history[-1]["logs"] if history else [],
                    },
                    "termination": termination,
                    "fallback_counts": {
                        "agent_a": _module_fallback_count(agent_a),
                        "agent_b": _module_fallback_count(agent_b),
                    },
                }
                result["metrics"] = build_match_metrics(
                    history,
                    winner=state.result,
                    turn=state.turn,
                    steps=steps,
                    status="success",
                )
                return result

            if observation.select is None:
                raise RuntimeError("Unexpected observation without select data during battle loop.")

            player_index = state.yourIndex
            board_snapshot = capture_board_snapshot(observation) if capture_details else None
            step_record = {
                "step": steps,
                "player_index": player_index,
                "agent": agent_a_path.parent.name if player_index == 0 else agent_b_path.parent.name,
                "turn": state.turn,
                "turn_action_count": state.turnActionCount,
                "context": _enum_name(SelectContext, observation.select.context),
                "context_name": _enum_name(SelectContext, observation.select.context),
                "select_type": _enum_name(SelectType, observation.select.type),
                "select_type_name": _enum_name(SelectType, observation.select.type),
                "option_count": len(observation.select.option),
                "min_count": observation.select.minCount,
                "max_count": observation.select.maxCount,
                "board_snapshot": board_snapshot,
                "hand_snapshot": [] if board_snapshot is None else list(board_snapshot["players"][player_index]["hand"]),
                "available_options": (
                    []
                    if not capture_details
                    else [describe_option(option, observation, player_index) for option in observation.select.option]
                ),
                "reward": 0,
                "done": False,
                "delta_logs": [],
            }
            try:
                selected = agents[player_index].agent(obs)
                step_record["selected"] = list(selected)
                step_record["selected_options"] = (
                    []
                    if not capture_details
                    else [describe_option(observation.select.option[index], observation, player_index) for index in selected]
                )
            except Exception as exc:
                history.append(step_record)
                return build_error_result(
                    phase="agent_action",
                    agent_a_path=agent_a_path,
                    agent_b_path=agent_b_path,
                    steps=steps,
                    history=history,
                    exc=exc,
                    player_index=player_index,
                    step_record=step_record,
                )
            try:
                if capture_details:
                    obs_log.append(_sanitize_observation_snapshot(obs))
                    action_log.append(list(selected))
                next_obs = battle_select(selected)
                next_observation = to_observation_class(next_obs)
                if capture_details:
                    all_logs = describe_logs(next_observation.logs)
                    step_record["logs"] = all_logs
                    step_record["delta_logs"] = all_logs[previous_log_count:]
                    previous_log_count = len(all_logs)
                else:
                    step_record["logs"] = []
                    step_record["delta_logs"] = []
                step_record["result_after_step"] = next_observation.current.result if next_observation.current else None
                step_record["done"] = bool(next_observation.current and next_observation.current.result != -1)
                if step_record["done"]:
                    winner = next_observation.current.result
                    if winner == player_index:
                        step_record["reward"] = 1
                    elif winner in (0, 1):
                        step_record["reward"] = -1
            except Exception as exc:
                history.append(step_record)
                return build_error_result(
                    phase="battle_select",
                    agent_a_path=agent_a_path,
                    agent_b_path=agent_b_path,
                    steps=steps,
                    history=history,
                    exc=exc,
                    player_index=player_index,
                    step_record=step_record,
                )
            history.append(step_record)
            if verbose:
                print_step_log(step_record)
            obs = next_obs
    except Exception as exc:
        return build_error_result(
            phase="battle_loop",
            agent_a_path=agent_a_path,
            agent_b_path=agent_b_path,
            steps=steps,
            history=history,
            exc=exc,
        )
    finally:
        battle_finish()


def play_series(
    agent_a: str | Path,
    agent_b: str | Path,
    games: int = 1,
    swap_sides: bool = False,
    verbose: bool = False,
    capture_details: bool = True,
) -> dict:
    if games <= 0:
        raise ValueError("games must be >= 1")

    results = []
    wins_by_agent: dict[str, int] = {}
    draws = 0
    total_steps = 0
    total_turns = 0

    for game_index in range(games):
        use_swap = swap_sides and game_index % 2 == 1
        left = agent_b if use_swap else agent_a
        right = agent_a if use_swap else agent_b
        result = play_match(left, right, verbose=verbose, capture_details=capture_details)
        result["game_index"] = game_index + 1
        result["swapped_sides"] = use_swap
        results.append(result)
        total_steps += result["steps"]
        total_turns += result["turn"]

        if result["winner"] == 2:
            draws += 1
        elif result["winner"] in (0, 1):
            winner_name = result["agent_a"] if result["winner"] == 0 else result["agent_b"]
            wins_by_agent[winner_name] = wins_by_agent.get(winner_name, 0) + 1

    return {
        "games": games,
        "swap_sides": swap_sides,
        "results": results,
        "wins_by_agent": wins_by_agent,
        "draws": draws,
        "average_steps": total_steps / games,
        "average_turns": total_turns / games,
    }


__all__ = [
    "play_match",
    "play_series",
    "save_human_log",
    "save_match_record",
    "save_visualizer_json",
    "save_summary_log",
]
