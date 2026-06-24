# Crustle Rule Prior Fix Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix the current rule-layer tactical bugs before any further RL work so the agent can preserve board presence, choose valid gust lines, protect key resources, and attach special energy correctly.

**Architecture:** Keep the current agent structure intact and make surgical fixes in `deck_state.py`, `rule_prior.py`, `selection_scorer.py`, and `observation_builder.py`. Add regression tests first for each broken behavior, then implement the minimum state fields and scoring changes needed to make those tests pass.

**Tech Stack:** Python, pytest, local battle harness

---

### Task 1: Add regression tests for hard rule-layer bugs

**Files:**
- Modify: `tests/test_local_battle.py`

**Step 1: Write failing tests**

Add focused tests for:
- `must_bench_basic` when only one Pokémon is in play
- `gust_for_win` requiring both my remaining prizes and a real KO line
- Ultra Ball discard scoring using the actual discard candidate under `SelectContext.DISCARD`
- Spiky Energy preferring the expected Active tank over a bench target

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_local_battle.py -k "must_bench_basic or gust_for_win_requires_ko or ultra_ball_discard_context or spiky_energy_active_target" -v`

Expected: FAIL on current rule logic

### Task 2: Add hard board-state fields and plan gating

**Files:**
- Modify: `agents/crustle_mega_kangaskhan_rule_rl_p1/deck_state.py`
- Modify: `agents/crustle_mega_kangaskhan_rule_rl_p1/observation_builder.py`

**Step 1: Implement minimum new state fields**

Add:
- `field_basic_count`
- `bench_basic_count`
- `empty_bench`
- `only_one_pokemon_in_play`
- `must_bench_basic`
- `active_under_ko_threat`
- `current_attack_damage`

**Step 2: Replace pure `max(plan_scores)` with explicit priority checks**

Use a fixed priority order so close-game and prevent-loss states beat setup heuristics.

**Step 3: Run targeted tests**

Run: `pytest tests/test_local_battle.py -k "must_bench_basic or deck_state" -v`

Expected: PASS for new state behavior

### Task 3: Fix rule prior action scoring

**Files:**
- Modify: `agents/crustle_mega_kangaskhan_rule_rl_p1/rule_prior.py`
- Modify: `agents/crustle_mega_kangaskhan_rule_rl_p1/selection_scorer.py`

**Step 1: Fix Ultra Ball discard context**

Score discard candidates only in `SelectContext.DISCARD`, using the selected card from hand instead of Ultra Ball itself.

**Step 2: Fix Spiky Energy targeting**

Only give the high tank score when attaching to the current Active target.

**Step 3: Fix gust scoring**

Require:
- `my_prizes_left`
- prize value of gust target
- estimated current attack damage high enough to KO the target

**Step 4: Add hard benching priority**

When `must_bench_basic` is true, strongly prioritize benchable basics and penalize off-plan non-bench plays.

**Step 5: Run targeted tests**

Run: `pytest tests/test_local_battle.py -k "must_bench_basic or gust_for_win_requires_ko or ultra_ball_discard_context or spiky_energy_active_target" -v`

Expected: PASS

### Task 4: Run focused regression suite and agent eval

**Files:**
- None required unless a test exposes another small fix

**Step 1: Run focused agent tests**

Run: `pytest tests/test_local_battle.py -k "crustle_kangaskhan or play_match_exposes_termination_reason" -v`

Expected: PASS

**Step 2: Run fresh 50-game eval**

Run the existing evaluation entrypoint for 50 games per opponent and append results to `agents/crustle_mega_kangaskhan_rule_rl_p1/compare_eval_history.jsonl`.

**Step 3: Compare termination reasons**

Confirm `no_active` drops materially versus the latest logged baseline before considering any further rule-layer refactor.
