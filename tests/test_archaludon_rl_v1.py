import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    root_str = str(ROOT)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
    agent_dir = str(path.parent)
    if agent_dir not in sys.path:
        sys.path.insert(0, agent_dir)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _fake_card(card_id: int, *, hp: int = 100, max_hp: int = 100, energies=None, tools=None):
    return SimpleNamespace(
        id=card_id,
        hp=hp,
        maxHp=max_hp,
        energies=list(energies or []),
        energyCards=[],
        tools=list(tools or []),
        preEvolution=[],
    )


def _fake_obs(module, *, options, hand=None, active=None, bench=None, context=None, min_count=1, max_count=1):
    current = SimpleNamespace(
        yourIndex=0,
        supporterPlayed=False,
        energyAttached=False,
        retreated=False,
        firstPlayer=0,
        turn=3,
        turnActionCount=1,
        result=-1,
        stadium=[],
        looking=[],
        players=[
            SimpleNamespace(
                hand=list(hand or []),
                active=[active] if active else [],
                bench=list(bench or []),
                discard=[],
                deckCount=34,
                prize=[1, 2, 3, 4],
                handCount=len(hand or []),
            ),
            SimpleNamespace(
                hand=[],
                active=[_fake_card(module.DURALUDON, hp=130, max_hp=130)],
                bench=[],
                discard=[],
                deckCount=35,
                prize=[1, 2, 3, 4],
                handCount=5,
            ),
        ],
    )
    return SimpleNamespace(
        current=current,
        logs=[],
        select=SimpleNamespace(
            option=list(options),
            context=context if context is not None else module.SelectContext.MAIN,
            minCount=min_count,
            maxCount=max_count,
            deck=[],
            effect=None,
            contextCard=None,
        ),
    )


def test_zero_weight_residual_keeps_rule_order(monkeypatch):
    module = load_module("archaludon_rl_v1_zero_weight", ROOT / "agents" / "archaludon_rl_v1" / "main.py")
    options = [SimpleNamespace(type=module.OptionType.END), SimpleNamespace(type=module.OptionType.END)]
    obs = _fake_obs(module, options=options)

    scores = {id(options[0]): (1000, "low"), id(options[1]): (2000, "high")}
    monkeypatch.setattr(module, "score_option", lambda _obs, opt: scores[id(opt)])
    monkeypatch.setattr(module, "rl_model_forward", lambda _features: 0.0)

    assert module.choose_options(obs) == [1]
    debug = module.get_last_decision_debug()
    assert debug["options"][0]["delta"] == 0.0
    assert debug["options"][1]["final_score"] == 2000.0


def test_hard_guard_keeps_forbidden_rule_score_down(monkeypatch):
    module = load_module("archaludon_rl_v1_hard_guard", ROOT / "agents" / "archaludon_rl_v1" / "main.py")
    bad = SimpleNamespace(type=module.OptionType.END)
    good = SimpleNamespace(type=module.OptionType.END)
    obs = _fake_obs(module, options=[bad, good])

    scores = {id(bad): (-10000, "forbidden"), id(good): (0, "ok")}
    monkeypatch.setattr(module, "score_option", lambda _obs, opt: scores[id(opt)])
    monkeypatch.setattr(module, "rl_model_forward", lambda _features: 1.0)

    final_score, rule_score, delta, reason = module.final_score_option(obs, bad)

    assert (final_score, rule_score, delta, reason) == (-10000.0, -10000.0, 0.0, "forbidden")
    assert module.choose_options(obs) == [1]


def test_manifest_uses_new_agent_name():
    manifest = json.loads((ROOT / "agents" / "archaludon_rl_v1" / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["name"] == "archaludon_rl_v1"


def test_choose_options_train_allows_empty_selection_when_min_count_zero(monkeypatch):
    module = load_module("archaludon_rl_v1_train_optional_empty", ROOT / "agents" / "archaludon_rl_v1" / "main.py")
    options = [SimpleNamespace(type=module.OptionType.END), SimpleNamespace(type=module.OptionType.END)]
    obs = _fake_obs(module, options=options, min_count=0, max_count=1)
    monkeypatch.setattr(module, "score_options_with_debug", lambda _obs: (
        [(-10.0, 0, -10.0, 0.0, "neg", [0.0] * module.FEATURE_DIM), (-20.0, 1, -20.0, 0.0, "neg2", [0.0] * module.FEATURE_DIM)],
        [{"option_index": 0, "rule_score": -10.0, "final_score": -10.0, "delta": 0.0, "reason": "neg", "feature_dim": module.FEATURE_DIM},
         {"option_index": 1, "rule_score": -20.0, "final_score": -20.0, "delta": 0.0, "reason": "neg2", "feature_dim": module.FEATURE_DIM}]
    ))
    monkeypatch.setattr(module, "_candidate_scored", lambda _obs, scored: scored)
    monkeypatch.setattr(module, "_softmax_sample", lambda scored, temperature: scored[0][1])

    assert module.choose_options_train(obs) == []


def test_option_target_uses_option_player_index_for_opponent_targets():
    module = load_module("archaludon_rl_v1_option_target_player_index", ROOT / "agents" / "archaludon_rl_v1" / "main.py")
    my_bench = _fake_card(module.DURALUDON)
    opp_bench = _fake_card(module.ARCHALUDON_EX)
    obs = _fake_obs(
        module,
        options=[SimpleNamespace(type=module.OptionType.CARD)],
        bench=[my_bench],
    )
    obs.current.players[1].bench = [opp_bench]
    opt = SimpleNamespace(inPlayArea=module.AreaType.BENCH, inPlayIndex=0, playerIndex=1)

    target = module.option_target(obs, opt)

    assert target.id == module.ARCHALUDON_EX


def test_option_target_falls_back_when_player_index_is_none():
    module = load_module("archaludon_rl_v1_option_target_none_player_index", ROOT / "agents" / "archaludon_rl_v1" / "main.py")
    my_bench = _fake_card(module.DURALUDON)
    obs = _fake_obs(
        module,
        options=[SimpleNamespace(type=module.OptionType.CARD)],
        bench=[my_bench],
    )
    opt = SimpleNamespace(inPlayArea=module.AreaType.BENCH, inPlayIndex=0, playerIndex=None)

    target = module.option_target(obs, opt)

    assert target.id == module.DURALUDON


def test_resource_context_delta_cannot_raise_score(monkeypatch):
    module = load_module("archaludon_rl_v1_resource_delta_guard", ROOT / "agents" / "archaludon_rl_v1" / "main.py")
    opt = SimpleNamespace(type=module.OptionType.CARD)
    obs = _fake_obs(module, options=[opt], context=module.SelectContext.TO_HAND)
    monkeypatch.setattr(module, "score_option", lambda _obs, _opt: (1000.0, "take Explorer"))
    monkeypatch.setattr(module, "extract_features", lambda *_args: [0.0] * module.FEATURE_DIM)
    monkeypatch.setattr(module, "rl_model_forward", lambda _features: 1.0)

    final_score, rule_score, delta, _reason = module.final_score_option(obs, opt)

    assert rule_score == 1000.0
    assert final_score == 1000.0
    assert delta == 0.0


def test_read_deck_csv_works_without___file__(monkeypatch, tmp_path):
    module = load_module("archaludon_rl_v1_no_file_deck", ROOT / "agents" / "archaludon_rl_v1" / "main.py")
    deck_path = tmp_path / "deck.csv"
    deck_path.write_text("1\n2\n3\n", encoding="utf-8")
    monkeypatch.setattr(module, "ROOT", None)
    monkeypatch.chdir(tmp_path)

    deck = module.read_deck_csv()

    assert deck == [1, 2, 3]
