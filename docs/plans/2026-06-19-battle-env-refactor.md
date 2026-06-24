# Battle Environment Refactor Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a dedicated `battle_env` package that becomes the single local battle runtime for agent matches, logging, replay, metrics, and RL-facing data.

**Architecture:** Move battle runtime logic out of `scripts/local_battle.py` into a package with small modules for agent loading, runtime execution, recording, viewer output, and CLI wrapping. Reuse the existing viewer implementation as the only replay generator and relocate the official `cg` SDK unchanged into the package.

**Tech Stack:** Python 3.12, pytest, official `cg` SDK, JSON, dynamic module loading

---

### Task 1: Freeze the new package contract in tests

**Files:**
- Modify: `tests/test_local_battle.py`
- Modify: `tests/test_battle_viewer.py`

**Step 1: Write the failing tests**

```python
def test_local_battle_wrapper_delegates_to_battle_env_cli():
    module = load_module("root_local_battle", ROOT / "local_battle.py")
    assert callable(module.main)


def test_play_match_exposes_metrics_and_rl_fields():
    runner = load_module("battle_env_runner", ROOT / "battle_env" / "runner.py")
    result = runner.play_match("dragapult_rule_based", "mega_lucario_beginner")
    assert "metrics" in result
    assert "reward" in result["history"][0]
    assert "done" in result["history"][0]
    assert "delta_logs" in result["history"][0]
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_local_battle.py tests/test_battle_viewer.py -v`
Expected: FAIL because `battle_env` and `local_battle.py` do not yet exist.

**Step 3: Write minimal implementation**

Create the package, wrappers, and replay wiring needed for the tests.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_local_battle.py tests/test_battle_viewer.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_local_battle.py tests/test_battle_viewer.py local_battle.py battle_env
git commit -m "test: define battle environment package contract"
```

### Task 2: Create the battle_env package and migrate the runtime

**Files:**
- Create: `battle_env/__init__.py`
- Create: `battle_env/agents.py`
- Create: `battle_env/runner.py`
- Create: `battle_env/recording.py`
- Create: `battle_env/cli.py`
- Modify: `scripts/local_battle.py`
- Create: `local_battle.py`

**Step 1: Write the failing test**

```python
def test_play_series_returns_aggregate_stats_from_new_runner():
    runner = load_module("battle_env_runner_series", ROOT / "battle_env" / "runner.py")
    series = runner.play_series("dragapult_rule_based", "mega_lucario_beginner", games=2, swap_sides=True)
    assert series["games"] == 2
    assert "wins_by_agent" in series
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_local_battle.py::test_play_series_returns_aggregate_stats -v`
Expected: FAIL before the new runner is in place.

**Step 3: Write minimal implementation**

Implement:

- agent resolution by name or path
- match and series execution
- structured error results
- metrics population
- thin CLI wrappers

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_local_battle.py::test_play_series_returns_aggregate_stats -v`
Expected: PASS

**Step 5: Commit**

```bash
git add battle_env scripts/local_battle.py local_battle.py
git commit -m "feat: move local battle runtime into battle_env package"
```

### Task 3: Migrate the viewer and remove the inline replay implementation

**Files:**
- Create: `battle_env/viewer.py`
- Delete or stop using: inline replay HTML code in `scripts/local_battle.py`
- Modify: `tests/test_battle_viewer.py`

**Step 1: Write the failing test**

```python
def test_battle_env_viewer_writes_html_for_local_match_record(tmp_path):
    viewer = load_module("battle_env_viewer", ROOT / "battle_env" / "viewer.py")
    out_html = tmp_path / "viewer.html"
    viewer.write_html(ROOT / "battle_records" / "sample_match.json", out_html=out_html)
    assert out_html.exists()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_battle_viewer.py -v`
Expected: FAIL because `battle_env/viewer.py` does not exist yet.

**Step 3: Write minimal implementation**

Move the current root viewer implementation into `battle_env/viewer.py` and make any compatibility wrapper at the root import from the package instead of maintaining a second implementation.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_battle_viewer.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add battle_env/viewer.py battle_viewer.py tests/test_battle_viewer.py
git commit -m "refactor: unify replay generation through battle_env viewer"
```

### Task 4: Relocate the official cg SDK unchanged

**Files:**
- Create or move: `battle_env/cg/*`
- Stop runtime dependence on: `sample_submission/cg/*`

**Step 1: Write the failing test**

```python
def test_runner_uses_cg_from_battle_env_package():
    runner = load_module("battle_env_runner_cg", ROOT / "battle_env" / "runner.py")
    assert "battle_env" in runner.__file__
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_local_battle.py -v`
Expected: FAIL until imports are updated to the relocated SDK path.

**Step 3: Write minimal implementation**

Move the `cg` directory into `battle_env/cg` without editing its file contents, then update surrounding imports and `sys.path` handling to use the new package location.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_local_battle.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add battle_env/cg sample_submission
git commit -m "chore: relocate official cg sdk under battle_env"
```

### Task 5: Update docs and verify the full flow

**Files:**
- Modify: `README.md`

**Step 1: Write the failing test**

```python
def test_save_replay_html_still_writes_html(tmp_path):
    runner = load_module("battle_env_runner_docs", ROOT / "battle_env" / "runner.py")
    result = runner.play_match("dragapult_rule_based", "mega_lucario_beginner")
    out_html = tmp_path / "match.replay.html"
    runner.save_replay_html(result, out_html)
    assert "<title>Pokémon TCG Battle Viewer</title>" in out_html.read_text(encoding="utf-8")
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_local_battle.py::test_save_replay_html_writes_visualizer_page -v`
Expected: FAIL until the new viewer-backed save path is wired in.

**Step 3: Write minimal implementation**

Update README examples to use the new entrypoint and output model, then wire replay generation through the unified viewer-backed save function.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_local_battle.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add README.md tests/test_local_battle.py
git commit -m "docs: update local battle environment usage"
```
