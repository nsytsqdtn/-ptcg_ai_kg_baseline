from pathlib import Path
import importlib.util
import sys


ROOT = Path(__file__).resolve().parents[1]
AGENT_DIR = ROOT / "agents" / "crustle_mega_kangaskhan_rule_compact_v1"


def load_module(name: str, path: Path):
    root_str = str(ROOT)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
    agent_str = str(AGENT_DIR)
    if agent_str not in sys.path:
        sys.path.insert(0, agent_str)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_compact_agent_counts_safe_action_fallback(monkeypatch):
    module = load_module("compact_v1_main_fallback", AGENT_DIR / "main.py")
    module.reset_fallback_count()

    calls = {"n": 0}

    def fake_to_observation_class(obs_dict):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom")
        return type("Obs", (), {"select": type("Select", (), {"option": [1], "minCount": 1, "maxCount": 1})()})()

    monkeypatch.setattr(module, "to_observation_class", fake_to_observation_class)
    monkeypatch.setattr(module, "choose_safe_action", lambda n: [0] if n > 0 else [])

    selected = module.agent({"select": {"option": [1], "minCount": 1, "maxCount": 1}})

    assert selected == [0]
    assert module.get_fallback_count() == 1


def test_play_match_reports_agent_fallback_counts():
    runner = load_module("battle_env_runner_fallback_counts", ROOT / "battle_env" / "runner.py")

    result = runner.play_match("crustle_mega_kangaskhan_rule_compact_v1", "mega_lucario_beginner", capture_details=False)

    assert "fallback_counts" in result
    assert result["fallback_counts"]["agent_a"] >= 0
    assert result["fallback_counts"]["agent_b"] >= 0
