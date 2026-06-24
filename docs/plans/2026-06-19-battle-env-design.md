# Local Battle Environment Design

**Date:** 2026-06-19

## Goal

Rebuild the local PTCG battle tooling into a dedicated battle environment package that can serve as the single foundation for:

- local agent-vs-agent matches
- future algorithm competitions
- structured logs and replay output
- metrics and match summaries
- reinforcement learning data collection

## Constraints

- Remove the custom inline replay implementation currently embedded in `scripts/local_battle.py`.
- Use the existing root `battle_viewer.py` implementation as the only HTML replay generator.
- The official `cg` SDK may be relocated into the new battle environment area, but the contents of the `cg` directory must not be modified.
- Keep agent management minimal. No manifest system, no agent registry, no directory scanning requirement beyond simple name-to-path resolution.

## Architecture

Create a dedicated `battle_env/` package with narrow responsibilities:

- `battle_env/agents.py`
  Resolve an agent reference to `agents/<name>/agent.py` or an explicit path, then load the module.
- `battle_env/runner.py`
  Own the battle loop, series loop, error handling, step capture, and the public runtime API.
- `battle_env/recording.py`
  Own structured JSON serialization, text logs, turn summaries, output path helpers, and match-level metrics.
- `battle_env/viewer.py`
  Host the replay viewer implementation migrated from the current root `battle_viewer.py`.
- `battle_env/cli.py`
  Provide a single command-line entrypoint for local matches and series runs.
- `battle_env/cg/`
  Contain the official SDK copied from `sample_submission/cg` without content changes.

Thin wrapper entrypoints should remain at the surface:

- `local_battle.py`
- `scripts/local_battle.py`

Both wrappers should delegate directly to `battle_env.cli.main()`.

## Public Runtime API

The environment should expose a stable Python API:

- `play_match(agent_a, agent_b, verbose=False)`
- `play_series(agent_a, agent_b, games=1, swap_sides=False, verbose=False)`
- `save_match_record(result, path)`
- `save_human_log(result, path)`
- `save_summary_log(result, path)`
- `save_replay_html(result, path)`

## Data Model

The match result should stay JSON-serializable and remain suitable for replay, debugging, and RL export.

Required top-level fields:

- `status`
- `winner`
- `turn`
- `steps`
- `agent_a`
- `agent_b`
- `agent_a_path`
- `agent_b_path`
- `recorded_at`
- `history`
- `summary`
- `metrics`

Required per-step fields:

- `step`
- `player_index`
- `agent`
- `turn`
- `turn_action_count`
- `context_name`
- `select_type_name`
- `available_options`
- `selected`
- `selected_options`
- `board_snapshot`
- `hand_snapshot`
- `logs`
- `delta_logs`
- `reward`
- `done`
- `result_after_step`

`delta_logs` should capture only the logs produced by the current step so downstream consumers do not need to diff cumulative logs themselves.

`reward` and `done` should be present now even if the reward is currently sparse and terminal-only. That keeps the structure stable for future RL code.

## Replay Strategy

The replay HTML should always be generated through the migrated viewer module. The runner should save the JSON match record first, then render replay HTML from that saved JSON path or from the same normalized match record structure.

There should be no second HTML rendering implementation left in the runtime path.

## Metrics

Keep metrics minimal and useful:

- winner
- total turns
- total steps
- steps per turn
- action counts by player
- action counts by select type
- final status

For series runs:

- wins by agent
- draws
- average turns
- average steps

## Agent Resolution

Keep agent resolution intentionally small:

- if the argument is an existing file path, use it
- otherwise resolve `agents/<name>/agent.py`

No manifest parsing is required in the new design.

## Testing Strategy

Use TDD for the refactor.

Core tests should cover:

- CLI wrappers delegate into the new package
- agent reference resolution by name and by path
- match execution still completes between sample agents
- replay HTML is generated through the migrated viewer module
- result records contain stable metrics and RL-facing fields
- error capture still works when an agent raises

## Non-Goals

- no tournament scheduler
- no database
- no training loop implementation
- no expanded agent metadata system
- no second viewer format
