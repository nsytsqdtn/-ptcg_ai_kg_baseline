# RL MCTS Submission-Compatible Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Retrain and restructure `rl_mcts_sample` so it learns primarily against the existing rule-based opponents and deploys through a submission-compatible `main.py` entrypoint.

**Architecture:** Make `agents/rl_mcts_sample/main.py` the canonical inference entrypoint and submission surface, keep shared model/training code in `model.py` and `train.py`, and extend training to use named rule-based opponents plus per-opponent evaluation reporting. Preserve loud failure behavior instead of adding fallback paths.

**Tech Stack:** Python 3.12, PyTorch CUDA in `sam2`, pytest, current `battle_env`, official `cg` submission layout

---

### Task 1: Freeze the submission-style contract in tests

**Files:**
- Modify: `tests/test_local_battle.py`

**Step 1: Write the failing test**

```python
def test_rl_mcts_sample_submission_entrypoint_exists():
    module = load_module("rl_mcts_sample_main", ROOT / "agents" / "rl_mcts_sample" / "main.py")
    assert callable(module.agent)
    assert isinstance(module.my_deck, list)
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_local_battle.py::test_rl_mcts_sample_submission_entrypoint_exists -v`
Expected: FAIL because `main.py` does not yet exist as the canonical entrypoint.

**Step 3: Write minimal implementation**

Create `agents/rl_mcts_sample/main.py` and expose the submission-style `agent()` entrypoint plus `my_deck`.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_local_battle.py::test_rl_mcts_sample_submission_entrypoint_exists -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_local_battle.py agents/rl_mcts_sample/main.py
git commit -m "test: define submission entrypoint for rl mcts sample"
```

### Task 2: Make local resolution use `main.py`

**Files:**
- Modify: `battle_env/agents.py`
- Modify: `tests/test_local_battle.py`

**Step 1: Write the failing test**

```python
def test_battle_env_resolves_rl_mcts_sample_to_main_py():
    agents = load_module("battle_env_agents_submission", ROOT / "battle_env" / "agents.py")
    path = agents.resolve_agent("rl_mcts_sample")
    assert path.name == "main.py"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_local_battle.py::test_battle_env_resolves_rl_mcts_sample_to_main_py -v`
Expected: FAIL while the resolver still prefers `agent.py`.

**Step 3: Write minimal implementation**

Update resolution rules to prefer `main.py` when present, while keeping compatibility for older agents that still use `agent.py`.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_local_battle.py::test_battle_env_resolves_rl_mcts_sample_to_main_py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add battle_env/agents.py tests/test_local_battle.py
git commit -m "feat: resolve submission-style main.py agents"
```

### Task 3: Extend training to use named rule-based opponents

**Files:**
- Modify: `agents/rl_mcts_sample/model.py`
- Modify: `agents/rl_mcts_sample/train.py`
- Modify: `tests/test_local_battle.py`

**Step 1: Write the failing test**

```python
def test_rl_mcts_training_metadata_records_named_opponents():
    metadata = json.loads((ROOT / "agents" / "rl_mcts_sample" / "training_metadata.json").read_text(encoding="utf-8"))
    assert "opponents" in metadata["config"]
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_local_battle.py::test_rl_mcts_training_metadata_records_named_opponents -v`
Expected: FAIL because the metadata does not yet describe named-opponent training.

**Step 3: Write minimal implementation**

Add opponent configuration, named-opponent game collection, and per-opponent evaluation reporting to the training code.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_local_battle.py::test_rl_mcts_training_metadata_records_named_opponents -v`
Expected: PASS

**Step 5: Commit**

```bash
git add agents/rl_mcts_sample/model.py agents/rl_mcts_sample/train.py tests/test_local_battle.py
git commit -m "feat: train rl mcts sample against named rule agents"
```

### Task 4: Align package structure with submission expectations

**Files:**
- Create or copy: `agents/rl_mcts_sample/cg/*`
- Modify: `agents/rl_mcts_sample/README.md`
- Modify: `tests/test_local_battle.py`

**Step 1: Write the failing test**

```python
def test_rl_mcts_sample_submission_package_contains_required_files():
    agent_dir = ROOT / "agents" / "rl_mcts_sample"
    assert (agent_dir / "main.py").exists()
    assert (agent_dir / "deck.csv").exists()
    assert (agent_dir / "cg" / "__init__.py").exists()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_local_battle.py::test_rl_mcts_sample_submission_package_contains_required_files -v`
Expected: FAIL until the package layout is aligned.

**Step 3: Write minimal implementation**

Copy the required `cg` package into the candidate directory and update docs to describe the final submission layout.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_local_battle.py::test_rl_mcts_sample_submission_package_contains_required_files -v`
Expected: PASS

**Step 5: Commit**

```bash
git add agents/rl_mcts_sample/cg agents/rl_mcts_sample/README.md tests/test_local_battle.py
git commit -m "chore: align rl mcts sample with submission package layout"
```

### Task 5: Retrain, verify locally, and document usage

**Files:**
- Modify: `README.md`
- Create or update: `agents/rl_mcts_sample/model_latest.pth`
- Create or update: `agents/rl_mcts_sample/training_metadata.json`

**Step 1: Write the failing test**

```python
def test_play_match_supports_rl_mcts_sample_submission_entrypoint():
    runner = load_module("battle_env_runner_submission_rl", ROOT / "battle_env" / "runner.py")
    result = runner.play_match("rl_mcts_sample", "mega_lucario_beginner")
    assert result["status"] == "success"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_local_battle.py::test_play_match_supports_rl_mcts_sample_submission_entrypoint -v`
Expected: FAIL before the new entrypoint and retrained checkpoint are both wired.

**Step 3: Write minimal implementation**

Retrain with the named rule-based opponents, update the checkpoint and metadata, and document the local-vs-submission usage in README.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_local_battle.py::test_play_match_supports_rl_mcts_sample_submission_entrypoint -v`
Expected: PASS

**Step 5: Commit**

```bash
git add README.md agents/rl_mcts_sample/model_latest.pth agents/rl_mcts_sample/training_metadata.json tests/test_local_battle.py
git commit -m "feat: retrain submission-compatible rl mcts sample"
```
