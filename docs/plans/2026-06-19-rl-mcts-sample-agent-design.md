# RL MCTS Sample Agent Design

**Date:** 2026-06-19

## Goal

Turn the sample reinforcement-learning notebook into a real candidate agent that can be trained locally with CUDA and then used by the unified `battle_env` runtime for normal agent-vs-agent matches.

## Constraints

- Keep the original sample idea intact: transformer-like value/policy model plus MCTS search.
- Use a CUDA-enabled local PyTorch environment for training.
- Preserve a notebook copy for reference and reproducibility.
- Do not add a second battle runtime or a second agent interface.
- The deployed agent must do inference only. Training stays outside match execution.

## Architecture

Create a new candidate agent directory at `agents/rl_mcts_sample/` with the following files:

- `reinforcement-learning-and-mcts-sample-code.ipynb`
  A localized copy of the sample notebook with local import paths.
- `model.py`
  Shared model, feature encoding, MCTS, and action-selection code.
- `train.py`
  A script version of the notebook training loop that saves local checkpoints.
- `agent.py`
  The runtime inference entrypoint expected by `battle_env`.
- `deck.csv`
  The deck used by the sample agent.
- `model_latest.pth`
  The trained weight file used for inference.

## Training Strategy

Use the `sam2` conda environment because it already provides CUDA PyTorch on this machine:

- `torch 2.9.0+cu130`
- CUDA available
- GPU detected: `NVIDIA GeForce RTX 5070 Ti`

Training should remain faithful to the sample notebook:

- periodic evaluation against a random agent
- self-play data collection with MCTS
- supervised-style updates on value and policy targets
- checkpoint export after each outer loop

The main local change is replacing the Kaggle path bootstrap with imports that work against this repository's `cg` compatibility path.

## Deployment Strategy

The deployed candidate agent should:

- lazily load `model_latest.pth`
- keep the loaded model cached in-process
- run `mcts_agent(obs_dict, my_deck, model)`
- return only the selected action list required by the battle runtime

No training code should execute during matches.

## Testing Strategy

Add tests for:

- the new agent directory and required files
- importability of `agents/rl_mcts_sample/agent.py`
- clear failure behavior when weights are missing
- successful loading when a valid checkpoint is present

Then verify end-to-end by:

- training a local checkpoint with `conda run -n sam2`
- running a real match through `local_battle.py`
- confirming JSON, logs, metrics, and replay output still work

