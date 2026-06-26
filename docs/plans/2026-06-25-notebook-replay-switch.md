# Notebook Replay Switch Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the current replay output path with the notebook-compatible `*.vis.json + visualizer.html` workflow.

**Architecture:** `play_match()` will capture notebook-style replay inputs directly from `visualize_data()`, the raw obs passed to the agent, and the chosen action indices. Recording helpers will write `*.vis.json` and stop emitting runtime `*.replay.html` files. A fixed uploader HTML will live under `replay_systems/replay/`.

**Tech Stack:** Python, pytest, static HTML, existing `cg.game` APIs.

---

### Task 1: Lock the new replay contract in tests

**Files:**
- Modify: `tests/test_local_battle.py`
- Modify: `tests/test_replay_visualizer.py`

**Step 1: Write the failing tests**

- assert replay output is `*.vis.json`
- assert saved replay JSON is a list of frames with `obs` and `action`
- assert uploader HTML matches the notebook flow and posts to `https://ptcgvis.heroz.jp/Visualizer/Replay/0`

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_local_battle.py tests/test_replay_visualizer.py -q`

**Step 3: Do not touch implementation yet**

Leave the old replay implementation in place so the test proves the contract changed.

**Step 4: Re-run the failing tests if needed**

Confirm failures are caused by the old replay behavior.

### Task 2: Capture notebook-compatible visualizer frames

**Files:**
- Modify: `battle_env/runner.py`

**Step 1: Write the minimal implementation**

- track per-step raw obs snapshots
- remove `search_begin_input` from saved obs copies
- track per-step selected action indices
- after battle, transform `json.loads(visualize_data())` into notebook-compatible frames

**Step 2: Run targeted tests**

Run: `pytest tests/test_local_battle.py -q`

### Task 3: Replace replay writers with vis/uploader outputs

**Files:**
- Modify: `battle_env/recording.py`
- Modify: `battle_env/cli.py`
- Modify: `battle_env/__init__.py`
- Add: `replay_systems/replay/visualizer.html`

**Step 1: Write the minimal implementation**

- add `save_visualizer_json(...)`
- add `build_visualizer_path(...)`
- switch CLI flag from `--replay-file` to `--vis-file`
- copy the uploader HTML from the notebook into `replay_systems/replay/visualizer.html`

**Step 2: Run targeted tests**

Run: `pytest tests/test_local_battle.py tests/test_replay_visualizer.py -q`

### Task 4: Update docs and user-facing output

**Files:**
- Modify: `README.md`

**Step 1: Update commands and output examples**

- remove `*.replay.html` guidance
- document `*.vis.json`
- document opening `replay_systems/replay/visualizer.html`

**Step 2: Run full verification**

Run:

```powershell
pytest tests\test_local_battle.py tests\test_replay_visualizer.py tests\test_battle_viewer.py -q
python local_battle.py --agent-a dragapult_rule_based --agent-b mega_lucario_beginner --record-file battle_records\sample_match.json --vis-file battle_records\sample_match.vis.json
```
