from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


def _relu(values: list[float]) -> list[float]:
    return [max(0.0, value) for value in values]


def _linear(weights: list[list[float]], bias: list[float], inputs: list[float]) -> list[float]:
    outputs: list[float] = []
    for row, b in zip(weights, bias):
        total = b
        for weight, value in zip(row, inputs):
            total += weight * value
        outputs.append(total)
    return outputs


@dataclass
class ExportedPolicy:
    obs_hidden_weights: list[list[float]]
    obs_hidden_bias: list[float]
    policy_hidden_weights: list[list[float]]
    policy_hidden_bias: list[float]
    output_weights: list[list[float]]
    output_bias: list[float]
    value_hidden_weights: list[list[float]]
    value_hidden_bias: list[float]
    value_output_weights: list[list[float]]
    value_output_bias: list[float]
    beta: float

    def obs_embed(self, observation_features: list[float]) -> list[float]:
        return _relu(_linear(self.obs_hidden_weights, self.obs_hidden_bias, observation_features))

    def score(self, observation_features: list[float], action_features: list[float], rule_logit: float) -> float:
        obs_hidden = self.obs_embed(observation_features)
        inputs = obs_hidden + action_features + [rule_logit]
        hidden = _relu(_linear(self.policy_hidden_weights, self.policy_hidden_bias, inputs))
        return _linear(self.output_weights, self.output_bias, hidden)[0]

    def value(self, observation_features: list[float]) -> float:
        obs_hidden = self.obs_embed(observation_features)
        value_hidden = _relu(_linear(self.value_hidden_weights, self.value_hidden_bias, obs_hidden))
        return _linear(self.value_output_weights, self.value_output_bias, value_hidden)[0]


_POLICY_CACHE: dict[str, tuple[int, ExportedPolicy | None]] = {}


def load_exported_policy(path: Path) -> ExportedPolicy | None:
    if not path.exists():
        return None
    resolved = str(path.resolve())
    mtime_ns = path.stat().st_mtime_ns
    cached = _POLICY_CACHE.get(resolved)
    if cached is not None and cached[0] == mtime_ns:
        return cached[1]
    payload = json.loads(path.read_text(encoding="utf-8"))
    if "obs_hidden_weights" not in payload:
        payload = {
            "obs_hidden_weights": payload["hidden_weights"],
            "obs_hidden_bias": payload["hidden_bias"],
            "policy_hidden_weights": payload["hidden_weights"],
            "policy_hidden_bias": payload["hidden_bias"],
            "output_weights": payload["output_weights"],
            "output_bias": payload["output_bias"],
            "value_hidden_weights": payload["hidden_weights"],
            "value_hidden_bias": payload["hidden_bias"],
            "value_output_weights": [[0.0] * len(payload["hidden_bias"])],
            "value_output_bias": [0.0],
            "beta": payload.get("beta", 0.0),
        }
    policy = ExportedPolicy(
        obs_hidden_weights=payload["obs_hidden_weights"],
        obs_hidden_bias=payload["obs_hidden_bias"],
        policy_hidden_weights=payload["policy_hidden_weights"],
        policy_hidden_bias=payload["policy_hidden_bias"],
        output_weights=payload["output_weights"],
        output_bias=payload["output_bias"],
        value_hidden_weights=payload["value_hidden_weights"],
        value_hidden_bias=payload["value_hidden_bias"],
        value_output_weights=payload["value_output_weights"],
        value_output_bias=payload["value_output_bias"],
        beta=float(payload.get("beta", 0.0)),
    )
    _POLICY_CACHE[resolved] = (mtime_ns, policy)
    return policy
