from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import torch

from model import create_model, load_deck_from_csv, mcts_agent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="RL MCTS sample inference worker.")
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--deck-path", type=Path, required=True)
    return parser.parse_args()


def emit(payload: dict):
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main():
    args = parse_args()
    deck = load_deck_from_csv(args.deck_path)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = create_model(device)
    state_dict = torch.load(args.model_path, map_location=device)
    model.load_state_dict(state_dict)
    model.eval()

    for line in sys.stdin:
        if not line:
            break
        payload = json.loads(line)
        command = payload.get("cmd")
        if command == "ping":
            emit({"status": "ready"})
        elif command == "shutdown":
            emit({"status": "bye"})
            break
        elif command == "select":
            selected, _ = mcts_agent(payload["obs"], deck, model)
            emit({"selected": selected})
        else:
            emit({"error": f"Unknown command: {command}"})


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        emit({"error": f"{type(exc).__name__}: {exc}"})
        raise
