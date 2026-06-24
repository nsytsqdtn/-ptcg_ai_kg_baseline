# Crustle Kang V2 Integration Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make `agents/crustle_mega_kangaskhan_rule_rl_p1_v2` pass dedicated regression tests, run cleanly in `battle_env`, and produce a trustworthy baseline before the later full v5 cleanup.

**Architecture:** Keep the current v2 `TurnPlan`-centered structure, use `deck_state.py` as a temporary adapter, and harden the integration points through v2-specific tests before changing behavior. Treat every bugfix as TDD: failing test first, then minimal production change, then verification in `battle_env`.

**Tech Stack:** Python, pytest, local `battle_env`, `cg` battle runtime

---

### Task 1: Add v2 test helpers and entrypoint coverage

**Files:**
- Modify: `tests/test_local_battle.py`

**Step 1: Write the failing test**

Add v2-specific helpers and tests for:
- module loading from `agents/crustle_mega_kangaskhan_rule_rl_p1_v2`
- `battle_env.agents.resolve_agent("crustle_mega_kangaskhan_rule_rl_p1_v2")`
- submission package files (`main.py`, `deck.csv`, `cg/__init__.py`)

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_local_battle.py -k "crustle_kangaskhan_v2 and entrypoint" -v`
Expected: FAIL because the helper/tests do not exist yet.

**Step 3: Write minimal implementation**

Generalize the existing crustle test helper so it can load either `p1` or `p1_v2` without duplicating the whole file.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_local_battle.py -k "crustle_kangaskhan_v2 and entrypoint" -v`
Expected: PASS

### Task 2: Add v2 battle-env smoke and rule-surface tests

**Files:**
- Modify: `tests/test_local_battle.py`

**Step 1: Write the failing test**

Add v2-specific tests for:
- `play_match("crustle_mega_kangaskhan_rule_rl_p1_v2", "...")` returns `status == "success"`
- `analyze_deck_state(...)` exposes `turn_plan`
- `build_turn_plan(...)` selects `survival_setup` and `finish` in simple controlled states

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_local_battle.py -k "crustle_kangaskhan_v2 and (play_match or turn_plan or deck_state)" -v`
Expected: FAIL with missing tests or behavior mismatch.

**Step 3: Write minimal implementation**

Only patch `agents/crustle_mega_kangaskhan_rule_rl_p1_v2` where the new tests expose integration gaps.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_local_battle.py -k "crustle_kangaskhan_v2 and (play_match or turn_plan or deck_state)" -v`
Expected: PASS

### Task 3: Add v2 context/inference regression tests

**Files:**
- Modify: `tests/test_local_battle.py`
- Modify: `agents/crustle_mega_kangaskhan_rule_rl_p1_v2/inference.py`
- Modify: `agents/crustle_mega_kangaskhan_rule_rl_p1_v2/context_chooser.py`

**Step 1: Write the failing test**

Add v2-specific tests for:
- emergency gate only filtering on main-action setup windows
- Hilda / Poffin / Ultra Ball / Petrel chooser behavior using the v2 module loader
- debug payload fields for v2 if absent

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_local_battle.py -k "crustle_kangaskhan_v2 and (context_chooser or inference or rule_debug)" -v`
Expected: FAIL where the v2 branch diverges from expected behavior.

**Step 3: Write minimal implementation**

Patch only the failing v2 chooser or inference code paths.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_local_battle.py -k "crustle_kangaskhan_v2 and (context_chooser or inference or rule_debug)" -v`
Expected: PASS

### Task 4: Run the full local v2 regression slice

**Files:**
- Modify: `tests/test_local_battle.py` if any new failures require helper cleanup

**Step 1: Run focused regression**

Run: `pytest tests/test_local_battle.py -k "crustle_kangaskhan_v2 or play_match_exposes_termination_reason" -v`
Expected: PASS

**Step 2: Fix only failing v2 issues**

Patch the smallest possible production code in `agents/crustle_mega_kangaskhan_rule_rl_p1_v2`.

**Step 3: Re-run regression**

Run: `pytest tests/test_local_battle.py -k "crustle_kangaskhan_v2 or play_match_exposes_termination_reason" -v`
Expected: PASS

### Task 5: Run live evaluation baseline for v2

**Files:**
- Read/append: `agents/crustle_mega_kangaskhan_rule_rl_p1_v2/compare_eval_history.jsonl`
- Read/write: `agents/crustle_mega_kangaskhan_rule_rl_p1_v2/eval_report.json`

**Step 1: Run live evaluation**

Run: `python agents\crustle_mega_kangaskhan_rule_rl_p1_v2\evaluate.py --games 50 --label v2_integration_baseline --progress-every 10`

**Step 2: Inspect outcomes**

Confirm:
- the run completes
- termination reasons are recorded
- results are appended to `compare_eval_history.jsonl`

**Step 3: If behavior is obviously broken, write the next failing test first**

Do not patch from eval output alone; encode the issue into `tests/test_local_battle.py` before changing production code.
