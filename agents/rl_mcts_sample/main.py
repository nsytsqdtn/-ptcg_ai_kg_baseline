from __future__ import annotations

import atexit
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


AGENT_DIR = Path(__file__).resolve().parent
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))

MODEL_PATH = AGENT_DIR / "model_latest.pth"
DECK_PATH = AGENT_DIR / "deck.csv"
_MODEL_CACHE = None


def _candidate_env_roots() -> list[Path]:
    return [
        Path(sys.prefix) / "envs" / "sam2",
        Path("D:/software/anaconda/envs/sam2"),
    ]


def _resolve_worker_python() -> Path:
    for env_root in _candidate_env_roots():
        python_exe = env_root / "python.exe"
        if python_exe.exists():
            return python_exe
    raise FileNotFoundError("Could not find python.exe for the sam2 environment.")


@dataclass
class WorkerClient:
    process: subprocess.Popen

    def request(self, payload: dict) -> dict:
        assert self.process.stdin is not None
        assert self.process.stdout is not None
        self.process.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
        self.process.stdin.flush()
        response_line = self.process.stdout.readline()
        if not response_line:
            stderr_text = ""
            if self.process.stderr is not None:
                stderr_text = self.process.stderr.read()
            raise RuntimeError(f"RL worker exited unexpectedly. {stderr_text}".strip())
        response = json.loads(response_line)
        if "error" in response:
            raise RuntimeError(response["error"])
        return response

    def close(self):
        if self.process.poll() is not None:
            return
        try:
            self.request({"cmd": "shutdown"})
        except Exception:
            self.process.kill()
        self.process.wait(timeout=5)


my_deck = [int(line.strip()) for line in DECK_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_model():
    global _MODEL_CACHE
    if _MODEL_CACHE is not None:
        return _MODEL_CACHE
    if not MODEL_PATH.exists():
        raise FileNotFoundError(f"Missing RL MCTS checkpoint: {MODEL_PATH}")
    worker_path = AGENT_DIR / "infer_worker.py"
    python_exe = _resolve_worker_python()
    process = subprocess.Popen(
        [str(python_exe), str(worker_path), "--model-path", str(MODEL_PATH), "--deck-path", str(DECK_PATH)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        bufsize=1,
        cwd=str(AGENT_DIR),
    )
    client = WorkerClient(process)
    ready = client.request({"cmd": "ping"})
    if ready.get("status") != "ready":
        client.close()
        raise RuntimeError(f"RL worker failed to initialize: {ready}")
    atexit.register(client.close)
    _MODEL_CACHE = client
    return _MODEL_CACHE


def agent(obs_dict: dict) -> list[int]:
    if obs_dict.get("select") is None:
        return my_deck
    worker = load_model()
    return worker.request({"cmd": "select", "obs": obs_dict})["selected"]
