# RL MCTS Sample Agent

This agent is the local engineering version of `sample_code/reinforcement-learning-and-mcts-sample-code.ipynb`.

Files:

- `agent.py`
  Inference-only battle entrypoint used by `battle_env`.
- `model.py`
  Shared model, feature encoding, and MCTS logic extracted from the sample notebook.
- `train.py`
  Scriptable local training entrypoint.
- `reinforcement-learning-and-mcts-sample-code.ipynb`
  Notebook copy kept for reference and reproducibility.
- `model_latest.pth`
  Latest trained checkpoint used by runtime inference.

Training command:

```powershell
conda run -n sam2 python agents/rl_mcts_sample/train.py
```

Battle command:

```powershell
python local_battle.py --agent-a rl_mcts_sample --agent-b mega_lucario_beginner
```
