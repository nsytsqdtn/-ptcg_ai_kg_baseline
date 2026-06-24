# Crustle Kangaskhan Rule-Guided PPO Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build and train a submission-compatible `crustle_mega_kangaskhan_rule_rl_p1` agent that combines a deck-specific rule prior with residual PPO and wins reliably against the two fixed rule-based opponents.

**Architecture:** Keep `agents/crustle_mega_kangaskhan_rule_rl_p1/main.py` as the canonical inference entrypoint. Put reusable runtime, rule, RL, training, evaluation, and packaging helpers inside the same agent directory so local battle execution and final submission use the same logic.

**Tech Stack:** Python 3.12, current `battle_env`, current `cg` SDK, PyTorch, pytest.

---

### Task 1: Freeze the submission contract for the new agent

**Files:**
- Modify: `D:\workspace\ptcg\tests\test_local_battle.py`
- Create: `D:\workspace\ptcg\agents\crustle_mega_kangaskhan_rule_rl_p1\main.py`
- Create: `D:\workspace\ptcg\agents\crustle_mega_kangaskhan_rule_rl_p1\deck.csv`

**Step 1: Write the failing test**

Add tests asserting the new agent exposes `agent()` and `my_deck`, and that `battle_env` resolves the directory to `main.py`.

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_local_battle.py -k crustle_kangaskhan_submission -v`
Expected: FAIL because `main.py` and the tests do not exist yet.

**Step 3: Write minimal implementation**

Create a minimal `main.py` and normalize `desk.csv` into `deck.csv`.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_local_battle.py -k crustle_kangaskhan_submission -v`
Expected: PASS.

### Task 2: Freeze core deck-state and rule-prior behavior

**Files:**
- Modify: `D:\workspace\ptcg\tests\test_local_battle.py`
- Create: `D:\workspace\ptcg\agents\crustle_mega_kangaskhan_rule_rl_p1\runtime.py`
- Create: `D:\workspace\ptcg\agents\crustle_mega_kangaskhan_rule_rl_p1\rule_prior.py`

**Step 1: Write the failing test**

Add tests for pure Python helpers:
- deck CSV loader returns 60 cards
- safe fallback chooses a legal action index
- rule-prior result includes `total_logit`, `breakdown`, and `reason_tags`

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_local_battle.py -k crustle_kangaskhan_runtime -v`
Expected: FAIL because helper modules do not exist yet.

**Step 3: Write minimal implementation**

Implement the helper modules with the smallest legal runtime surface needed by the tests.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_local_battle.py -k crustle_kangaskhan_runtime -v`
Expected: PASS.

### Task 3: Implement runtime inference path

**Files:**
- Modify: `D:\workspace\ptcg\agents\crustle_mega_kangaskhan_rule_rl_p1\main.py`
- Create: `D:\workspace\ptcg\agents\crustle_mega_kangaskhan_rule_rl_p1\deck_state.py`
- Create: `D:\workspace\ptcg\agents\crustle_mega_kangaskhan_rule_rl_p1\observation_builder.py`
- Create: `D:\workspace\ptcg\agents\crustle_mega_kangaskhan_rule_rl_p1\action_encoder.py`
- Create: `D:\workspace\ptcg\agents\crustle_mega_kangaskhan_rule_rl_p1\policy.py`
- Create: `D:\workspace\ptcg\agents\crustle_mega_kangaskhan_rule_rl_p1\value.py`

**Step 1: Write the failing test**

Add a test that the new agent can play one local match successfully against `mega_lucario_beginner`.

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_local_battle.py::test_play_match_supports_crustle_kangaskhan_submission_entrypoint -v`
Expected: FAIL because runtime logic is incomplete.

**Step 3: Write minimal implementation**

Implement legal-action normalization, observation features, per-action encoding, rule-prior scoring, residual policy inference, deterministic selection, and fallback handling.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_local_battle.py::test_play_match_supports_crustle_kangaskhan_submission_entrypoint -v`
Expected: PASS.

### Task 4: Implement training, distillation, and evaluation tooling

**Files:**
- Create: `D:\workspace\ptcg\agents\crustle_mega_kangaskhan_rule_rl_p1\train.py`
- Create: `D:\workspace\ptcg\agents\crustle_mega_kangaskhan_rule_rl_p1\evaluate.py`
- Create: `D:\workspace\ptcg\agents\crustle_mega_kangaskhan_rule_rl_p1\ppo.py`
- Create: `D:\workspace\ptcg\agents\crustle_mega_kangaskhan_rule_rl_p1\trajectory.py`
- Create: `D:\workspace\ptcg\agents\crustle_mega_kangaskhan_rule_rl_p1\distill.py`

**Step 1: Write the failing test**

Add tests that training metadata records named opponents and that evaluation helpers emit per-opponent stats.

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_local_battle.py -k crustle_kangaskhan_training -v`
Expected: FAIL because scripts and metadata are missing.

**Step 3: Write minimal implementation**

Implement rule distillation, PPO rollout collection, PPO updates, deterministic evaluation, checkpoint saving, and metadata writing.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_local_battle.py -k crustle_kangaskhan_training -v`
Expected: PASS.

### Task 5: Align package layout with submission expectations

**Files:**
- Modify: `D:\workspace\ptcg\tests\test_local_battle.py`
- Create: `D:\workspace\ptcg\agents\crustle_mega_kangaskhan_rule_rl_p1\cg\__init__.py`

**Step 1: Write the failing test**

Add a test asserting the agent directory contains `main.py`, `deck.csv`, and `cg/__init__.py`.

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_local_battle.py::test_crustle_kangaskhan_submission_package_contains_required_files -v`
Expected: FAIL until the package is aligned.

**Step 3: Write minimal implementation**

Copy the required `cg` package and ensure the directory matches the sample submission contract.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_local_battle.py::test_crustle_kangaskhan_submission_package_contains_required_files -v`
Expected: PASS.

### Task 6: Train baseline and PPO checkpoints, then verify win rate

**Files:**
- Modify: `D:\workspace\ptcg\agents\crustle_mega_kangaskhan_rule_rl_p1\training_metadata.json`
- Create: `D:\workspace\ptcg\agents\crustle_mega_kangaskhan_rule_rl_p1\model_latest.pth`
- Create: `D:\workspace\ptcg\agents\crustle_mega_kangaskhan_rule_rl_p1\eval_report.json`

**Step 1: Write the failing test**

Add tests that metadata and evaluation report exist and reference `mega_lucario_beginner` and `dragapult_rule_based`.

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_local_battle.py -k crustle_kangaskhan_report -v`
Expected: FAIL because no trained artifacts exist yet.

**Step 3: Write minimal implementation**

Run baseline evaluation, run distillation plus PPO training, select the best stable checkpoint, and write the final metadata and evaluation report.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_local_battle.py -k crustle_kangaskhan_report -v`
Expected: PASS.

### Task 7: Run final verification

**Files:**
- Verify only

**Step 1: Run focused tests**

Run: `pytest tests/test_local_battle.py -k crustle_kangaskhan -v`
Expected: PASS.

**Step 2: Run local battle smoke tests**

Run: `python -m battle_env.cli --agent-a crustle_mega_kangaskhan_rule_rl_p1 --agent-b mega_lucario_beginner --games 10 --swap-sides`
Expected: completes with no crashes.

Run: `python -m battle_env.cli --agent-a crustle_mega_kangaskhan_rule_rl_p1 --agent-b dragapult_rule_based --games 10 --swap-sides`
Expected: completes with no crashes.

**Step 3: Run deterministic evaluation**

Run the agent evaluation script against both named opponents and verify the final checkpoint is not worse than the pure rule-prior baseline.
