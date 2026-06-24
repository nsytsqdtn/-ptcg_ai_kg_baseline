# RL MCTS Sample Agent Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Convert the sample RL/MCTS notebook into a CUDA-trainable local candidate agent that loads trained weights and plays through the unified battle environment.

**Architecture:** Keep one shared implementation for model, feature encoding, and MCTS under `agents/rl_mcts_sample/`, with `train.py` for training and `agent.py` for inference-only runtime use. Preserve a notebook copy for reference but make the script path the reproducible training entrypoint.

**Tech Stack:** Python 3.12, PyTorch CUDA (`sam2` conda env), pytest, official `cg` SDK compatibility path, existing `battle_env` runtime

---

### Task 1: Freeze the new RL agent contract in tests

**Files:**
- Modify: `tests/test_local_battle.py`

**Step 1: Write the failing test**

```python
def test_rl_mcts_sample_agent_module_exposes_agent_and_deck():
    module = load_module("rl_mcts_sample_agent", ROOT / "agents" / "rl_mcts_sample" / "agent.py")
    assert callable(module.agent)
    assert isinstance(module.my_deck, list)
    assert module.my_deck
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_local_battle.py::test_rl_mcts_sample_agent_module_exposes_agent_and_deck -v`
Expected: FAIL because the new agent does not exist yet.

**Step 3: Write minimal implementation**

Create the new agent directory, add `agent.py`, and expose `agent` plus `my_deck`.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_local_battle.py::test_rl_mcts_sample_agent_module_exposes_agent_and_deck -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_local_battle.py agents/rl_mcts_sample
git commit -m "test: define rl mcts sample agent contract"
```

### Task 2: Extract shared model and inference logic

**Files:**
- Create: `agents/rl_mcts_sample/model.py`
- Modify: `agents/rl_mcts_sample/agent.py`

**Step 1: Write the failing test**

```python
def test_rl_mcts_sample_agent_reports_missing_weights_cleanly(monkeypatch):
    module = load_module("rl_mcts_sample_agent_missing", ROOT / "agents" / "rl_mcts_sample" / "agent.py")
    monkeypatch.setattr(module, "MODEL_PATH", ROOT / "agents" / "rl_mcts_sample" / "missing.pth")
    with pytest.raises(FileNotFoundError):
        module.load_model()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_local_battle.py::test_rl_mcts_sample_agent_reports_missing_weights_cleanly -v`
Expected: FAIL before the loader exists.

**Step 3: Write minimal implementation**

Extract the notebook model and MCTS code into `model.py`, then make `agent.py` provide a cached `load_model()` helper with clear missing-checkpoint behavior.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_local_battle.py::test_rl_mcts_sample_agent_reports_missing_weights_cleanly -v`
Expected: PASS

**Step 5: Commit**

```bash
git add agents/rl_mcts_sample/model.py agents/rl_mcts_sample/agent.py tests/test_local_battle.py
git commit -m "feat: extract rl mcts model and inference loader"
```

### Task 3: Add the CUDA training entrypoint and localized notebook copy

**Files:**
- Create: `agents/rl_mcts_sample/train.py`
- Create: `agents/rl_mcts_sample/reinforcement-learning-and-mcts-sample-code.ipynb`
- Create: `agents/rl_mcts_sample/README.md`

**Step 1: Write the failing test**

```python
def test_rl_mcts_sample_training_files_exist():
    agent_dir = ROOT / "agents" / "rl_mcts_sample"
    assert (agent_dir / "train.py").exists()
    assert (agent_dir / "reinforcement-learning-and-mcts-sample-code.ipynb").exists()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_local_battle.py::test_rl_mcts_sample_training_files_exist -v`
Expected: FAIL before the files are added.

**Step 3: Write minimal implementation**

Add a script version of the notebook training loop and copy the notebook into the new agent directory with local path bootstrap.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_local_battle.py::test_rl_mcts_sample_training_files_exist -v`
Expected: PASS

**Step 5: Commit**

```bash
git add agents/rl_mcts_sample/train.py agents/rl_mcts_sample/reinforcement-learning-and-mcts-sample-code.ipynb agents/rl_mcts_sample/README.md tests/test_local_battle.py
git commit -m "feat: add rl mcts sample training entrypoint"
```

### Task 4: Train a checkpoint on CUDA and wire runtime inference

**Files:**
- Create: `agents/rl_mcts_sample/model_latest.pth`
- Modify: `agents/rl_mcts_sample/agent.py`

**Step 1: Write the failing test**

```python
def test_rl_mcts_sample_agent_can_load_checkpoint():
    module = load_module("rl_mcts_sample_agent_checkpoint", ROOT / "agents" / "rl_mcts_sample" / "agent.py")
    model = module.load_model()
    assert model is not None
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_local_battle.py::test_rl_mcts_sample_agent_can_load_checkpoint -v`
Expected: FAIL until a real checkpoint exists.

**Step 3: Write minimal implementation**

Run training with `conda run -n sam2 python agents/rl_mcts_sample/train.py` and save the latest usable checkpoint as `model_latest.pth`.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_local_battle.py::test_rl_mcts_sample_agent_can_load_checkpoint -v`
Expected: PASS

**Step 5: Commit**

```bash
git add agents/rl_mcts_sample/model_latest.pth agents/rl_mcts_sample/agent.py tests/test_local_battle.py
git commit -m "feat: add trained rl mcts sample checkpoint"
```

### Task 5: Verify end-to-end battle execution and document usage

**Files:**
- Modify: `README.md`

**Step 1: Write the failing test**

```python
def test_play_match_supports_rl_mcts_sample_agent():
    runner = load_module("battle_env_runner_rl", ROOT / "battle_env" / "runner.py")
    result = runner.play_match("rl_mcts_sample", "mega_lucario_beginner")
    assert result["status"] == "success"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_local_battle.py::test_play_match_supports_rl_mcts_sample_agent -v`
Expected: FAIL before the trained agent is wired and loadable.

**Step 3: Write minimal implementation**

Document the training command and runtime usage, then ensure the new agent works through the existing match runner.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_local_battle.py::test_play_match_supports_rl_mcts_sample_agent -v`
Expected: PASS

**Step 5: Commit**

```bash
git add README.md tests/test_local_battle.py
git commit -m "docs: document rl mcts sample agent usage"
```
