# Local Battle Harness Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extract two official sample notebook agents into standalone folders and add a local Windows battle harness that runs them against each other with the provided `cg` SDK.

**Architecture:** Keep both agents as close as possible to the notebook implementations to avoid behavior drift. Add a thin local harness that loads each agent from its own folder, reads its deck, drives `battle_start` and `battle_select`, and reports the result of a completed match.

**Tech Stack:** Python 3, `pytest`, official `sample_submission/cg` ctypes SDK

---

### Task 1: Define target layout and red tests

**Files:**
- Create: `tests/test_local_battle.py`
- Create: `agents/`
- Create: `scripts/`

**Step 1: Write the failing test**

Add tests that expect:
- `agents/dragapult_rule_based/agent.py` and `agents/mega_lucario_beginner/agent.py` to exist
- each agent module to expose `agent()` and `my_deck`
- a local harness module to expose `play_match()`

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_local_battle.py -v`
Expected: FAIL because the extracted agent files and harness do not exist yet.

### Task 2: Extract sample agents into per-agent folders

**Files:**
- Create: `agents/dragapult_rule_based/agent.py`
- Create: `agents/dragapult_rule_based/deck.csv`
- Create: `agents/dragapult_rule_based/README.md`
- Create: `agents/mega_lucario_beginner/agent.py`
- Create: `agents/mega_lucario_beginner/deck.csv`
- Create: `agents/mega_lucario_beginner/README.md`

**Step 1: Copy notebook agent logic with minimal path adaptation**

Keep the notebook logic intact and only change deck file resolution so each module can read its sibling `deck.csv`.

**Step 2: Verify tests move forward**

Run: `pytest tests/test_local_battle.py::test_agent_modules_load_and_expose_decks -v`
Expected: PASS for module loading, with the harness test still failing.

### Task 3: Add local harness

**Files:**
- Create: `scripts/local_battle.py`

**Step 1: Write minimal implementation**

Implement:
- agent module loading by file path
- deck extraction from `my_deck`
- match loop using `battle_start`, `battle_select`, `battle_finish`
- metadata reporting for winner, turns, and step count

**Step 2: Verify full harness behavior**

Run: `pytest tests/test_local_battle.py::test_play_match_completes_between_sample_agents -v`
Expected: PASS with a completed battle and a valid winner.

### Task 4: End-to-end verification

**Files:**
- Reuse: `tests/test_local_battle.py`
- Reuse: `scripts/local_battle.py`

**Step 1: Run the focused test suite**

Run: `pytest tests/test_local_battle.py -v`
Expected: PASS

**Step 2: Run the harness directly**

Run: `python scripts/local_battle.py`
Expected: prints both agent names and a completed match summary.
