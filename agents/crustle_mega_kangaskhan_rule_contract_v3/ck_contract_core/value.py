from __future__ import annotations


def estimate_state_value(observation_features: list[float]) -> float:
    if not observation_features:
        return 0.0
    return sum(observation_features) / float(len(observation_features))
