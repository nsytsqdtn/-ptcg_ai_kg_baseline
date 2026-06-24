from pathlib import Path
import sys


AGENT_DIR = Path(__file__).resolve().parent
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))

import main as _main


MODEL_PATH = AGENT_DIR / "model_latest.pth"
_MODEL_CACHE = _main._MODEL_CACHE
my_deck = _main.my_deck


def load_model():
    global _MODEL_CACHE
    _main.MODEL_PATH = MODEL_PATH
    _main._MODEL_CACHE = _MODEL_CACHE
    model = _main.load_model()
    _MODEL_CACHE = _main._MODEL_CACHE
    return model


def agent(obs_dict: dict) -> list[int]:
    return _main.agent(obs_dict)
