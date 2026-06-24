# RL MCTS Submission-Compatible Design

**Date:** 2026-06-21

## Goal

Rework the RL/MCTS sample agent so that:

- training uses the existing rule-based agents as the main opponents
- the runtime entrypoint matches the official submission shape
- the same `main.py` entrypoint is used both by local battles and by the final submission package

## Constraints

- Do not keep silent fallback paths. Missing runtime dependencies, missing weights, or invalid package structure should fail loudly.
- The final candidate package must expose `agent(obs_dict)` from `main.py`.
- The candidate package must include `deck.csv` and `cg/`, matching the official submission layout expectations.
- Local training may still use the CUDA `sam2` environment, but the deployed package structure must not depend on the local `battle_env` runtime to define the submission entrypoint.

## Recommended Architecture

Keep `agents/rl_mcts_sample/` as the single source of truth, but reorganize it around submission shape:

- `main.py`
  The canonical inference entrypoint. This is the function local battles and final submission should both call.
- `deck.csv`
  Deck definition used by both training and deployment.
- `cg/`
  Submission-local SDK copy for package parity with the official format.
- `model.py`
  Shared value/policy model, feature encoding, MCTS, and training helpers.
- `train.py`
  CUDA training script.
- `infer_worker.py`
  Kept only if the local Python version still cannot directly host the training environment's torch build. This is a local runtime bridge, not the canonical entrypoint.
- `model_latest.pth`
  Current trained checkpoint.
- `training_metadata.json`
  Training outputs and evaluation summaries.

The important boundary is that `main.py` is the canonical public entrypoint. Any local bridging must sit behind it rather than replacing it.

## Training Strategy

The previous version overfit to random-opponent evaluation and was not representative of match strength against real candidates. Replace that with mixed-opponent training:

- primary opponents:
  - `dragapult_rule_based`
  - `mega_lucario_beginner`
- optional self-play remains allowed, but it is not the only source of games
- evaluation should report per-opponent results, not only a single aggregate random win rate

The training script should support:

- opponent list configuration
- opponent sampling across training games
- evaluation against named opponents
- metadata output that records results by opponent

## Runtime Strategy

Local battle execution should resolve `rl_mcts_sample` to `agents/rl_mcts_sample/main.py`, not to a separate development-only entrypoint. This guarantees that what is tested locally is the same interface that will be submitted.

If direct in-process torch loading is still impossible because of Python ABI mismatch, keep a worker subprocess internally, but only as an implementation detail behind `main.py`. There should be no separate public runtime path.

## Testing Strategy

Add tests for:

- resolving `rl_mcts_sample` to `main.py`
- importability of `agents/rl_mcts_sample/main.py`
- explicit failure when checkpoint files are missing
- training metadata includes per-opponent evaluation records
- local battle execution uses the submission-style entrypoint successfully

## Non-Goals

- no hidden runtime fallback to random actions
- no second independent submission directory
- no tournament infrastructure changes beyond what is needed for opponent-conditioned training
