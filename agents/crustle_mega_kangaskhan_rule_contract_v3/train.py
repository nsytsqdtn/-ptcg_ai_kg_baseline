from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


AGENT_DIR = Path(__file__).resolve().parent
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))
MODEL_EXPORT_PATH = AGENT_DIR / "model_export.json"
BASELINE_EXPORT_PATH = AGENT_DIR / "baseline_model_export.json"
DISTILLED_EXPORT_PATH = AGENT_DIR / "distilled_model_export.json"
CHECKPOINT_DIR = AGENT_DIR / "checkpoints"
DISTILL_DATASET_PATH = AGENT_DIR / "distill_dataset.json"
ROLLOUT_DATASET_PATH = AGENT_DIR / "rollout_dataset.json"
EVAL_REPORT_PATH = AGENT_DIR / "eval_report.json"
METADATA_PATH = AGENT_DIR / "training_metadata.json"
TRAINING_METRICS_PATH = AGENT_DIR / "training_metrics.json"
SAM2_PYTHON = Path("D:/software/anaconda/envs/sam2/python.exe")
from action_encoder import ACTION_FEATURE_NAMES
from observation_builder import OBSERVATION_FEATURE_NAMES


OBS_DIM = len(OBSERVATION_FEATURE_NAMES)
ACTION_DIM = len(ACTION_FEATURE_NAMES)


def parse_args():
    parser = argparse.ArgumentParser(description="Train a rule-guided PPO policy for crustle kangaskhan.")
    parser.add_argument("--distill-games", type=int, default=80)
    parser.add_argument("--rollout-games", type=int, default=40)
    parser.add_argument("--eval-games", type=int, default=50)
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--temperature", type=float, default=1.0)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--beta", type=float, default=0.2)
    parser.add_argument("--distill-epochs", type=int, default=10)
    parser.add_argument("--ppo-epochs", type=int, default=4)
    parser.add_argument("--gamma", type=float, default=0.99)
    parser.add_argument("--gae-lambda", type=float, default=0.95)
    parser.add_argument("--clip-range", type=float, default=0.2)
    parser.add_argument("--value-coef", type=float, default=0.5)
    parser.add_argument("--entropy-coef", type=float, default=0.01)
    parser.add_argument("--kl-rule-coef", type=float, default=0.02)
    parser.add_argument("--batch-size", type=int, default=64)
    return parser.parse_args()


def _run(command: list[str]):
    subprocess.run(command, cwd=str(AGENT_DIR.parents[1]), check=True)


def _log(message: str):
    print(message, flush=True)


def _evaluate_current(eval_games: int, label: str) -> dict:
    sys.path.insert(0, str(AGENT_DIR.parents[1]))
    from evaluate import run_evaluation

    return run_evaluation(eval_games, label, EVAL_REPORT_PATH)["matchups"]


def _format_matchups(matchups: dict) -> str:
    parts = []
    for opponent, result in matchups.items():
        parts.append(f"{opponent}={result['wins']}/{result['games']} ({result['win_rate']:.3f})")
    return ", ".join(parts)


def _total_wins(matchups: dict) -> int:
    return sum(item["wins"] for item in matchups.values())


def _min_win_rate(matchups: dict) -> float:
    return min(item["win_rate"] for item in matchups.values())


def _copy(path_from: Path, path_to: Path):
    path_to.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(path_from, path_to)


def _collect_dataset(mode: str, output: Path, games: int, args):
    _run(
        [
            sys.executable,
            str(AGENT_DIR / "collect_dataset.py"),
            "--output",
            str(output),
            "--games",
            str(games),
            "--seed",
            str(args.seed),
            "--temperature",
            str(args.temperature),
            "--top-k",
            str(args.top_k),
            "--gamma",
            str(args.gamma),
            "--gae-lambda",
            str(args.gae_lambda),
            "--mode",
            mode,
        ]
    )


def _train_model(
    mode: str,
    dataset: Path,
    output: Path,
    metrics_output: Path,
    epochs: int,
    args,
    init_model: Path | None = None,
):
    command = [
        str(SAM2_PYTHON),
        str(AGENT_DIR / "trainer_torch.py"),
        "--dataset",
        str(dataset),
        "--output",
        str(output),
        "--metrics-output",
        str(metrics_output),
        "--mode",
        mode,
        "--epochs",
        str(epochs),
        "--beta",
        str(args.beta),
        "--learning-rate",
        "0.0003",
        "--clip-range",
        str(args.clip_range),
        "--value-coef",
        str(args.value_coef),
        "--entropy-coef",
        str(args.entropy_coef),
        "--kl-rule-coef",
        str(args.kl_rule_coef),
        "--kl-rule-final-coef",
        str(args.kl_rule_coef if mode == "distill" else max(0.005, args.kl_rule_coef * 0.25)),
        "--batch-size",
        str(args.batch_size),
    ]
    if init_model is not None:
        command.extend(["--init-model", str(init_model)])
    _run(command)


def main():
    args = parse_args()
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    _log(
        f"train_start distill_games={args.distill_games} rollout_games={args.rollout_games} "
        f"eval_games={args.eval_games} iterations={args.iterations} beta={args.beta} batch_size={args.batch_size}"
    )

    baseline_export = {
        "obs_hidden_weights": [[0.0] * OBS_DIM for _ in range(64)],
        "obs_hidden_bias": [0.0] * 64,
        "policy_hidden_weights": [[0.0] * (64 + ACTION_DIM + 1) for _ in range(64)],
        "policy_hidden_bias": [0.0] * 64,
        "output_weights": [[0.0] * 64],
        "output_bias": [0.0],
        "value_hidden_weights": [[0.0] * 64 for _ in range(64)],
        "value_hidden_bias": [0.0] * 64,
        "value_output_weights": [[0.0] * 64],
        "value_output_bias": [0.0],
        "beta": 0.0,
    }
    BASELINE_EXPORT_PATH.write_text(json.dumps(baseline_export), encoding="utf-8")
    _copy(BASELINE_EXPORT_PATH, MODEL_EXPORT_PATH)
    _log("stage=baseline_eval status=start")
    baseline_matchups = _evaluate_current(args.eval_games, "baseline")
    _log(f"stage=baseline_eval status=done { _format_matchups(baseline_matchups) }")

    _log("stage=distill_dataset status=start")
    _collect_dataset("distill", DISTILL_DATASET_PATH, args.distill_games, args)
    _log("stage=distill_dataset status=done")
    distill_metrics_path = CHECKPOINT_DIR / "distill_metrics.json"
    _log("stage=distill_train status=start")
    _train_model(
        "distill",
        DISTILL_DATASET_PATH,
        DISTILLED_EXPORT_PATH,
        distill_metrics_path,
        args.distill_epochs,
        args,
    )
    _log("stage=distill_train status=done")
    _copy(DISTILLED_EXPORT_PATH, MODEL_EXPORT_PATH)
    _log("stage=distill_eval status=start")
    distilled_matchups = _evaluate_current(args.eval_games, "distill")
    _log(f"stage=distill_eval status=done { _format_matchups(distilled_matchups) }")

    history: list[dict] = []
    best_choice = {
        "name": "baseline",
        "path": BASELINE_EXPORT_PATH,
        "matchups": baseline_matchups,
    }
    best_overall_path = CHECKPOINT_DIR / "best_overall.json"
    best_vs_lucario_path = CHECKPOINT_DIR / "best_vs_lucario.json"
    best_vs_dragapult_path = CHECKPOINT_DIR / "best_vs_dragapult.json"
    most_stable_path = CHECKPOINT_DIR / "most_stable.json"
    latest_path = CHECKPOINT_DIR / "latest.json"
    _copy(BASELINE_EXPORT_PATH, best_overall_path)
    _copy(BASELINE_EXPORT_PATH, best_vs_lucario_path)
    _copy(BASELINE_EXPORT_PATH, best_vs_dragapult_path)
    _copy(BASELINE_EXPORT_PATH, most_stable_path)
    _copy(BASELINE_EXPORT_PATH, latest_path)

    best_lucario = baseline_matchups["mega_lucario_beginner"]["wins"]
    best_dragapult = baseline_matchups["dragapult_rule_based"]["wins"]
    best_stability = _min_win_rate(baseline_matchups)
    best_overall = _total_wins(baseline_matchups)

    current_export = DISTILLED_EXPORT_PATH
    for iteration in range(args.iterations):
        _copy(current_export, MODEL_EXPORT_PATH)
        _log(f"stage=ppo_dataset iteration={iteration + 1} status=start")
        _collect_dataset("ppo", ROLLOUT_DATASET_PATH, args.rollout_games, args)
        _log(f"stage=ppo_dataset iteration={iteration + 1} status=done")
        metrics_path = CHECKPOINT_DIR / f"ppo_metrics_iter_{iteration + 1}.json"
        checkpoint_path = CHECKPOINT_DIR / f"ppo_iter_{iteration + 1}.json"
        _log(f"stage=ppo_train iteration={iteration + 1} status=start")
        _train_model(
            "ppo",
            ROLLOUT_DATASET_PATH,
            checkpoint_path,
            metrics_path,
            args.ppo_epochs,
            args,
            init_model=current_export,
        )
        _log(f"stage=ppo_train iteration={iteration + 1} status=done")
        _copy(checkpoint_path, MODEL_EXPORT_PATH)
        _log(f"stage=ppo_eval iteration={iteration + 1} status=start")
        matchups = _evaluate_current(args.eval_games, f"ppo_iter_{iteration + 1}")
        _log(
            f"stage=ppo_eval iteration={iteration + 1} status=done "
            f"{_format_matchups(matchups)} overall={_total_wins(matchups)} stability={_min_win_rate(matchups):.3f}"
        )
        overall = _total_wins(matchups)
        stability = _min_win_rate(matchups)
        history.append(
            {
                "iteration": iteration + 1,
                "checkpoint": str(checkpoint_path),
                "metrics_path": str(metrics_path),
                "matchups": matchups,
                "overall_wins": overall,
                "stability": stability,
            }
        )
        _copy(checkpoint_path, latest_path)
        current_export = checkpoint_path

        if overall > best_overall:
            best_overall = overall
            _copy(checkpoint_path, best_overall_path)
            best_choice = {"name": f"ppo_iter_{iteration + 1}", "path": checkpoint_path, "matchups": matchups}
        if matchups["mega_lucario_beginner"]["wins"] > best_lucario:
            best_lucario = matchups["mega_lucario_beginner"]["wins"]
            _copy(checkpoint_path, best_vs_lucario_path)
        if matchups["dragapult_rule_based"]["wins"] > best_dragapult:
            best_dragapult = matchups["dragapult_rule_based"]["wins"]
            _copy(checkpoint_path, best_vs_dragapult_path)
        if stability > best_stability:
            best_stability = stability
            _copy(checkpoint_path, most_stable_path)

    _copy(best_choice["path"], MODEL_EXPORT_PATH)
    _log(f"stage=final_eval status=start selected={best_choice['name']}")
    final_matchups = _evaluate_current(args.eval_games, f"final_{best_choice['name']}")
    _log(f"stage=final_eval status=done { _format_matchups(final_matchups) }")

    training_metrics = {
        "distill_metrics": str(distill_metrics_path),
        "ppo_metrics": [str(CHECKPOINT_DIR / f"ppo_metrics_iter_{i + 1}.json") for i in range(args.iterations)],
    }
    TRAINING_METRICS_PATH.write_text(json.dumps(training_metrics, ensure_ascii=False, indent=2), encoding="utf-8")

    metadata = {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "config": {
            "distill_games": args.distill_games,
            "rollout_games": args.rollout_games,
            "eval_games": args.eval_games,
            "iterations": args.iterations,
            "seed": args.seed,
            "temperature": args.temperature,
            "top_k": args.top_k,
            "beta": args.beta,
            "distill_epochs": args.distill_epochs,
            "ppo_epochs": args.ppo_epochs,
            "gamma": args.gamma,
            "gae_lambda": args.gae_lambda,
            "clip_range": args.clip_range,
            "value_coef": args.value_coef,
            "entropy_coef": args.entropy_coef,
            "kl_rule_coef": args.kl_rule_coef,
            "batch_size": args.batch_size,
            "opponents": ["mega_lucario_beginner", "dragapult_rule_based"],
            "trainer_python": str(SAM2_PYTHON),
        },
        "artifacts": {
            "baseline_export": str(BASELINE_EXPORT_PATH),
            "distilled_export": str(DISTILLED_EXPORT_PATH),
            "trained_export": str(current_export),
            "active_export": str(MODEL_EXPORT_PATH),
            "best_overall": str(best_overall_path),
            "best_vs_lucario": str(best_vs_lucario_path),
            "best_vs_dragapult": str(best_vs_dragapult_path),
            "most_stable": str(most_stable_path),
            "latest": str(latest_path),
            "selected_export": best_choice["name"],
            "distill_dataset": str(DISTILL_DATASET_PATH),
            "rollout_dataset": str(ROLLOUT_DATASET_PATH),
        },
    }
    METADATA_PATH.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    _log(f"train_done selected={best_choice['name']} { _format_matchups(final_matchups) }")


if __name__ == "__main__":
    main()
