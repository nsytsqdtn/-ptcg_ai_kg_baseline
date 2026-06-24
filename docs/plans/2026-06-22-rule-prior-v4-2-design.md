# RulePrior v4.2 Design

Goal: implement the `rule_prior_v4_2_integrated_fix_handoff.md` requirements in the existing Crustle / Mega Kangaskhan ex rule agent without touching PPO logic.

Architecture:
- Add persistent deck knowledge so rule decisions can distinguish "target unknown" from "target confirmed absent".
- Move survival and finish decisions from soft score competition into explicit gating in inference.
- Route multi-step selections through context-specific choosers instead of generic top-N ranking.

Scope:
- `deck_knowledge.py` for full-deck search knowledge and prize inference.
- `deck_state.py` for expanded `must_bench_basic`, `direct_win_available`, and related plan inputs.
- `inference.py` and `main.py` for emergency filtering and context-aware selection dispatch.
- `selection_scorer.py` / `rule_prior.py` / `line_evaluator.py` for deck-aware scoring and Ascension constraints.
- `tests/test_local_battle.py` for regression coverage before each implementation slice.

Non-goals:
- No PPO retraining changes.
- No policy export or checkpoint selection changes.
- No decklist changes.
