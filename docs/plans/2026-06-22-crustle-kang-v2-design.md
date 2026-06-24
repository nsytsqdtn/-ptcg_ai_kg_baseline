# Crustle Kang V2 Integration Design

Goal: stabilize `agents/crustle_mega_kangaskhan_rule_rl_p1_v2` against the real `battle_env` while preserving the current v2 structure, then prepare it for the later full v5 cleanup that removes the old compatibility layer.

Architecture:
- Keep the current `BoardSnapshot` / `TurnPlan` core in `turn_plan.py`, but treat `deck_state.py` as a temporary compatibility facade for the rest of the rule stack.
- Add v2-specific regression coverage for agent loading, battle-env execution, emergency gating, and context selection so the refactor can proceed under test.
- Fix only the integration gaps that stop `TurnPlan -> DeckState facade -> RulePrior/Inference -> ContextChooser -> battle_env` from behaving consistently; do not retrain or expand PPO in this phase.

Current Findings:
- `main.py` already runs pure rules (`use_policy=False`) and updates `DeckKnowledgeTracker`.
- `turn_plan.py` already contains the new `BoardSnapshot` and `TurnPlan` model aligned with the v5 direction.
- `deck_state.py` is currently a compatibility wrapper that maps `TurnPlan` back into legacy `DeckState` fields.
- `rule_prior.py` and `inference.py` still score through the old `DeckState` surface, so the new plan layer is only partially authoritative.
- `tests/test_local_battle.py` currently covers the old `p1` agent almost exclusively; `v2` does not yet have dedicated entrypoint, battle-env, or rule-behavior coverage.
- A direct `battle_env.runner.play_match(...)` smoke test confirms the v2 agent loads and runs, but behavior is not validated and still loses live games.

Phase 1 Scope:
- Add dedicated v2 loading and execution tests.
- Add v2 rule tests around the new plan layer where it already differs from `p1`.
- Fix any battle-env integration or context-selection bugs found by those tests.
- Run targeted live evaluations to confirm the v2 branch is at least behaviorally coherent before deeper cleanup.

Phase 2 Intent:
- After the v2 branch is stable under tests and battle-env, move fully toward the v5 md design by deleting legacy scoring pathways and shrinking the `DeckState` compatibility surface.

Non-goals for this phase:
- No PPO / distillation / checkpoint work.
- No decklist changes.
- No broad code cleanup outside `crustle_mega_kangaskhan_rule_rl_p1_v2` unless a shared test helper must be generalized.
