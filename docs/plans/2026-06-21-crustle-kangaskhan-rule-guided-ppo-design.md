# Crustle Kangaskhan Rule-Guided PPO Design

## Goal

Build a submission-compatible `crustle_mega_kangaskhan_rule_rl_p1` agent that uses a deck-specific rule prior plus trainable policy and value networks, trains only against `mega_lucario_beginner` and `dragapult_rule_based`, and defaults to deterministic safe inference in `main.py`.

## Runtime Shape

The agent directory will be the single source of truth for local battles and final submission. `main.py` will expose `my_deck` and `agent(obs_dict)`, read the local `deck.csv`, load a checkpoint, compute rule logits plus residual policy logits over legal actions only, and return deterministic argmax selections. If model loading or scoring fails, runtime falls back to pure rule-prior argmax and then to a safe legal-action heuristic.

## Decision Stack

The runtime pipeline is:

1. Normalize the simulator observation into legal action candidates.
2. Build a deck-state summary tuned for `Crustle / Mega Kangaskhan ex`.
3. Score every legal action with a rule prior.
4. Encode the observation and each legal action.
5. Compute residual policy logits and a scalar value estimate.
6. Combine `rule_logit + beta * policy_logit`.
7. Use sampling only during training rollouts; use argmax in evaluation and submission.

The rule prior is responsible for the large strategic shape:

- Establish `Dwebble -> Crustle` early.
- Put `Mega Kangaskhan ex` Active when draw or pressure matters.
- Prefer actions that create or preserve a live `Crustle` wall into opposing ex attackers.
- Value healing only when it changes the KO outcome.
- Reserve gust and disruption for prize swings, stall turns, or close-game conversions.

## RL Shape

The RL stack is intentionally small and win-rate-oriented:

- `ObservationBuilder`: visible-information feature extraction only.
- `ActionEncoder`: per-legal-action feature vectors, not a global action ID space.
- `PolicyNet`: MLP over observation embedding, action embedding, and rule features, producing a residual logit.
- `ValueNet`: MLP over observation embedding, producing `V(s)`.
- `TrajectoryBuffer`: transition storage for PPO.
- `RuleDistillation`: warm-start policy to imitate rule-prior action distributions before PPO.
- `PPOTrainer`: rollout, GAE, clipped policy loss, value loss, entropy bonus, and KL-to-rule penalty.

This keeps RL constrained. The policy can improve local ranking decisions without being allowed to abandon the rule prior too aggressively.

## Training Loop

Training uses only the named fixed opponents:

- `mega_lucario_beginner`
- `dragapult_rule_based`

Each rollout game samples one opponent with equal probability and alternates seat position over time. The trainer first generates rule-prior trajectories for distillation, then runs PPO updates, then runs deterministic evaluation per opponent. Checkpoints are tracked for overall win rate and matchup stability. Any candidate that introduces illegal moves, crashes, or large regression against one matchup is rejected.

## Submission Layout

The final agent directory will contain:

- `main.py`
- `deck.csv`
- runtime modules used by `main.py`
- training and evaluation scripts
- saved checkpoints and metadata
- copied `cg/` folder for submission compatibility

The directory will be locally runnable through `battle_env` and structurally compatible with the official sample submission bundle.

## Verification Strategy

Success is not defined by training reward. The acceptance gate is:

- submission-style `main.py` import works
- local battle runner resolves the new agent directory
- pure rule-prior baseline runs cleanly
- PPO checkpoints run deterministically with zero illegal actions and zero crashes
- PPO beats or at least matches the pure rule-prior baseline overall, without collapsing one matchup

## Scope Controls

This phase intentionally excludes public replay mining, MCTS, large opponent pools, and meta-level deck adaptation. The only objective is a stable, stronger-than-baseline rule-guided PPO agent for the fixed deck and the two fixed rule-based opponents.
