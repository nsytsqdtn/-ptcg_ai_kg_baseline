# Notebook Replay Switch Design

## Goal

Switch the local battle replay integration to the notebook workflow defined in `replay_systems/replay/how-to-output-local-battle-as-json-and-view.ipynb`.

## Decision

The battle environment will stop generating self-contained `*.replay.html` files. It will instead:

- keep the existing structured `*.json` match record for local debugging and analysis
- generate a separate `*.vis.json` replay payload aligned with the notebook example
- provide a fixed uploader page at `replay_systems/replay/visualizer.html`

Users will open the uploader and choose a generated `*.vis.json` file.

## Replay Contract

The notebook example expects:

- a JSON array from `json.loads(visualize_data())`
- each visualizer frame extended with:
  - `obs`
  - `action`

The local battle integration will therefore build:

- `obs_log = [""] + per-step obs snapshots`
- `action_log = [None] + per-step selected index lists`
- `vis[i]["obs"] = obs_log[i]`
- `vis[i]["action"] = [action_log[i], action_log[i]]`

This mirrors the notebook exactly.

## Scope

Files to update:

- `battle_env/runner.py`
- `battle_env/recording.py`
- `battle_env/cli.py`
- `battle_env/__init__.py`
- `tests/test_local_battle.py`
- `tests/test_replay_visualizer.py`
- `README.md`

Files to add:

- `replay_systems/replay/visualizer.html`
- `docs/plans/2026-06-25-notebook-replay-switch.md`

## Compatibility

- `agents/` stays untouched
- `sample_code/` stays untouched
- legacy replay implementations remain archived and disconnected from the runtime path

## Verification

Required checks:

- targeted pytest for replay and CLI output behavior
- one real local battle run that produces `*.vis.json`
- browser validation that `visualizer.html` opens and exposes the notebook upload flow
