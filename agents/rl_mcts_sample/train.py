from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import torch

from model import (
    TrainConfig,
    collect_opponent_samples,
    create_model,
    evaluate_model,
    load_named_opponent,
    load_deck_from_csv,
    save_checkpoint,
    train_epoch,
)


AGENT_DIR = Path(__file__).resolve().parent
DEFAULT_DECK_PATH = AGENT_DIR / "deck.csv"
DEFAULT_OUTPUT_DIR = AGENT_DIR / "out"
DEFAULT_MODEL_PATH = AGENT_DIR / "model_latest.pth"
DEFAULT_METADATA_PATH = AGENT_DIR / "training_metadata.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train the RL MCTS sample agent.")
    parser.add_argument("--deck-path", type=Path, default=DEFAULT_DECK_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--model-path", type=Path, default=DEFAULT_MODEL_PATH)
    parser.add_argument("--metadata-path", type=Path, default=DEFAULT_METADATA_PATH)
    parser.add_argument("--iterations", type=int, default=5)
    parser.add_argument("--evaluation-games", type=int, default=50)
    parser.add_argument("--self-play-games", type=int, default=100)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--learning-rate", type=float, default=3e-4)
    parser.add_argument("--lambda-value", type=float, default=0.9)
    parser.add_argument("--search-count", type=int, default=10)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--opponents",
        nargs="+",
        default=["dragapult_rule_based", "mega_lucario_beginner"],
        help="Named local opponent agents used for training and evaluation.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    torch.manual_seed(args.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(args.seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    config = TrainConfig(
        iterations=args.iterations,
        evaluation_games=args.evaluation_games,
        self_play_games=args.self_play_games,
        batch_size=args.batch_size,
        learning_rate=args.learning_rate,
        lambda_value=args.lambda_value,
        search_count=args.search_count,
        opponents=tuple(args.opponents),
    )
    deck = load_deck_from_csv(args.deck_path)
    opponent_modules = {name: load_named_opponent(name) for name in config.opponents}
    model = create_model(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=config.learning_rate)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    history: list[dict] = []

    for counter in range(config.iterations):
        checkpoint_path = args.output_dir / f"model{counter}.pth"
        save_checkpoint(model, checkpoint_path)
        evaluations = {
            name: evaluate_model(model, deck, config.evaluation_games, config.search_count, opponent_module)
            for name, opponent_module in opponent_modules.items()
        }
        total_eval = sum(result["win"] + result["lose"] for result in evaluations.values())
        total_wins = sum(result["win"] for result in evaluations.values())
        win_rate = 0.0 if total_eval == 0 else total_wins / total_eval
        print(f"Iteration {counter}: evaluation={evaluations} win_rate={win_rate:.3f}", flush=True)

        sample_list = collect_opponent_samples(
            model,
            deck,
            config.self_play_games,
            config.search_count,
            config.lambda_value,
            list(opponent_modules.values()),
        )
        print(f"Iteration {counter}: collected_samples={len(sample_list)}", flush=True)
        print("Training Start.", flush=True)
        train_epoch(model, optimizer, sample_list, config.batch_size)
        print("Training Finish.", flush=True)

        history.append(
            {
                "iteration": counter,
                "checkpoint": str(checkpoint_path),
                "evaluations": evaluations,
                "win_rate": win_rate,
                "sample_count": len(sample_list),
            }
        )

    save_checkpoint(model, args.model_path)
    metadata = {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "device": str(device),
        "torch_version": torch.__version__,
        "config": {
            key: str(value) if isinstance(value, Path) else value for key, value in vars(args).items()
        },
        "history": history,
    }
    args.metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved final checkpoint to {args.model_path}", flush=True)


if __name__ == "__main__":
    main()
