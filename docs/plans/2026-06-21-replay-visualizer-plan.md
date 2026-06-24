# Replay Visualizer Replacement Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the current replay renderer with the notebook-based visualizer and make local battle records use a Kaggle-like `steps` replay structure.

**Architecture:** Extract the notebook replay viewer into a standalone Python module that renders HTML from `steps`. Update `scripts/local_battle.py` so local matches emit `steps[]` as the primary replay payload and invoke the new renderer for `--replay-file`.

**Tech Stack:** Python, pytest, embedded HTML/CSS/JS, local battle harness

---

### Task 1: Lock The Target Record Shape

**Files:**
- Modify: `D:\workspace\ptcg\tests\test_local_battle.py`
- Create: `D:\workspace\ptcg\tests\test_replay_visualizer.py`

**Step 1: Write the failing test**

Add tests asserting:
- local record JSON has top-level `steps`
- `steps` is a non-empty list
- each step contains viewer-compatible replay data
- replay HTML can be generated from a saved local record

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_local_battle.py tests/test_replay_visualizer.py -q`
Expected: FAIL because the new module and new record shape do not exist yet

**Step 3: Write minimal implementation**

Only add the smallest helpers or stubs needed to let tests reach the real failure point.

**Step 4: Run test to verify the failure is now specific**

Run: `pytest tests/test_local_battle.py tests/test_replay_visualizer.py -q`
Expected: FAIL on missing conversion/render behavior, not import errors

### Task 2: Extract The Notebook Replay Visualizer

**Files:**
- Create: `D:\workspace\ptcg\replay_visualizer.py`
- Reference: `D:\workspace\ptcg\sample_code\battle-replay-visualizer-visualizer.ipynb`
- Test: `D:\workspace\ptcg\tests\test_replay_visualizer.py`

**Step 1: Write the failing test**

Add a test that imports `replay_visualizer.py`, passes a minimal `steps` list, writes HTML, and checks for notebook viewer markers.

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_replay_visualizer.py::test_generate_html_from_steps -q`
Expected: FAIL because `replay_visualizer.py` does not exist or lacks `generate_html`

**Step 3: Write minimal implementation**

Extract only the reusable viewer pieces:
- card metadata loaders
- embedded CSS/HTML/JS
- `generate_html(steps, out_html, ...)`
- record wrapper helpers needed by local battle integration

Do not copy notebook runtime cells like `battle_start`, `display`, or upload UI.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_replay_visualizer.py::test_generate_html_from_steps -q`
Expected: PASS

### Task 3: Emit `steps[]` From Local Battles

**Files:**
- Modify: `D:\workspace\ptcg\scripts\local_battle.py`
- Test: `D:\workspace\ptcg\tests\test_local_battle.py`

**Step 1: Write the failing test**

Add tests asserting `play_match()` returns:
- top-level `steps`
- each step contains viewer payload compatible with the new renderer
- summary/log behavior is still present

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_local_battle.py::test_play_match_returns_steps_payload -q`
Expected: FAIL because `play_match()` still returns `history`

**Step 3: Write minimal implementation**

Update match execution so each decision step appends a new `steps[]` entry containing:
- replay `visualize` snapshot compatible with notebook viewer
- local debug extras such as selected options and readable metadata

Preserve top-level metadata and keep any legacy fields only if required by existing tests during transition.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_local_battle.py::test_play_match_returns_steps_payload -q`
Expected: PASS

### Task 4: Replace Replay HTML Generation

**Files:**
- Modify: `D:\workspace\ptcg\scripts\local_battle.py`
- Remove or stop using: `D:\workspace\ptcg\battle_viewer.py`
- Test: `D:\workspace\ptcg\tests\test_local_battle.py`

**Step 1: Write the failing test**

Add or update the replay HTML test so it checks the new notebook visualizer output markers rather than the old custom viewer markers.

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_local_battle.py::test_save_replay_html_writes_visualizer_page -q`
Expected: FAIL because `save_replay_html()` still uses the old renderer

**Step 3: Write minimal implementation**

Change `save_replay_html()` to call `replay_visualizer.py`.
Ensure it reads the new local record/steps format directly.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_local_battle.py::test_save_replay_html_writes_visualizer_page -q`
Expected: PASS

### Task 5: Clean Up Legacy Paths

**Files:**
- Modify: `D:\workspace\ptcg\README.md`
- Delete or deprecate: `D:\workspace\ptcg\battle_viewer.py`
- Test: `D:\workspace\ptcg\tests\test_local_battle.py`, `D:\workspace\ptcg\tests\test_replay_visualizer.py`

**Step 1: Write the failing test**

If needed, add a narrow test confirming the replay writer imports the new module path and not `battle_viewer`.

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_replay_visualizer.py -q`
Expected: FAIL until imports and docs are aligned

**Step 3: Write minimal implementation**

- Remove or stop referencing `battle_viewer.py`
- Update README examples and output descriptions
- Keep the CLI flags unchanged unless a rename is strictly necessary

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_local_battle.py tests/test_replay_visualizer.py -q`
Expected: PASS

### Task 6: End-To-End Verification

**Files:**
- Verify: `D:\workspace\ptcg\scripts\local_battle.py`
- Verify output: `D:\workspace\ptcg\battle_records\*.json`, `D:\workspace\ptcg\battle_records\*.replay.html`

**Step 1: Run a real local battle**

Run:

```powershell
python scripts\local_battle.py --agent-a dragapult_rule_based --agent-b mega_lucario_beginner --record-file battle_records\sample_match.json --replay-file battle_records\sample_match.replay.html
```

Expected:
- command exits successfully
- record JSON includes `steps[]`
- replay HTML is written

**Step 2: Run targeted tests**

Run:

```powershell
pytest tests/test_local_battle.py tests/test_replay_visualizer.py -q
```

Expected: PASS

**Step 3: Run syntax verification**

Run:

```powershell
python -m py_compile replay_visualizer.py scripts\local_battle.py
```

Expected: no syntax errors
