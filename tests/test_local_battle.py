from pathlib import Path
import importlib.util
import json
from types import SimpleNamespace
import sys

ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    root_str = str(ROOT)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_root_local_battle_wrapper_loads():
    wrapper = load_module("root_local_battle_wrapper", ROOT / "local_battle.py")

    assert callable(wrapper.main)


def test_script_local_battle_wrapper_loads():
    wrapper = load_module("script_local_battle_wrapper", ROOT / "scripts" / "local_battle.py")

    assert callable(wrapper.main)


def test_battle_env_agent_resolver_supports_name_and_path():
    agents = load_module("battle_env_agents_module", ROOT / "battle_env" / "agents.py")
    path = agents.resolve_agent("dragapult_rule_based")

    assert path.name == "agent.py"
    assert path.parent.name == "dragapult_rule_based"

    resolved_again = agents.resolve_agent(path)
    assert resolved_again == path.resolve()


def test_play_match_completes_between_sample_agents():
    runner = load_module("battle_env_runner_match", ROOT / "battle_env" / "runner.py")

    result = runner.play_match("dragapult_rule_based", "mega_lucario_beginner")

    assert result["winner"] in (0, 1, 2)
    assert result["steps"] > 0
    assert result["turn"] >= 0
    assert result["history"]
    assert result["steps_data"]
    assert result["history"][0]["step"] == 1
    assert result["history"][0]["context_name"]
    assert result["history"][0]["select_type_name"]
    assert isinstance(result["history"][0]["available_options"], list)
    assert isinstance(result["history"][0]["selected_options"], list)
    assert result["steps_data"][0]["step"] == 1
    assert "current" in result["steps_data"][0]
    assert isinstance(result["steps_data"][0]["current"], dict)


def test_play_match_exposes_metrics_and_rl_fields():
    runner = load_module("battle_env_runner_metrics", ROOT / "battle_env" / "runner.py")

    result = runner.play_match("dragapult_rule_based", "mega_lucario_beginner")
    first_step = result["history"][0]

    assert "metrics" in result
    assert result["metrics"]["total_steps"] == result["steps"]
    assert "reward" in first_step
    assert "done" in first_step
    assert "delta_logs" in first_step
    assert isinstance(first_step["delta_logs"], list)


def test_play_match_exposes_termination_reason():
    runner = load_module("battle_env_runner_termination", ROOT / "battle_env" / "runner.py")

    result = runner.play_match("dragapult_rule_based", "mega_lucario_beginner", capture_details=False)

    assert "termination" in result
    assert "reason_key" in result["termination"]
    assert result["termination"]["reason_key"] in {
        "prize_out",
        "deck_out",
        "no_active",
        "card_effect",
        "draw",
        "unknown",
    }


def test_save_match_record_writes_json(tmp_path: Path):
    runner = load_module("battle_env_runner_save_record", ROOT / "battle_env" / "runner.py")

    result = runner.play_match("dragapult_rule_based", "mega_lucario_beginner")
    output_path = tmp_path / "match_record.json"
    runner.save_match_record(result, output_path)

    saved = json.loads(output_path.read_text(encoding="utf-8"))
    assert saved["winner"] == result["winner"]
    assert saved["history"]
    assert saved["steps"]
    assert saved["step_count"] == result["steps"]
    assert saved["metrics"]["total_steps"] == result["steps"]


def test_save_human_log_writes_text(tmp_path: Path):
    runner = load_module("battle_env_runner_human_log", ROOT / "battle_env" / "runner.py")

    result = runner.play_match("dragapult_rule_based", "mega_lucario_beginner")
    output_path = tmp_path / "match.log"
    runner.save_human_log(result, output_path)

    text = output_path.read_text(encoding="utf-8")
    assert "对战结果" in text
    assert "终局原因" in text
    assert "步骤" in text
    assert result["agent_a"] in text
    assert "动作选项" in text
    assert "事件详情" in text


def test_save_summary_log_writes_turn_summary(tmp_path: Path):
    runner = load_module("battle_env_runner_summary_log", ROOT / "battle_env" / "runner.py")

    result = runner.play_match("dragapult_rule_based", "mega_lucario_beginner")
    output_path = tmp_path / "match.summary.log"
    runner.save_summary_log(result, output_path)

    text = output_path.read_text(encoding="utf-8")
    assert "回合摘要" in text
    assert "终局原因" in text
    assert "第 1 回合" in text


def test_save_replay_html_writes_viewer_page(tmp_path: Path):
    runner = load_module("battle_env_runner_replay_html", ROOT / "battle_env" / "runner.py")

    result = runner.play_match("dragapult_rule_based", "mega_lucario_beginner")
    output_path = tmp_path / "match.replay.html"
    runner.save_replay_html(result, output_path)

    text = output_path.read_text(encoding="utf-8")
    assert "<title>PTCG Battle Replay v2</title>" in text
    assert 'id="eval-strip"' in text
    assert 'id="decision-list"' in text


def test_play_series_returns_aggregate_stats():
    runner = load_module("battle_env_runner_series", ROOT / "battle_env" / "runner.py")

    series = runner.play_series(
        "dragapult_rule_based",
        "mega_lucario_beginner",
        games=2,
        swap_sides=True,
    )

    assert series["games"] == 2
    assert len(series["results"]) == 2
    assert "wins_by_agent" in series


def test_play_match_captures_agent_exception(tmp_path: Path):
    runner = load_module("battle_env_runner_failure", ROOT / "battle_env" / "runner.py")

    bad_agent_dir = tmp_path / "bad_agent"
    bad_agent_dir.mkdir()
    source_deck = (ROOT / "agents" / "mega_lucario_beginner" / "deck.csv").read_text(encoding="utf-8")
    (bad_agent_dir / "deck.csv").write_text(source_deck, encoding="utf-8")
    (bad_agent_dir / "agent.py").write_text(
        "from pathlib import Path\n"
        "my_deck = [int(line) for line in Path(__file__).with_name('deck.csv').read_text(encoding='utf-8').splitlines() if line.strip()]\n"
        "def agent(obs_dict):\n"
        "    if obs_dict.get('select') is None:\n"
        "        return my_deck\n"
        "    raise RuntimeError('intentional test failure')\n",
        encoding="utf-8",
    )

    result = runner.play_match(
        bad_agent_dir / "agent.py",
        "mega_lucario_beginner",
    )

    assert result["status"] == "error"
    assert result["error"]["phase"] == "agent_action"
    assert "intentional test failure" in result["error"]["message"]


def test_rl_mcts_sample_agent_module_exposes_agent_and_deck():
    module = load_module("rl_mcts_sample_agent_module", ROOT / "agents" / "rl_mcts_sample" / "agent.py")

    assert callable(module.agent)
    assert isinstance(module.my_deck, list)
    assert module.my_deck


def test_rl_mcts_sample_agent_reports_missing_weights_cleanly(monkeypatch):
    module = load_module("rl_mcts_sample_agent_missing", ROOT / "agents" / "rl_mcts_sample" / "agent.py")
    monkeypatch.setattr(module, "MODEL_PATH", ROOT / "agents" / "rl_mcts_sample" / "missing_weights.pth")
    monkeypatch.setattr(module, "_MODEL_CACHE", None)

    try:
        module.load_model()
    except FileNotFoundError as exc:
        assert "missing_weights.pth" in str(exc)
    else:
        raise AssertionError("load_model() should raise FileNotFoundError when checkpoint is missing")


def test_rl_mcts_sample_training_files_exist():
    agent_dir = ROOT / "agents" / "rl_mcts_sample"

    assert (agent_dir / "train.py").exists()
    assert (agent_dir / "reinforcement-learning-and-mcts-sample-code.ipynb").exists()


def test_rl_mcts_sample_agent_can_load_checkpoint():
    module = load_module("rl_mcts_sample_agent_checkpoint", ROOT / "agents" / "rl_mcts_sample" / "agent.py")

    model = module.load_model()

    assert model is not None


def test_play_match_supports_rl_mcts_sample_agent():
    runner = load_module("battle_env_runner_rl_mcts_sample", ROOT / "battle_env" / "runner.py")

    result = runner.play_match("rl_mcts_sample", "mega_lucario_beginner")

    assert result["status"] == "success"


def test_rl_mcts_sample_submission_entrypoint_exists():
    module = load_module("rl_mcts_sample_submission_main", ROOT / "agents" / "rl_mcts_sample" / "main.py")

    assert callable(module.agent)
    assert isinstance(module.my_deck, list)
    assert module.my_deck


def test_battle_env_resolves_rl_mcts_sample_to_main_py():
    agents = load_module("battle_env_agents_submission_main", ROOT / "battle_env" / "agents.py")

    path = agents.resolve_agent("rl_mcts_sample")

    assert path.name == "main.py"


def test_rl_mcts_training_metadata_records_named_opponents():
    metadata = json.loads((ROOT / "agents" / "rl_mcts_sample" / "training_metadata.json").read_text(encoding="utf-8"))

    assert "opponents" in metadata["config"]
    assert metadata["config"]["opponents"]


def test_rl_mcts_sample_submission_package_contains_required_files():
    agent_dir = ROOT / "agents" / "rl_mcts_sample"

    assert (agent_dir / "main.py").exists()
    assert (agent_dir / "deck.csv").exists()
    assert (agent_dir / "cg" / "__init__.py").exists()


def test_play_match_supports_rl_mcts_sample_submission_entrypoint():
    runner = load_module("battle_env_runner_submission_rl_mcts", ROOT / "battle_env" / "runner.py")

    result = runner.play_match("rl_mcts_sample", "mega_lucario_beginner")

    assert result["status"] == "success"


def test_crustle_kangaskhan_submission_entrypoint_exists():
    module = load_module(
        "crustle_kangaskhan_submission_main",
        ROOT / "agents" / "crustle_mega_kangaskhan_rule_rl_p1" / "main.py",
    )

    assert callable(module.agent)
    assert isinstance(module.my_deck, list)
    assert len(module.my_deck) == 60


def test_crustle_kangaskhan_v2_submission_entrypoint_exists():
    module = load_module(
        "crustle_kangaskhan_v2_submission_main",
        ROOT / "agents" / "crustle_mega_kangaskhan_rule_rl_p1_v2" / "main.py",
    )

    assert callable(module.agent)
    assert isinstance(module.my_deck, list)
    assert len(module.my_deck) == 60


def test_battle_env_resolves_crustle_kangaskhan_to_main_py():
    agents = load_module("battle_env_agents_crustle_kangaskhan_main", ROOT / "battle_env" / "agents.py")

    path = agents.resolve_agent("crustle_mega_kangaskhan_rule_rl_p1")

    assert path.name == "main.py"


def test_battle_env_resolves_crustle_kangaskhan_v2_to_main_py():
    agents = load_module("battle_env_agents_crustle_kangaskhan_v2_main", ROOT / "battle_env" / "agents.py")

    path = agents.resolve_agent("crustle_mega_kangaskhan_rule_rl_p1_v2")

    assert path.name == "main.py"


def test_crustle_kangaskhan_runtime_helpers_load():
    module = load_module(
        "crustle_kangaskhan_runtime",
        ROOT / "agents" / "crustle_mega_kangaskhan_rule_rl_p1" / "runtime.py",
    )

    deck = module.load_deck_from_csv(ROOT / "agents" / "crustle_mega_kangaskhan_rule_rl_p1" / "deck.csv")
    rule_result = module.make_rule_prior_result(1.25, {"setup": 1.0}, ["setup_crustle"])

    assert len(deck) == 60
    assert isinstance(module.choose_safe_action(3), list)
    assert rule_result["total_logit"] == 1.25
    assert rule_result["breakdown"]["setup"] == 1.0
    assert rule_result["reason_tags"] == ["setup_crustle"]


def test_crustle_kangaskhan_v2_runtime_helpers_load():
    module = load_module(
        "crustle_kangaskhan_v2_runtime",
        ROOT / "agents" / "crustle_mega_kangaskhan_rule_rl_p1_v2" / "runtime.py",
    )

    deck = module.load_deck_from_csv(ROOT / "agents" / "crustle_mega_kangaskhan_rule_rl_p1_v2" / "deck.csv")
    rule_result = module.make_rule_prior_result(1.25, {"setup": 1.0}, ["setup_crustle"])

    assert len(deck) == 60
    assert isinstance(module.choose_safe_action(3), list)
    assert rule_result["total_logit"] == 1.25
    assert rule_result["breakdown"]["setup"] == 1.0
    assert rule_result["reason_tags"] == ["setup_crustle"]


def test_play_match_supports_crustle_kangaskhan_submission_entrypoint():
    runner = load_module("battle_env_runner_submission_crustle_kangaskhan", ROOT / "battle_env" / "runner.py")

    result = runner.play_match("crustle_mega_kangaskhan_rule_rl_p1", "mega_lucario_beginner")

    assert result["status"] == "success"


def test_play_match_supports_crustle_kangaskhan_v2_submission_entrypoint():
    runner = load_module("battle_env_runner_submission_crustle_kangaskhan_v2", ROOT / "battle_env" / "runner.py")

    result = runner.play_match("crustle_mega_kangaskhan_rule_rl_p1_v2", "mega_lucario_beginner")

    assert result["status"] == "success"


def test_crustle_kangaskhan_evaluate_history_appends_run(tmp_path: Path):
    module = load_module(
        "crustle_kangaskhan_evaluate_history_module",
        ROOT / "agents" / "crustle_mega_kangaskhan_rule_rl_p1" / "evaluate.py",
    )

    output_path = tmp_path / "compare_history.jsonl"
    run_record = {
        "run_at": "2026-06-22T00:00:00Z",
        "label": "baseline",
        "games_per_opponent": 2,
        "matchups": {
            "mega_lucario_beginner": {"wins": 1, "games": 2, "win_rate": 0.5},
        },
        "games": [
            {
                "label": "baseline",
                "opponent": "mega_lucario_beginner",
                "game_index": 1,
                "score": 1.0,
                "termination": {"reason_key": "prize_out"},
            }
        ],
    }

    module.append_eval_history(output_path, run_record)
    module.append_eval_history(output_path, run_record)

    lines = output_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    saved = json.loads(lines[0])
    assert saved["label"] == "baseline"
    assert saved["games"][0]["termination"]["reason_key"] == "prize_out"


def test_crustle_kangaskhan_training_metadata_records_named_opponents():
    metadata = json.loads(
        (ROOT / "agents" / "crustle_mega_kangaskhan_rule_rl_p1" / "training_metadata.json").read_text(
            encoding="utf-8"
        )
    )

    assert metadata["config"]["opponents"] == ["mega_lucario_beginner", "dragapult_rule_based"]


def test_crustle_kangaskhan_eval_report_records_named_opponents():
    report = json.loads(
        (ROOT / "agents" / "crustle_mega_kangaskhan_rule_rl_p1" / "eval_report.json").read_text(
            encoding="utf-8"
        )
    )

    assert "label" in report
    assert "matchups" in report
    assert "mega_lucario_beginner" in report["matchups"]
    assert "dragapult_rule_based" in report["matchups"]
    assert "termination_reasons" in report["matchups"]["dragapult_rule_based"]


def test_crustle_kangaskhan_submission_package_contains_required_files():
    agent_dir = ROOT / "agents" / "crustle_mega_kangaskhan_rule_rl_p1"

    assert (agent_dir / "main.py").exists()
    assert (agent_dir / "deck.csv").exists()
    assert (agent_dir / "cg" / "__init__.py").exists()


def test_crustle_kangaskhan_v2_submission_package_contains_required_files():
    agent_dir = ROOT / "agents" / "crustle_mega_kangaskhan_rule_rl_p1_v2"

    assert (agent_dir / "main.py").exists()
    assert (agent_dir / "deck.csv").exists()
    assert (agent_dir / "cg" / "__init__.py").exists()


def _load_crustle_module(name: str, agent_name: str = "crustle_mega_kangaskhan_rule_rl_p1"):
    agent_dir = ROOT / "agents" / agent_name
    agent_dir_str = str(agent_dir)
    if agent_dir_str not in sys.path:
        sys.path.insert(0, agent_dir_str)
    module_name = f"{agent_name}_{name}"
    return load_module(module_name, agent_dir / f"{name}.py")


def _fake_card(card_id: int, *, name: str, hp: int = 100, max_hp: int = 100, energies=None, tools=None):
    return SimpleNamespace(
        id=card_id,
        name=name,
        hp=hp,
        maxHp=max_hp,
        energies=list(energies or []),
        tools=list(tools or []),
    )


def _fake_obs(
    *,
    hand,
    active,
    bench,
    opponent_active,
    opponent_bench=None,
    options=None,
    context=None,
    supporter_played=False,
    looking=None,
    select_deck=None,
    effect=None,
    context_card=None,
    my_discard=None,
    opponent_discard=None,
):
    current = SimpleNamespace(
        yourIndex=0,
        supporterPlayed=supporter_played,
        energyAttached=False,
        firstPlayer=0,
        turn=1,
        result=-1,
        players=[
            SimpleNamespace(
                hand=list(hand),
                active=[active] if active is not None else [],
                bench=list(bench),
                discard=list(my_discard or []),
                deckCount=40,
                prize=[1, 2, 3, 4],
                handCount=len(hand),
            ),
            SimpleNamespace(
                hand=[],
                active=[opponent_active] if opponent_active is not None else [],
                bench=list(opponent_bench or []),
                discard=list(opponent_discard or []),
                deckCount=40,
                prize=[1, 2],
                handCount=6,
            ),
        ],
        looking=list(looking or []),
    )
    return SimpleNamespace(
        current=current,
        select=SimpleNamespace(
            option=list(options or []),
            context=context,
            deck=list(select_deck or []),
            maxCount=1,
            effect=effect,
            contextCard=context_card,
        ),
    )


def test_crustle_kangaskhan_rule_prior_scores_play_options():
    runtime = _load_crustle_module("runtime")
    rule_prior = _load_crustle_module("rule_prior")
    from cg.api import OptionType

    obs = _fake_obs(
        hand=[_fake_card(runtime.CardIds.BUDDY_BUDDY_POFFIN, name="Buddy-Buddy Poffin")],
        active=_fake_card(runtime.CardIds.MEGA_KANGASKHAN_EX, name="Mega Kangaskhan ex"),
        bench=[
            _fake_card(runtime.CardIds.DWEBBLE, name="Dwebble", hp=70, max_hp=70, energies=[]),
            _fake_card(runtime.CardIds.DWEBBLE, name="Dwebble", hp=70, max_hp=70, energies=[]),
        ],
        opponent_active=_fake_card(9001, name="Dragapult ex"),
        options=[
            SimpleNamespace(type=OptionType.PLAY, index=0),
            SimpleNamespace(type=OptionType.ATTACK),
        ],
    )

    result = rule_prior.score_option(obs, obs.select.option[0])

    assert result["total_logit"] > 0.0
    assert "poffin" in result["reason_tags"]


def test_crustle_kangaskhan_deck_state_exposes_key_windows():
    runtime = _load_crustle_module("runtime")
    deck_state_module = _load_crustle_module("deck_state")
    from cg.api import OptionType

    crustle = _fake_card(
        runtime.CardIds.CRUSTLE,
        name="Crustle",
        hp=40,
        max_hp=140,
        energies=[1, 1, 1],
    )
    kangaskhan = _fake_card(runtime.CardIds.MEGA_KANGASKHAN_EX, name="Mega Kangaskhan ex", hp=230, max_hp=230)
    obs = _fake_obs(
        hand=[],
        active=crustle,
        bench=[kangaskhan],
        opponent_active=_fake_card(9002, name="Mega Lucario ex", hp=220, max_hp=220, energies=[1, 1]),
        opponent_bench=[_fake_card(9003, name="Support Pokemon", hp=60, max_hp=60)],
        options=[SimpleNamespace(type=OptionType.ATTACK)],
    )

    state = deck_state_module.analyze_deck_state(obs)

    assert state.wall_online is True
    assert state.primary_plan == "wall_and_tax"
    assert state.heal_window is False
    assert state.disruption_window is True
    assert state.gust_window is True


def test_crustle_kangaskhan_deck_knowledge_tracks_full_search_only():
    runtime = _load_crustle_module("runtime")
    deck_knowledge = _load_crustle_module("deck_knowledge")

    tracker = deck_knowledge.DeckKnowledgeTracker(
        [
            runtime.CardIds.DWEBBLE,
            runtime.CardIds.CRUSTLE,
            runtime.CardIds.MEGA_KANGASKHAN_EX,
            runtime.CardIds.GROW_GRASS_ENERGY,
        ]
    )
    hidden_obs = _fake_obs(
        hand=[],
        active=_fake_card(runtime.CardIds.MEGA_KANGASKHAN_EX, name="Mega Kangaskhan ex"),
        bench=[],
        opponent_active=_fake_card(9901, name="Mega Lucario ex"),
        select_deck=[_fake_card(runtime.CardIds.DWEBBLE, name="Dwebble")],
    )
    tracker.update(hidden_obs)

    assert tracker.deck_has(runtime.CardIds.CRUSTLE) is None

    full_search_obs = _fake_obs(
        hand=[],
        active=_fake_card(runtime.CardIds.MEGA_KANGASKHAN_EX, name="Mega Kangaskhan ex"),
        bench=[],
        opponent_active=_fake_card(9902, name="Mega Lucario ex"),
        select_deck=[
            _fake_card(runtime.CardIds.DWEBBLE, name="Dwebble"),
            _fake_card(runtime.CardIds.GROW_GRASS_ENERGY, name="Growing Grass Energy"),
        ],
    )
    full_search_obs.current.players[0].deckCount = 2
    tracker.update(full_search_obs)

    assert tracker.deck_has(runtime.CardIds.DWEBBLE) is True
    assert tracker.deck_has(runtime.CardIds.CRUSTLE) is False


def test_crustle_kangaskhan_action_encoder_marks_key_trainers():
    runtime = _load_crustle_module("runtime")
    action_encoder = _load_crustle_module("action_encoder")
    from cg.api import OptionType

    obs = _fake_obs(
        hand=[_fake_card(runtime.CardIds.HILDA, name="Hilda")],
        active=_fake_card(runtime.CardIds.MEGA_KANGASKHAN_EX, name="Mega Kangaskhan ex"),
        bench=[],
        opponent_active=_fake_card(9001, name="Dragapult ex"),
        options=[SimpleNamespace(type=OptionType.PLAY, index=0)],
    )
    features = action_encoder.encode_action(obs, obs.select.option[0])
    index_map = {name: idx for idx, name in enumerate(action_encoder.ACTION_FEATURE_NAMES)}

    assert features[index_map["is_play"]] == 1.0
    assert features[index_map["is_hilda"]] == 1.0
    assert features[index_map["is_lillie"]] == 0.0


def test_crustle_kangaskhan_observation_marks_key_hand_cards():
    runtime = _load_crustle_module("runtime")
    observation_builder = _load_crustle_module("observation_builder")

    obs = _fake_obs(
        hand=[
            _fake_card(runtime.CardIds.HILDA, name="Hilda"),
            _fake_card(runtime.CardIds.JUMBO_ICE_CREAM, name="Jumbo Ice Cream"),
        ],
        active=_fake_card(runtime.CardIds.MEGA_KANGASKHAN_EX, name="Mega Kangaskhan ex"),
        bench=[],
        opponent_active=_fake_card(9001, name="Dragapult ex"),
    )
    features = observation_builder.build_observation_features(obs)
    index_map = {name: idx for idx, name in enumerate(observation_builder.OBSERVATION_FEATURE_NAMES)}

    assert features[index_map["has_hilda"]] == 1.0
    assert features[index_map["has_jumbo_ice_cream"]] == 1.0
    assert features[index_map["has_lillie"]] == 0.0


def test_crustle_kangaskhan_rule_logits_are_preserved_without_policy():
    inference = _load_crustle_module("inference", agent_name="crustle_mega_kangaskhan_rule_rl_p1_v2")

    preserved = inference.normalize_rule_logits([90.0, 60.0, 30.0], use_policy=False)

    assert preserved == [90.0, 60.0, 30.0]


def test_crustle_kangaskhan_rule_logits_only_normalize_when_policy_enabled():
    inference = _load_crustle_module("inference", agent_name="crustle_mega_kangaskhan_rule_rl_p1_v2")

    normalized = inference.normalize_rule_logits([90.0, 60.0, 30.0], use_policy=True)

    assert max(normalized) <= 3.0
    assert min(normalized) >= -3.0
    assert normalized[0] > normalized[1] > normalized[2]
    assert abs(sum(normalized)) < 1e-5


def test_crustle_kangaskhan_reward_uses_prize_delta_instead_of_cumulative_state():
    collect_dataset = _load_crustle_module("collect_dataset")

    prev_obs = SimpleNamespace(
        current=SimpleNamespace(
            result=-1,
            players=[
                SimpleNamespace(prize=[1, 2, 3, 4]),
                SimpleNamespace(prize=[1, 2, 3, 4]),
            ],
        )
    )
    next_obs = SimpleNamespace(
        current=SimpleNamespace(
            result=-1,
            players=[
                SimpleNamespace(prize=[1, 2, 3, 4]),
                SimpleNamespace(prize=[1, 2, 3]),
            ],
        )
    )
    later_obs = SimpleNamespace(
        current=SimpleNamespace(
            result=-1,
            players=[
                SimpleNamespace(prize=[1, 2, 3, 4]),
                SimpleNamespace(prize=[1, 2, 3]),
            ],
        )
    )

    reward_on_prize = collect_dataset._compute_shaped_reward(prev_obs, next_obs, player_index=0)
    reward_without_new_delta = collect_dataset._compute_shaped_reward(next_obs, later_obs, player_index=0)

    assert reward_on_prize > 0.0
    assert reward_without_new_delta == 0.0


def test_crustle_kangaskhan_matchup_profile_detects_dragapult():
    matchup_profile = _load_crustle_module("matchup_profile")

    obs = _fake_obs(
        hand=[],
        active=_fake_card(1, name="Crustle"),
        bench=[],
        opponent_active=_fake_card(9001, name="Dragapult ex"),
    )
    profile = matchup_profile.detect_matchup_profile(obs)

    assert profile.name == "dragapult_ex"
    assert profile.values_mist_energy is True


def test_crustle_kangaskhan_deck_state_keeps_wall_plan_over_setup_kang():
    runtime = _load_crustle_module("runtime")
    deck_state_module = _load_crustle_module("deck_state")
    from cg.api import OptionType

    crustle = _fake_card(runtime.CardIds.CRUSTLE, name="Crustle", hp=90, max_hp=140, energies=[1])
    obs = _fake_obs(
        hand=[],
        active=crustle,
        bench=[],
        opponent_active=_fake_card(9002, name="Mega Lucario ex", hp=220, max_hp=220, energies=[1, 1]),
        options=[SimpleNamespace(type=OptionType.ATTACK)],
    )

    state = deck_state_module.analyze_deck_state(obs)

    assert state.wall_online is True
    assert state.primary_plan == "wall_and_tax"


def test_crustle_kangaskhan_observation_tracks_special_energy_counts():
    runtime = _load_crustle_module("runtime")
    observation_builder = _load_crustle_module("observation_builder")

    obs = _fake_obs(
        hand=[
            _fake_card(runtime.CardIds.GROW_GRASS_ENERGY, name="Growing Grass Energy"),
            _fake_card(runtime.CardIds.MIST_ENERGY, name="Mist Energy"),
            _fake_card(runtime.CardIds.SPIKY_ENERGY, name="Spiky Energy"),
            _fake_card(runtime.CardIds.BASIC_GRASS, name="Grass Energy"),
        ],
        active=_fake_card(runtime.CardIds.MEGA_KANGASKHAN_EX, name="Mega Kangaskhan ex"),
        bench=[],
        opponent_active=_fake_card(9001, name="Dragapult ex"),
    )
    features = observation_builder.build_observation_features(obs)
    index_map = {name: idx for idx, name in enumerate(observation_builder.OBSERVATION_FEATURE_NAMES)}

    assert features[index_map["hand_growing_grass_count"]] > 0.0
    assert features[index_map["hand_mist_count"]] > 0.0
    assert features[index_map["hand_spiky_count"]] > 0.0
    assert features[index_map["hand_basic_grass_count"]] > 0.0


def test_crustle_kangaskhan_selection_scorer_prefers_close_game_petrel_targets():
    runtime = _load_crustle_module("runtime")
    selection_scorer = _load_crustle_module("selection_scorer")

    deck_state = SimpleNamespace(primary_plan="close_game")

    boss_score, boss_tag = selection_scorer.score_petrel_target(runtime.CardIds.BOSS_ORDERS, deck_state)
    heal_score, _ = selection_scorer.score_petrel_target(runtime.CardIds.JUMBO_ICE_CREAM, deck_state)

    assert boss_score > heal_score
    assert boss_tag == "petrel_close_game"


def test_crustle_kangaskhan_selection_scorer_protects_one_ofs_on_ultra_ball_discard():
    runtime = _load_crustle_module("runtime")
    selection_scorer = _load_crustle_module("selection_scorer")

    deck_state = SimpleNamespace(
        setup_missing_crustle=True,
        crustle_in_play=0,
        kangaskhan_in_play=0,
    )

    hero_score, hero_tag = selection_scorer.score_ultra_ball_discard(runtime.CardIds.HERO_CAPE, deck_state)
    basic_score, basic_tag = selection_scorer.score_ultra_ball_discard(runtime.CardIds.BASIC_GRASS, deck_state)

    assert hero_score < basic_score
    assert hero_tag == "protect_one_of"
    assert basic_tag == "discard_basic_grass"


def test_crustle_kangaskhan_rule_prior_prefers_mist_in_dragapult_matchup():
    runtime = _load_crustle_module("runtime")
    rule_prior = _load_crustle_module("rule_prior")
    from cg.api import AreaType, OptionType

    active = _fake_card(runtime.CardIds.MEGA_KANGASKHAN_EX, name="Mega Kangaskhan ex", hp=180, max_hp=230, energies=[1, 1])
    mist = _fake_card(runtime.CardIds.MIST_ENERGY, name="Mist Energy")
    basic = _fake_card(runtime.CardIds.BASIC_GRASS, name="Grass Energy")
    obs = _fake_obs(
        hand=[mist, basic],
        active=active,
        bench=[],
        opponent_active=_fake_card(9001, name="Dragapult ex", hp=320, max_hp=320, energies=[1, 1]),
        options=[
            SimpleNamespace(type=OptionType.ATTACH, index=0, inPlayArea=AreaType.ACTIVE, inPlayIndex=0),
            SimpleNamespace(type=OptionType.ATTACH, index=1, inPlayArea=AreaType.ACTIVE, inPlayIndex=0),
        ],
    )

    mist_result = rule_prior.score_option(obs, obs.select.option[0])
    basic_result = rule_prior.score_option(obs, obs.select.option[1])

    assert mist_result["total_logit"] > basic_result["total_logit"]
    assert "mist_protection" in mist_result["reason_tags"]


def test_crustle_kangaskhan_rule_prior_penalizes_wasted_boss():
    runtime = _load_crustle_module("runtime")
    rule_prior = _load_crustle_module("rule_prior")
    from cg.api import OptionType

    active = _fake_card(runtime.CardIds.MEGA_KANGASKHAN_EX, name="Mega Kangaskhan ex", hp=230, max_hp=230, energies=[1, 1, 1])
    switch = _fake_card(runtime.CardIds.SWITCH, name="Switch")
    boss = _fake_card(runtime.CardIds.BOSS_ORDERS, name="Boss's Orders")
    obs = _fake_obs(
        hand=[switch, boss],
        active=active,
        bench=[],
        opponent_active=_fake_card(9002, name="Support Pokemon", hp=220, max_hp=220, energies=[]),
        opponent_bench=[_fake_card(9003, name="Bench Pokemon", hp=180, max_hp=180, energies=[1])],
        options=[SimpleNamespace(type=OptionType.PLAY, index=0)],
    )

    result = rule_prior.score_option(obs, obs.select.option[0])

    assert result["breakdown"].get("risk", 0.0) < 0.0
    assert "wasted_boss" in result["reason_tags"]


def test_crustle_kangaskhan_selection_scorer_prefers_dwebble_for_poffin():
    runtime = _load_crustle_module("runtime")
    selection_scorer = _load_crustle_module("selection_scorer")

    deck_state = SimpleNamespace(primary_plan="setup_crustle")
    matchup = SimpleNamespace(prefers_crustle_wall=True)

    dwebble_score, dwebble_tag = selection_scorer.score_poffin_target(runtime.CardIds.DWEBBLE, deck_state, matchup)
    kang_score, _ = selection_scorer.score_poffin_target(runtime.CardIds.MEGA_KANGASKHAN_EX, deck_state, matchup)

    assert dwebble_score > kang_score
    assert dwebble_tag == "poffin_dwebble"


def test_crustle_kangaskhan_rule_prior_preserves_boss_in_unknown_matchup():
    runtime = _load_crustle_module("runtime")
    rule_prior = _load_crustle_module("rule_prior")
    from cg.api import OptionType

    active = _fake_card(runtime.CardIds.MEGA_KANGASKHAN_EX, name="Mega Kangaskhan ex", hp=230, max_hp=230, energies=[1, 1])
    switch = _fake_card(runtime.CardIds.SWITCH, name="Switch")
    boss = _fake_card(runtime.CardIds.BOSS_ORDERS, name="Boss's Orders")
    obs = _fake_obs(
        hand=[switch, boss],
        active=active,
        bench=[],
        opponent_active=_fake_card(9004, name="Unknown Attacker", hp=170, max_hp=170, energies=[1]),
        opponent_bench=[_fake_card(9005, name="Bench Pokemon", hp=170, max_hp=170, energies=[1])],
        options=[SimpleNamespace(type=OptionType.PLAY, index=0)],
    )

    result = rule_prior.score_option(obs, obs.select.option[0])

    assert result["breakdown"].get("risk", 0.0) < 0.0
    assert "preserve_unknown_resource" in result["reason_tags"]


def test_crustle_kangaskhan_rule_prior_penalizes_dead_poffin_with_known_empty_targets():
    runtime = _load_crustle_module("runtime")
    rule_prior = _load_crustle_module("rule_prior")
    from cg.api import OptionType

    poffin = _fake_card(runtime.CardIds.BUDDY_BUDDY_POFFIN, name="Buddy-Buddy Poffin")
    eri = _fake_card(runtime.CardIds.ERI, name="Eri")
    obs = _fake_obs(
        hand=[poffin, eri],
        active=_fake_card(runtime.CardIds.MEGA_KANGASKHAN_EX, name="Mega Kangaskhan ex", hp=230, max_hp=230),
        bench=[
            _fake_card(runtime.CardIds.CRUSTLE, name="Crustle", hp=140, max_hp=140),
            _fake_card(runtime.CardIds.CRUSTLE, name="Crustle", hp=140, max_hp=140),
        ],
        opponent_active=_fake_card(9306, name="Unknown Attacker", hp=180, max_hp=180, energies=[1]),
        options=[
            SimpleNamespace(type=OptionType.PLAY, index=0),
            SimpleNamespace(type=OptionType.PLAY, index=1),
        ],
    )
    deck_knowledge = SimpleNamespace(
        deck_has=lambda card_id: False if card_id in {runtime.CardIds.DWEBBLE, runtime.CardIds.MEGA_KANGASKHAN_EX} else None
    )

    poffin_result = rule_prior.score_option(obs, obs.select.option[0], deck_knowledge=deck_knowledge)
    eri_result = rule_prior.score_option(obs, obs.select.option[1], deck_knowledge=deck_knowledge)

    assert poffin_result["total_logit"] < eri_result["total_logit"]
    assert "dead_poffin" in poffin_result["reason_tags"]


def test_crustle_kangaskhan_rule_prior_values_petrel_for_setup_crustle():
    runtime = _load_crustle_module("runtime")
    rule_prior = _load_crustle_module("rule_prior")
    from cg.api import OptionType

    petrel = _fake_card(runtime.CardIds.PETREL, name="Petrel")
    lillie = _fake_card(runtime.CardIds.LILLIE, name="Lillie")
    obs = _fake_obs(
        hand=[petrel, lillie],
        active=_fake_card(runtime.CardIds.MEGA_KANGASKHAN_EX, name="Mega Kangaskhan ex", hp=230, max_hp=230),
        bench=[],
        opponent_active=_fake_card(9006, name="Mega Lucario ex", hp=220, max_hp=220, energies=[1, 1]),
        options=[
            SimpleNamespace(type=OptionType.PLAY, index=0),
            SimpleNamespace(type=OptionType.PLAY, index=1),
        ],
    )

    petrel_result = rule_prior.score_option(obs, obs.select.option[0])
    lillie_result = rule_prior.score_option(obs, obs.select.option[1])

    assert petrel_result["total_logit"] > lillie_result["total_logit"]
    assert "petrel_setup_crustle" in petrel_result["reason_tags"]


def test_crustle_kangaskhan_rule_prior_petrel_drops_when_no_clear_target():
    runtime = _load_crustle_module("runtime")
    rule_prior = _load_crustle_module("rule_prior")
    from cg.api import OptionType

    petrel = _fake_card(runtime.CardIds.PETREL, name="Petrel")
    hilda = _fake_card(runtime.CardIds.HILDA, name="Hilda")
    poffin = _fake_card(runtime.CardIds.BUDDY_BUDDY_POFFIN, name="Buddy-Buddy Poffin")
    ultra_ball = _fake_card(runtime.CardIds.ULTRA_BALL, name="Ultra Ball")
    lillie = _fake_card(runtime.CardIds.LILLIE, name="Lillie")
    obs = _fake_obs(
        hand=[petrel, hilda, poffin, ultra_ball, lillie],
        my_discard=[hilda, poffin, ultra_ball],
        active=_fake_card(runtime.CardIds.MEGA_KANGASKHAN_EX, name="Mega Kangaskhan ex", hp=230, max_hp=230),
        bench=[],
        opponent_active=_fake_card(90061, name="Mega Lucario ex", hp=220, max_hp=220, energies=[1, 1]),
        options=[
            SimpleNamespace(type=OptionType.PLAY, index=0),
            SimpleNamespace(type=OptionType.PLAY, index=4),
        ],
    )

    petrel_result = rule_prior.score_option(obs, obs.select.option[0])
    lillie_result = rule_prior.score_option(obs, obs.select.option[1])

    assert "petrel_no_clear_target" in petrel_result["reason_tags"]
    assert petrel_result["total_logit"] < lillie_result["total_logit"]


def test_crustle_kangaskhan_rule_prior_hilda_pairs_crustle_with_growing_grass():
    runtime = _load_crustle_module("runtime")
    rule_prior = _load_crustle_module("rule_prior")
    from cg.api import AreaType, OptionType, SelectContext

    hilda = _fake_card(runtime.CardIds.HILDA, name="Hilda")
    grow = _fake_card(runtime.CardIds.GROW_GRASS_ENERGY, name="Growing Grass Energy")
    basic = _fake_card(runtime.CardIds.BASIC_GRASS, name="Grass Energy")
    obs = _fake_obs(
        hand=[hilda],
        active=_fake_card(runtime.CardIds.MEGA_KANGASKHAN_EX, name="Mega Kangaskhan ex", hp=230, max_hp=230),
        bench=[],
        opponent_active=_fake_card(9007, name="Mega Lucario ex", hp=220, max_hp=220, energies=[1]),
        looking=[_fake_card(runtime.CardIds.CRUSTLE, name="Crustle")],
        select_deck=[grow, basic],
        effect=hilda,
        options=[
            SimpleNamespace(type=OptionType.CARD, area=AreaType.DECK, index=0, playerIndex=0),
            SimpleNamespace(type=OptionType.CARD, area=AreaType.DECK, index=1, playerIndex=0),
        ],
        context=SelectContext.TO_HAND,
    )

    grow_result = rule_prior.score_option(obs, obs.select.option[0])
    basic_result = rule_prior.score_option(obs, obs.select.option[1])

    assert grow_result["total_logit"] > basic_result["total_logit"]
    assert "hilda_pair_crustle_grow_grass" in grow_result["reason_tags"]


def test_crustle_kangaskhan_rule_prior_hilda_prefers_mist_with_dwebble_into_dragapult():
    runtime = _load_crustle_module("runtime")
    rule_prior = _load_crustle_module("rule_prior")
    from cg.api import AreaType, OptionType, SelectContext

    hilda = _fake_card(runtime.CardIds.HILDA, name="Hilda")
    mist = _fake_card(runtime.CardIds.MIST_ENERGY, name="Mist Energy")
    basic = _fake_card(runtime.CardIds.BASIC_GRASS, name="Grass Energy")
    obs = _fake_obs(
        hand=[hilda],
        active=_fake_card(runtime.CardIds.MEGA_KANGASKHAN_EX, name="Mega Kangaskhan ex", hp=230, max_hp=230),
        bench=[],
        opponent_active=_fake_card(9008, name="Dragapult ex", hp=320, max_hp=320, energies=[1, 1]),
        looking=[_fake_card(runtime.CardIds.DWEBBLE, name="Dwebble")],
        select_deck=[mist, basic],
        effect=hilda,
        options=[
            SimpleNamespace(type=OptionType.CARD, area=AreaType.DECK, index=0, playerIndex=0),
            SimpleNamespace(type=OptionType.CARD, area=AreaType.DECK, index=1, playerIndex=0),
        ],
        context=SelectContext.TO_HAND,
    )

    mist_result = rule_prior.score_option(obs, obs.select.option[0])
    basic_result = rule_prior.score_option(obs, obs.select.option[1])

    assert mist_result["total_logit"] > basic_result["total_logit"]
    assert "hilda_pair_dwebble_mist" in mist_result["reason_tags"]
    assert mist_result["reason_tags"].count("hilda_pair_dwebble_mist") == 1


def test_crustle_kangaskhan_matchup_profile_keeps_crustle_plan_into_dragapult():
    matchup_profile = _load_crustle_module("matchup_profile")

    obs = _fake_obs(
        hand=[],
        active=_fake_card(1, name="Mega Kangaskhan ex"),
        bench=[],
        opponent_active=_fake_card(9301, name="Dragapult ex"),
    )
    profile = matchup_profile.detect_matchup_profile(obs)

    assert profile.name == "dragapult_ex"
    assert profile.prefers_crustle_wall is True


def test_crustle_kangaskhan_hilda_combo_prefers_crustle_grow_over_singletons():
    runtime = _load_crustle_module("runtime")
    rule_prior = _load_crustle_module("rule_prior")
    from cg.api import AreaType, OptionType, SelectContext

    hilda = _fake_card(runtime.CardIds.HILDA, name="Hilda")
    crustle = _fake_card(runtime.CardIds.CRUSTLE, name="Crustle")
    grow = _fake_card(runtime.CardIds.GROW_GRASS_ENERGY, name="Growing Grass Energy")
    basic = _fake_card(runtime.CardIds.BASIC_GRASS, name="Grass Energy")
    obs = _fake_obs(
        hand=[hilda],
        active=_fake_card(runtime.CardIds.DWEBBLE, name="Dwebble", hp=70, max_hp=70, energies=[]),
        bench=[],
        opponent_active=_fake_card(9302, name="Mega Lucario ex", hp=220, max_hp=220, energies=[1]),
        looking=[crustle],
        select_deck=[crustle, grow, basic],
        effect=hilda,
        options=[
            SimpleNamespace(type=OptionType.CARD, area=AreaType.DECK, index=0, playerIndex=0),
            SimpleNamespace(type=OptionType.CARD, area=AreaType.DECK, index=1, playerIndex=0),
            SimpleNamespace(type=OptionType.CARD, area=AreaType.DECK, index=2, playerIndex=0),
        ],
        context=SelectContext.TO_HAND,
    )

    crustle_result = rule_prior.score_option(obs, obs.select.option[0])
    grow_result = rule_prior.score_option(obs, obs.select.option[1])
    basic_result = rule_prior.score_option(obs, obs.select.option[2])

    assert crustle_result["total_logit"] > basic_result["total_logit"]
    assert grow_result["total_logit"] > basic_result["total_logit"]
    assert "hilda_complete_crustle_grow" in crustle_result["reason_tags"] or "hilda_complete_crustle_grow" in grow_result["reason_tags"]


def test_crustle_kangaskhan_petrel_prefers_survival_setup_targets_when_exposed():
    runtime = _load_crustle_module("runtime")
    selection_scorer = _load_crustle_module("selection_scorer")

    deck_state = SimpleNamespace(primary_plan="survival_setup", must_bench_basic=True)

    poffin_score, poffin_tag = selection_scorer.score_petrel_target(runtime.CardIds.BUDDY_BUDDY_POFFIN, deck_state)
    boss_score, _ = selection_scorer.score_petrel_target(runtime.CardIds.BOSS_ORDERS, deck_state)

    assert poffin_score > boss_score
    assert poffin_tag == "petrel_survival_setup"


def test_crustle_kangaskhan_deck_state_splits_heal_windows():
    runtime = _load_crustle_module("runtime")
    deck_state_module = _load_crustle_module("deck_state")
    from cg.api import OptionType

    active = _fake_card(
        runtime.CardIds.MEGA_KANGASKHAN_EX,
        name="Mega Kangaskhan ex",
        hp=30,
        max_hp=230,
        energies=[1, 1, 1],
    )
    obs = _fake_obs(
        hand=[],
        active=active,
        bench=[],
        opponent_active=_fake_card(9303, name="Mega Lucario ex", hp=220, max_hp=220, energies=[1, 1]),
        options=[SimpleNamespace(type=OptionType.ATTACK)],
    )

    state = deck_state_module.analyze_deck_state(obs)

    assert state.jumbo_prevents_ko is False
    assert state.bianca_prevents_ko is True
    assert state.has_effective_heal is True


def test_crustle_kangaskhan_rule_prior_reports_line_progress_for_ascension():
    runtime = _load_crustle_module("runtime")
    rule_prior = _load_crustle_module("rule_prior")
    from cg.api import OptionType

    obs = _fake_obs(
        hand=[],
        active=_fake_card(runtime.CardIds.DWEBBLE, name="Dwebble", hp=70, max_hp=70, energies=[]),
        bench=[],
        opponent_active=_fake_card(9304, name="Mega Lucario ex", hp=220, max_hp=220, energies=[1]),
        options=[SimpleNamespace(type=OptionType.ATTACK)],
    )

    result = rule_prior.score_option(obs, obs.select.option[0])

    assert result["breakdown"].get("line_progress", 0.0) > 0.0


def test_crustle_kangaskhan_rule_debug_writes_jsonl(tmp_path: Path, monkeypatch):
    inference = _load_crustle_module("inference")
    deck_knowledge = _load_crustle_module("deck_knowledge")
    runtime = _load_crustle_module("runtime")
    from cg.api import OptionType

    debug_path = tmp_path / "rule_debug.jsonl"
    monkeypatch.setenv("RULE_DEBUG", "1")
    monkeypatch.setenv("RULE_DEBUG_PATH", str(debug_path))

    obs = _fake_obs(
        hand=[_fake_card(runtime.CardIds.BUDDY_BUDDY_POFFIN, name="Buddy-Buddy Poffin")],
        active=_fake_card(runtime.CardIds.MEGA_KANGASKHAN_EX, name="Mega Kangaskhan ex", hp=230, max_hp=230),
        bench=[],
        opponent_active=_fake_card(9305, name="Mega Lucario ex", hp=220, max_hp=220, energies=[1]),
        options=[SimpleNamespace(type=OptionType.PLAY, index=0), SimpleNamespace(type=OptionType.END)],
    )

    tracker = deck_knowledge.DeckKnowledgeTracker(
        [
            runtime.CardIds.BUDDY_BUDDY_POFFIN,
            runtime.CardIds.DWEBBLE,
            runtime.CardIds.MEGA_KANGASKHAN_EX,
        ]
    )
    scored = inference.score_actions(obs, None, use_policy=False, deck_knowledge=tracker)

    assert scored
    lines = debug_path.read_text(encoding="utf-8").splitlines()
    assert lines
    payload = json.loads(lines[-1])
    assert "primary_plan" in payload
    assert "top_actions" in payload
    assert "active" in payload
    assert "bench" in payload
    assert "selected" in payload
    assert "state_flags" in payload
    assert "selected_action" in payload
    assert "deck_knowledge" in payload


def test_crustle_kangaskhan_selection_scorer_prefers_gust_on_dragapult_setup_basic():
    runtime = _load_crustle_module("runtime")
    selection_scorer = _load_crustle_module("selection_scorer")

    deck_state = SimpleNamespace(
        gust_for_win=False,
        opponent_prizes_left=2,
        matchup=SimpleNamespace(values_gust_on_setup_targets=True),
    )
    dreepy = _fake_card(9101, name="Dreepy", hp=60, max_hp=60, energies=[])
    dragapult = _fake_card(9102, name="Dragapult ex", hp=320, max_hp=320, energies=[1, 1])

    dreepy_score, dreepy_tag = selection_scorer.score_gust_target(dreepy, deck_state)
    dragapult_score, _ = selection_scorer.score_gust_target(dragapult, deck_state)

    assert dreepy_score > dragapult_score
    assert dreepy_tag == "gust_setup_basic"


def test_crustle_kangaskhan_selection_scorer_protects_mist_on_ultra_ball_discard():
    runtime = _load_crustle_module("runtime")
    selection_scorer = _load_crustle_module("selection_scorer")

    deck_state = SimpleNamespace(
        setup_missing_crustle=False,
        crustle_in_play=1,
        kangaskhan_in_play=1,
        matchup=SimpleNamespace(values_mist_energy=True),
    )

    mist_score, mist_tag = selection_scorer.score_ultra_ball_discard(runtime.CardIds.MIST_ENERGY, deck_state)
    basic_score, basic_tag = selection_scorer.score_ultra_ball_discard(runtime.CardIds.BASIC_GRASS, deck_state)

    assert mist_score < basic_score
    assert mist_tag == "protect_mist"
    assert basic_tag == "discard_basic_grass"


def test_crustle_kangaskhan_deck_state_marks_dragapult_bench_risk():
    runtime = _load_crustle_module("runtime")
    deck_state_module = _load_crustle_module("deck_state")

    obs = _fake_obs(
        hand=[],
        active=_fake_card(runtime.CardIds.MEGA_KANGASKHAN_EX, name="Mega Kangaskhan ex", hp=230, max_hp=230, energies=[1, 1]),
        bench=[_fake_card(runtime.CardIds.DWEBBLE, name="Dwebble", hp=40, max_hp=70)],
        opponent_active=_fake_card(9103, name="Dragapult ex", hp=320, max_hp=320, energies=[1, 1]),
    )

    state = deck_state_module.analyze_deck_state(obs)

    assert "bench_risk" in state.state_tags
    assert state.plan_scores["setup_crustle"] > state.plan_scores["tank_and_heal"]


def test_crustle_kangaskhan_deck_state_marks_must_bench_basic():
    runtime = _load_crustle_module("runtime")
    deck_state_module = _load_crustle_module("deck_state")

    obs = _fake_obs(
        hand=[_fake_card(runtime.CardIds.DWEBBLE, name="Dwebble", hp=70, max_hp=70)],
        active=_fake_card(runtime.CardIds.MEGA_KANGASKHAN_EX, name="Mega Kangaskhan ex", hp=230, max_hp=230),
        bench=[],
        opponent_active=_fake_card(9201, name="Unknown Attacker", hp=170, max_hp=170, energies=[1]),
    )

    state = deck_state_module.analyze_deck_state(obs)

    assert state.only_one_pokemon_in_play is True
    assert state.must_bench_basic is True
    assert "must_bench_basic" in state.state_tags


def test_crustle_kangaskhan_deck_state_marks_must_bench_basic_for_low_board_early():
    runtime = _load_crustle_module("runtime")
    deck_state_module = _load_crustle_module("deck_state")

    obs = _fake_obs(
        hand=[],
        active=_fake_card(runtime.CardIds.MEGA_KANGASKHAN_EX, name="Mega Kangaskhan ex", hp=230, max_hp=230),
        bench=[_fake_card(runtime.CardIds.DWEBBLE, name="Dwebble", hp=70, max_hp=70)],
        opponent_active=_fake_card(9910, name="Mega Lucario ex", hp=220, max_hp=220, energies=[1]),
    )
    obs.current.turn = 1

    state = deck_state_module.analyze_deck_state(obs)

    assert state.must_bench_basic is True
    assert state.primary_plan == "survival_setup"


def test_crustle_kangaskhan_rule_prior_prioritizes_benching_when_must_bench_basic():
    runtime = _load_crustle_module("runtime")
    rule_prior = _load_crustle_module("rule_prior")
    from cg.api import OptionType

    dwebble = _fake_card(runtime.CardIds.DWEBBLE, name="Dwebble", hp=70, max_hp=70)
    pokegear = _fake_card(runtime.CardIds.POKEGEAR, name="Pokégear 3.0")
    obs = _fake_obs(
        hand=[dwebble, pokegear],
        active=_fake_card(runtime.CardIds.MEGA_KANGASKHAN_EX, name="Mega Kangaskhan ex", hp=230, max_hp=230),
        bench=[],
        opponent_active=_fake_card(9202, name="Unknown Attacker", hp=170, max_hp=170, energies=[1]),
        options=[
            SimpleNamespace(type=OptionType.PLAY, index=0),
            SimpleNamespace(type=OptionType.PLAY, index=1),
        ],
    )

    bench_result = rule_prior.score_option(obs, obs.select.option[0])
    gear_result = rule_prior.score_option(obs, obs.select.option[1])

    assert bench_result["total_logit"] > gear_result["total_logit"]
    assert "must_bench_basic" in bench_result["reason_tags"]


def test_crustle_kangaskhan_rule_prior_prefers_bench_search_over_kang_ability_when_exposed():
    runtime = _load_crustle_module("runtime")
    rule_prior = _load_crustle_module("rule_prior")
    from cg.api import OptionType

    poffin = _fake_card(runtime.CardIds.BUDDY_BUDDY_POFFIN, name="Buddy-Buddy Poffin")
    obs = _fake_obs(
        hand=[poffin],
        active=_fake_card(runtime.CardIds.MEGA_KANGASKHAN_EX, name="Mega Kangaskhan ex", hp=230, max_hp=230),
        bench=[],
        opponent_active=_fake_card(9207, name="Unknown Attacker", hp=170, max_hp=170, energies=[1]),
        options=[
            SimpleNamespace(type=OptionType.PLAY, index=0),
            SimpleNamespace(type=OptionType.ABILITY, area=4, index=0),
            SimpleNamespace(type=OptionType.END),
        ],
    )

    play_result = rule_prior.score_option(obs, obs.select.option[0])
    ability_result = rule_prior.score_option(obs, obs.select.option[1])
    end_result = rule_prior.score_option(obs, obs.select.option[2])

    assert play_result["total_logit"] > ability_result["total_logit"]
    assert play_result["total_logit"] > end_result["total_logit"]


def test_crustle_kangaskhan_deck_state_marks_must_bench_basic_under_ko_threat():
    runtime = _load_crustle_module("runtime")
    deck_state_module = _load_crustle_module("deck_state")

    obs = _fake_obs(
        hand=[],
        active=_fake_card(runtime.CardIds.MEGA_KANGASKHAN_EX, name="Mega Kangaskhan ex", hp=50, max_hp=230),
        bench=[],
        opponent_active=_fake_card(9208, name="Mega Lucario ex", hp=220, max_hp=220, energies=[1, 1]),
    )

    state = deck_state_module.analyze_deck_state(obs)

    assert state.active_under_ko_threat is True
    assert state.must_bench_basic is True


def test_crustle_kangaskhan_selection_scorer_poffin_gets_must_bench_bonus():
    runtime = _load_crustle_module("runtime")
    selection_scorer = _load_crustle_module("selection_scorer")

    deck_state = SimpleNamespace(primary_plan="survival_setup", must_bench_basic=True)
    matchup = SimpleNamespace(prefers_crustle_wall=True)

    dwebble_score, dwebble_tag = selection_scorer.score_poffin_target(runtime.CardIds.DWEBBLE, deck_state, matchup)
    kang_score, kang_tag = selection_scorer.score_poffin_target(runtime.CardIds.MEGA_KANGASKHAN_EX, deck_state, matchup)

    assert dwebble_score >= 140.0
    assert kang_score >= 120.0
    assert dwebble_tag == "poffin_must_bench_dwebble"
    assert kang_tag == "poffin_must_bench_kang"


def test_crustle_kangaskhan_primary_plan_prefers_survival_setup_when_exposed():
    runtime = _load_crustle_module("runtime")
    deck_state_module = _load_crustle_module("deck_state")

    obs = _fake_obs(
        hand=[_fake_card(runtime.CardIds.BUDDY_BUDDY_POFFIN, name="Buddy-Buddy Poffin")],
        active=_fake_card(runtime.CardIds.MEGA_KANGASKHAN_EX, name="Mega Kangaskhan ex", hp=50, max_hp=230),
        bench=[],
        opponent_active=_fake_card(9209, name="Mega Lucario ex", hp=220, max_hp=220, energies=[1, 1]),
    )

    state = deck_state_module.analyze_deck_state(obs)

    assert state.primary_plan == "survival_setup"


def test_crustle_kangaskhan_primary_plan_uses_close_pressure_not_finish_without_verified_win():
    runtime = _load_crustle_module("runtime")
    deck_state_module = _load_crustle_module("deck_state")

    obs = _fake_obs(
        hand=[],
        active=_fake_card(runtime.CardIds.CRUSTLE, name="Crustle", hp=140, max_hp=140, energies=[]),
        bench=[
            _fake_card(runtime.CardIds.MEGA_KANGASKHAN_EX, name="Mega Kangaskhan ex", hp=230, max_hp=230, energies=[]),
            _fake_card(runtime.CardIds.DWEBBLE, name="Dwebble", hp=70, max_hp=70, energies=[]),
        ],
        opponent_active=_fake_card(9911, name="Regular Pokemon", hp=200, max_hp=200, energies=[]),
        options=[],
    )
    obs.current.turn = 6
    obs.current.players[0].prize = [1, 2]
    obs.current.players[1].prize = [1, 2, 3, 4]

    state = deck_state_module.analyze_deck_state(obs)

    assert state.primary_plan == "close_pressure"


def test_crustle_kangaskhan_primary_plan_prefers_dragapult_bench_protection():
    runtime = _load_crustle_module("runtime")
    deck_state_module = _load_crustle_module("deck_state")

    obs = _fake_obs(
        hand=[],
        active=_fake_card(runtime.CardIds.CRUSTLE, name="Crustle", hp=140, max_hp=140, energies=[1]),
        bench=[_fake_card(runtime.CardIds.DWEBBLE, name="Dwebble", hp=40, max_hp=70)],
        opponent_active=_fake_card(9210, name="Dragapult ex", hp=320, max_hp=320, energies=[1, 1]),
    )

    state = deck_state_module.analyze_deck_state(obs)

    assert state.primary_plan == "protect_bench_vs_dragapult"


def test_crustle_kangaskhan_inference_filters_to_emergency_setup_actions():
    inference = _load_crustle_module("inference")
    runtime = _load_crustle_module("runtime")
    from cg.api import OptionType

    obs = _fake_obs(
        hand=[
            _fake_card(runtime.CardIds.BUDDY_BUDDY_POFFIN, name="Buddy-Buddy Poffin"),
            _fake_card(runtime.CardIds.ERI, name="Eri"),
        ],
        active=_fake_card(runtime.CardIds.MEGA_KANGASKHAN_EX, name="Mega Kangaskhan ex", hp=230, max_hp=230),
        bench=[_fake_card(runtime.CardIds.DWEBBLE, name="Dwebble", hp=70, max_hp=70)],
        opponent_active=_fake_card(9912, name="Mega Lucario ex", hp=220, max_hp=220, energies=[1]),
        options=[
            SimpleNamespace(type=OptionType.PLAY, index=0),
            SimpleNamespace(type=OptionType.PLAY, index=1),
        ],
    )
    obs.current.turn = 1
    scored = inference.score_actions(obs, None, use_policy=False)
    deck_state = _load_crustle_module("deck_state").analyze_deck_state(obs)

    filtered = inference.filter_scored_actions_for_emergency_setup(obs, scored, deck_state)

    assert [item.index for item in filtered] == [0]


def test_crustle_kangaskhan_context_chooser_hilda_prefers_crustle_grow_pair():
    context_chooser = _load_crustle_module("context_chooser")
    runtime = _load_crustle_module("runtime")
    from cg.api import AreaType, OptionType, SelectContext

    hilda = _fake_card(runtime.CardIds.HILDA, name="Hilda")
    obs = _fake_obs(
        hand=[hilda],
        active=_fake_card(runtime.CardIds.MEGA_KANGASKHAN_EX, name="Mega Kangaskhan ex"),
        bench=[],
        opponent_active=_fake_card(9920, name="Mega Lucario ex"),
        effect=hilda,
        context=SelectContext.TO_HAND,
        select_deck=[
            _fake_card(runtime.CardIds.CRUSTLE, name="Crustle"),
            _fake_card(runtime.CardIds.GROW_GRASS_ENERGY, name="Growing Grass Energy"),
            _fake_card(runtime.CardIds.BASIC_GRASS, name="Grass Energy"),
        ],
        options=[
            SimpleNamespace(type=OptionType.CARD, area=AreaType.DECK, index=0, playerIndex=0),
            SimpleNamespace(type=OptionType.CARD, area=AreaType.DECK, index=1, playerIndex=0),
            SimpleNamespace(type=OptionType.CARD, area=AreaType.DECK, index=2, playerIndex=0),
        ],
    )
    obs.select.maxCount = 2
    scored = [
        SimpleNamespace(index=0, total_logit=0.0),
        SimpleNamespace(index=1, total_logit=0.0),
        SimpleNamespace(index=2, total_logit=0.0),
    ]
    deck_state = SimpleNamespace(primary_plan="setup_crustle", setup_missing_crustle=True, dwebble_in_play=0)

    selected = context_chooser.choose_hilda_pair(obs, scored, deck_state, deck_knowledge=None)

    assert selected == [0, 1]


def test_crustle_kangaskhan_context_chooser_default_does_not_fill_negative_optional_slots():
    context_chooser = _load_crustle_module("context_chooser", agent_name="crustle_mega_kangaskhan_rule_rl_p1_v2")
    runtime = _load_crustle_module("runtime", agent_name="crustle_mega_kangaskhan_rule_rl_p1_v2")
    from cg.api import OptionType

    obs = _fake_obs(
        hand=[
            _fake_card(runtime.CardIds.BUDDY_BUDDY_POFFIN, name="Buddy-Buddy Poffin"),
            _fake_card(runtime.CardIds.LILLIE, name="Lillie"),
        ],
        active=_fake_card(runtime.CardIds.MEGA_KANGASKHAN_EX, name="Mega Kangaskhan ex"),
        bench=[],
        opponent_active=_fake_card(678, name="id:678", hp=300, max_hp=300, energies=[1, 1]),
        options=[
            SimpleNamespace(type=OptionType.PLAY, index=0),
            SimpleNamespace(type=OptionType.PLAY, index=1),
        ],
    )
    obs.select.minCount = 0
    obs.select.maxCount = 2
    scored = [
        SimpleNamespace(index=0, total_logit=50.0, prior={"total_logit": 50.0}),
        SimpleNamespace(index=1, total_logit=-10.0, prior={"total_logit": -10.0}),
    ]
    deck_state = SimpleNamespace(primary_plan="stabilize")

    selected = context_chooser.choose_actions_by_context(obs, scored, deck_state, deck_knowledge=None)

    assert selected == [0]


def test_crustle_kangaskhan_runtime_describe_option_explains_attach_target():
    runtime = _load_crustle_module("runtime", agent_name="crustle_mega_kangaskhan_rule_rl_p1_v2")
    from cg.api import AreaType, OptionType

    mist = _fake_card(runtime.CardIds.MIST_ENERGY, name="Mist Energy")
    dwebble = _fake_card(runtime.CardIds.DWEBBLE, name="Dwebble")
    obs = _fake_obs(
        hand=[mist],
        active=_fake_card(runtime.CardIds.MEGA_KANGASKHAN_EX, name="Mega Kangaskhan ex"),
        bench=[dwebble],
        opponent_active=_fake_card(121, name="id:121", hp=320, max_hp=320, energies=[]),
        options=[
            SimpleNamespace(type=OptionType.ATTACH, index=0, inPlayArea=AreaType.BENCH, inPlayIndex=0),
        ],
    )

    desc = runtime.describe_option(obs, obs.select.option[0])

    assert desc == "ATTACH Mist Energy -> Bench Dwebble"


def test_crustle_kangaskhan_v2_inference_uses_passed_snapshot_and_plan_without_deck_state(monkeypatch):
    inference = _load_crustle_module("inference", agent_name="crustle_mega_kangaskhan_rule_rl_p1_v2")
    turn_plan = _load_crustle_module("turn_plan", agent_name="crustle_mega_kangaskhan_rule_rl_p1_v2")
    runtime = _load_crustle_module("runtime", agent_name="crustle_mega_kangaskhan_rule_rl_p1_v2")
    from cg.api import OptionType

    obs = _fake_obs(
        hand=[_fake_card(runtime.CardIds.BUDDY_BUDDY_POFFIN, name="Buddy-Buddy Poffin")],
        active=_fake_card(runtime.CardIds.MEGA_KANGASKHAN_EX, name="Mega Kangaskhan ex", hp=230, max_hp=230),
        bench=[],
        opponent_active=_fake_card(678, name="id:678", hp=300, max_hp=300, energies=[1, 1]),
        options=[SimpleNamespace(type=OptionType.PLAY, index=0)],
    )
    snapshot, plan = turn_plan.build_turn_plan(obs)
    assert not hasattr(inference, "analyze_deck_state")
    scored = inference.score_actions(
        obs,
        None,
        use_policy=False,
        deck_knowledge=None,
        snapshot=snapshot,
        plan=plan,
    )

    assert scored


def test_crustle_kangaskhan_v2_main_path_no_longer_depends_on_deck_state(monkeypatch):
    agent_main = _load_crustle_module("main", agent_name="crustle_mega_kangaskhan_rule_rl_p1_v2")
    runtime = _load_crustle_module("runtime", agent_name="crustle_mega_kangaskhan_rule_rl_p1_v2")
    from cg.api import OptionType

    obs = _fake_obs(
        hand=[_fake_card(runtime.CardIds.BUDDY_BUDDY_POFFIN, name="Buddy-Buddy Poffin")],
        active=_fake_card(runtime.CardIds.MEGA_KANGASKHAN_EX, name="Mega Kangaskhan ex", hp=230, max_hp=230),
        bench=[],
        opponent_active=_fake_card(678, name="id:678", hp=300, max_hp=300, energies=[1, 1]),
        options=[SimpleNamespace(type=OptionType.PLAY, index=0)],
    )
    obs_dict = {
        "current": obs.current,
        "select": obs.select,
    }

    assert not hasattr(agent_main, "analyze_deck_state")
    monkeypatch.setattr(agent_main, "to_observation_class", lambda x: obs)
    selected = agent_main.agent(obs_dict)

    assert selected == [0]


def test_crustle_kangaskhan_context_chooser_poffin_prefers_dwebble_plus_kang():
    context_chooser = _load_crustle_module("context_chooser")
    runtime = _load_crustle_module("runtime")
    from cg.api import AreaType, OptionType, SelectContext

    poffin = _fake_card(runtime.CardIds.BUDDY_BUDDY_POFFIN, name="Buddy-Buddy Poffin")
    obs = _fake_obs(
        hand=[poffin],
        active=_fake_card(runtime.CardIds.MEGA_KANGASKHAN_EX, name="Mega Kangaskhan ex"),
        bench=[],
        opponent_active=_fake_card(9921, name="Mega Lucario ex"),
        effect=poffin,
        context=SelectContext.TO_BENCH,
        select_deck=[
            _fake_card(runtime.CardIds.DWEBBLE, name="Dwebble"),
            _fake_card(runtime.CardIds.MEGA_KANGASKHAN_EX, name="Mega Kangaskhan ex"),
            _fake_card(runtime.CardIds.DWEBBLE, name="Dwebble"),
        ],
        options=[
            SimpleNamespace(type=OptionType.CARD, area=AreaType.DECK, index=0, playerIndex=0),
            SimpleNamespace(type=OptionType.CARD, area=AreaType.DECK, index=1, playerIndex=0),
            SimpleNamespace(type=OptionType.CARD, area=AreaType.DECK, index=2, playerIndex=0),
        ],
    )
    obs.select.maxCount = 2
    scored = [
        SimpleNamespace(index=0, total_logit=0.0),
        SimpleNamespace(index=1, total_logit=0.0),
        SimpleNamespace(index=2, total_logit=0.0),
    ]
    deck_state = SimpleNamespace(must_bench_basic=True, setup_missing_crustle=True, kangaskhan_in_play=1)

    selected = context_chooser.choose_poffin_basics(obs, scored, deck_state)

    assert selected == [0, 1]


def test_crustle_kangaskhan_context_chooser_ultra_ball_uses_best_discards():
    context_chooser = _load_crustle_module("context_chooser")
    runtime = _load_crustle_module("runtime")
    from cg.api import AreaType, OptionType, SelectContext

    ultra_ball = _fake_card(runtime.CardIds.ULTRA_BALL, name="Ultra Ball")
    obs = _fake_obs(
        hand=[
            ultra_ball,
            _fake_card(runtime.CardIds.BASIC_GRASS, name="Grass Energy"),
            _fake_card(runtime.CardIds.MIST_ENERGY, name="Mist Energy"),
            _fake_card(runtime.CardIds.LILLIE, name="Lillie"),
        ],
        active=_fake_card(runtime.CardIds.MEGA_KANGASKHAN_EX, name="Mega Kangaskhan ex"),
        bench=[],
        opponent_active=_fake_card(9922, name="Dragapult ex"),
        effect=ultra_ball,
        context=SelectContext.DISCARD,
        options=[
            SimpleNamespace(type=OptionType.CARD, area=AreaType.HAND, index=1, playerIndex=0),
            SimpleNamespace(type=OptionType.CARD, area=AreaType.HAND, index=2, playerIndex=0),
            SimpleNamespace(type=OptionType.CARD, area=AreaType.HAND, index=3, playerIndex=0),
        ],
    )
    obs.select.maxCount = 2
    scored = [
        SimpleNamespace(index=0, total_logit=0.0),
        SimpleNamespace(index=1, total_logit=0.0),
        SimpleNamespace(index=2, total_logit=0.0),
    ]
    deck_state = SimpleNamespace(
        setup_missing_crustle=False,
        crustle_in_play=1,
        kangaskhan_in_play=1,
        matchup=SimpleNamespace(values_mist_energy=True),
    )

    selected = context_chooser.choose_ultra_ball_discards(obs, scored, deck_state)

    assert selected == [0, 2]


def test_crustle_kangaskhan_context_chooser_petrel_ignores_missing_finish_target():
    context_chooser = _load_crustle_module("context_chooser")
    runtime = _load_crustle_module("runtime")
    from cg.api import AreaType, OptionType, SelectContext

    petrel = _fake_card(runtime.CardIds.PETREL, name="Petrel")
    obs = _fake_obs(
        hand=[petrel],
        active=_fake_card(runtime.CardIds.MEGA_KANGASKHAN_EX, name="Mega Kangaskhan ex"),
        bench=[],
        opponent_active=_fake_card(9923, name="Regular Pokemon", hp=100, max_hp=100),
        effect=petrel,
        context=SelectContext.TO_HAND,
        select_deck=[
            _fake_card(runtime.CardIds.BOSS_ORDERS, name="Boss's Orders"),
            _fake_card(runtime.CardIds.LISIA, name="Lisia"),
        ],
        options=[
            SimpleNamespace(type=OptionType.CARD, area=AreaType.DECK, index=0, playerIndex=0),
            SimpleNamespace(type=OptionType.CARD, area=AreaType.DECK, index=1, playerIndex=0),
        ],
    )
    scored = [
        SimpleNamespace(index=0, total_logit=0.0),
        SimpleNamespace(index=1, total_logit=0.0),
    ]
    deck_state = SimpleNamespace(primary_plan="close_game", must_bench_basic=False)
    deck_knowledge = SimpleNamespace(deck_has=lambda card_id: False if card_id == runtime.CardIds.BOSS_ORDERS else True)

    selected = context_chooser.choose_petrel_target(obs, scored, deck_state, deck_knowledge)

    assert selected == [1]


def test_crustle_kangaskhan_line_progress_requires_real_missing_solution():
    line_evaluator = _load_crustle_module("line_evaluator")

    blocked_line = line_evaluator.LineState(
        name="crustle_wall",
        priority=1.2,
        is_online=False,
        missing={"crustle"},
        blocked=True,
        block_reasons=["crustle_not_in_deck"],
        tag_solves_missing={"hilda_crustle_grow": {"crustle"}},
        blocking_risks=set(),
    )
    live_line = line_evaluator.LineState(
        name="kang_tank",
        priority=1.0,
        is_online=False,
        missing={"kang"},
        blocked=False,
        block_reasons=[],
        tag_solves_missing={"bench_kang": {"kang"}},
        blocking_risks=set(),
    )

    blocked_score = line_evaluator.score_line_progress({"hilda_crustle_grow"}, [blocked_line])
    live_score = line_evaluator.score_line_progress({"bench_kang"}, [live_line])

    assert blocked_score == 0.0
    assert live_score > 0.0


def test_crustle_kangaskhan_rule_prior_petrel_does_not_beat_poffin_when_exposed():
    runtime = _load_crustle_module("runtime")
    rule_prior = _load_crustle_module("rule_prior")
    from cg.api import OptionType

    poffin = _fake_card(runtime.CardIds.BUDDY_BUDDY_POFFIN, name="Buddy-Buddy Poffin")
    petrel = _fake_card(runtime.CardIds.PETREL, name="Petrel")
    obs = _fake_obs(
        hand=[poffin, petrel],
        active=_fake_card(runtime.CardIds.MEGA_KANGASKHAN_EX, name="Mega Kangaskhan ex", hp=50, max_hp=230),
        bench=[],
        opponent_active=_fake_card(9211, name="Mega Lucario ex", hp=220, max_hp=220, energies=[1, 1]),
        options=[
            SimpleNamespace(type=OptionType.PLAY, index=0),
            SimpleNamespace(type=OptionType.PLAY, index=1),
        ],
    )

    poffin_result = rule_prior.score_option(obs, obs.select.option[0])
    petrel_result = rule_prior.score_option(obs, obs.select.option[1])

    assert poffin_result["total_logit"] > petrel_result["total_logit"]


def test_crustle_kangaskhan_rule_prior_penalizes_attack_before_setup_threshold():
    runtime = _load_crustle_module("runtime")
    rule_prior = _load_crustle_module("rule_prior")
    from cg.api import OptionType

    poffin = _fake_card(runtime.CardIds.BUDDY_BUDDY_POFFIN, name="Buddy-Buddy Poffin")
    obs = _fake_obs(
        hand=[poffin],
        active=_fake_card(runtime.CardIds.DWEBBLE, name="Dwebble", hp=70, max_hp=70),
        bench=[],
        opponent_active=_fake_card(9212, name="Mega Lucario ex", hp=220, max_hp=220, energies=[1]),
        options=[
            SimpleNamespace(type=OptionType.PLAY, index=0),
            SimpleNamespace(type=OptionType.ATTACK),
        ],
    )

    play_result = rule_prior.score_option(obs, obs.select.option[0])
    attack_result = rule_prior.score_option(obs, obs.select.option[1])

    assert play_result["total_logit"] > attack_result["total_logit"]
    assert "attack_before_setup" in attack_result["reason_tags"]


def test_crustle_kangaskhan_rule_prior_forbids_ascension_before_benching_backup():
    runtime = _load_crustle_module("runtime")
    rule_prior = _load_crustle_module("rule_prior")
    from cg.api import OptionType

    poffin = _fake_card(runtime.CardIds.BUDDY_BUDDY_POFFIN, name="Buddy-Buddy Poffin")
    obs = _fake_obs(
        hand=[poffin],
        active=_fake_card(runtime.CardIds.DWEBBLE, name="Dwebble", hp=70, max_hp=70),
        bench=[],
        opponent_active=_fake_card(9924, name="Mega Lucario ex", hp=220, max_hp=220, energies=[1]),
        options=[
            SimpleNamespace(type=OptionType.PLAY, index=0),
            SimpleNamespace(type=OptionType.ATTACK),
        ],
    )

    play_result = rule_prior.score_option(obs, obs.select.option[0])
    attack_result = rule_prior.score_option(obs, obs.select.option[1])

    assert play_result["total_logit"] > attack_result["total_logit"]
    assert "ascension_before_bench_forbidden" in attack_result["reason_tags"]


def test_crustle_kangaskhan_selection_scorer_gust_for_win_requires_real_ko():
    runtime = _load_crustle_module("runtime")
    selection_scorer = _load_crustle_module("selection_scorer")

    deck_state = SimpleNamespace(
        gust_for_win=True,
        my_prizes_left=2,
        current_attack_damage=100,
        matchup=SimpleNamespace(values_gust_on_setup_targets=False),
    )
    low_hp_ex = _fake_card(9203, name="Support ex", hp=90, max_hp=220, energies=[])
    high_hp_ex = _fake_card(9204, name="Tank ex", hp=180, max_hp=220, energies=[])

    ko_score, ko_tag = selection_scorer.score_gust_target(low_hp_ex, deck_state)
    miss_score, miss_tag = selection_scorer.score_gust_target(high_hp_ex, deck_state)

    assert ko_tag == "gust_for_win"
    assert ko_score > miss_score
    assert miss_tag != "gust_for_win"


def test_crustle_kangaskhan_rule_prior_uses_real_ultra_ball_discard_target():
    runtime = _load_crustle_module("runtime")
    rule_prior = _load_crustle_module("rule_prior")
    from cg.api import AreaType, OptionType, SelectContext

    ultra_ball = _fake_card(runtime.CardIds.ULTRA_BALL, name="Ultra Ball")
    hero_cape = _fake_card(runtime.CardIds.HERO_CAPE, name="Hero's Cape")
    basic_grass = _fake_card(runtime.CardIds.BASIC_GRASS, name="Grass Energy")
    obs = _fake_obs(
        hand=[ultra_ball, hero_cape, basic_grass],
        active=_fake_card(runtime.CardIds.MEGA_KANGASKHAN_EX, name="Mega Kangaskhan ex", hp=230, max_hp=230),
        bench=[],
        opponent_active=_fake_card(9205, name="Unknown Attacker", hp=170, max_hp=170, energies=[1]),
        effect=ultra_ball,
        context=SelectContext.DISCARD,
        options=[
            SimpleNamespace(type=OptionType.CARD, area=AreaType.HAND, index=1, playerIndex=0),
            SimpleNamespace(type=OptionType.CARD, area=AreaType.HAND, index=2, playerIndex=0),
        ],
    )

    hero_result = rule_prior.score_option(obs, obs.select.option[0])
    basic_result = rule_prior.score_option(obs, obs.select.option[1])

    assert hero_result["breakdown"].get("risk", 0.0) < basic_result["breakdown"].get("risk", 0.0)
    assert "protect_one_of" in hero_result["reason_tags"]


def test_crustle_kangaskhan_rule_prior_spiky_energy_prefers_active_tank():
    runtime = _load_crustle_module("runtime")
    rule_prior = _load_crustle_module("rule_prior")
    from cg.api import AreaType, OptionType

    spiky = _fake_card(runtime.CardIds.SPIKY_ENERGY, name="Spiky Energy")
    active_kang = _fake_card(runtime.CardIds.MEGA_KANGASKHAN_EX, name="Mega Kangaskhan ex", hp=230, max_hp=230)
    bench_kang = _fake_card(runtime.CardIds.MEGA_KANGASKHAN_EX, name="Mega Kangaskhan ex", hp=230, max_hp=230)
    obs = _fake_obs(
        hand=[spiky],
        active=active_kang,
        bench=[bench_kang],
        opponent_active=_fake_card(9206, name="Unknown Attacker", hp=170, max_hp=170, energies=[1]),
        options=[
            SimpleNamespace(type=OptionType.ATTACH, index=0, inPlayArea=AreaType.ACTIVE, inPlayIndex=0),
            SimpleNamespace(type=OptionType.ATTACH, index=0, inPlayArea=AreaType.BENCH, inPlayIndex=0),
        ],
    )

    active_result = rule_prior.score_option(obs, obs.select.option[0])
    bench_result = rule_prior.score_option(obs, obs.select.option[1])

    assert active_result["total_logit"] > bench_result["total_logit"]
    assert "spiky_tank" in active_result["reason_tags"]


def test_crustle_kangaskhan_v2_turn_plan_prefers_survival_setup_when_field_thin():
    turn_plan = _load_crustle_module("turn_plan", agent_name="crustle_mega_kangaskhan_rule_rl_p1_v2")

    obs = _fake_obs(
        hand=[],
        active=_fake_card(1122, name="Single Basic", hp=60, max_hp=60),
        bench=[],
        opponent_active=_fake_card(9307, name="Mega Lucario ex", hp=220, max_hp=220, energies=[1, 1]),
        options=[],
    )

    _, plan = turn_plan.build_turn_plan(obs)

    assert plan.mode == "survival_setup"


def test_crustle_kangaskhan_v2_turn_plan_only_marks_wall_now_when_wall_is_actually_available():
    runtime = _load_crustle_module("runtime", agent_name="crustle_mega_kangaskhan_rule_rl_p1_v2")
    turn_plan = _load_crustle_module("turn_plan", agent_name="crustle_mega_kangaskhan_rule_rl_p1_v2")
    from cg.api import OptionType

    obs = _fake_obs(
        hand=[],
        active=_fake_card(runtime.CardIds.DWEBBLE, name="Dwebble", hp=70, max_hp=70, energies=[]),
        bench=[_fake_card(runtime.CardIds.MEGA_KANGASKHAN_EX, name="Mega Kangaskhan ex", hp=230, max_hp=230)],
        opponent_active=_fake_card(9308, name="Mega Lucario ex", hp=220, max_hp=220, energies=[1]),
        options=[SimpleNamespace(type=OptionType.END)],
    )

    _, plan = turn_plan.build_turn_plan(obs)

    assert plan.mode != "setup_crustle_wall_now"


def test_crustle_kangaskhan_v2_turn_plan_prefers_finish_for_verified_active_ko():
    runtime = _load_crustle_module("runtime", agent_name="crustle_mega_kangaskhan_rule_rl_p1_v2")
    turn_plan = _load_crustle_module("turn_plan", agent_name="crustle_mega_kangaskhan_rule_rl_p1_v2")
    from cg.api import OptionType

    obs = _fake_obs(
        hand=[],
        active=_fake_card(runtime.CardIds.MEGA_KANGASKHAN_EX, name="Mega Kangaskhan ex", hp=230, max_hp=230, energies=[1, 1, 1]),
        bench=[],
        opponent_active=_fake_card(9309, name="Support ex", hp=180, max_hp=180, energies=[]),
        options=[SimpleNamespace(type=OptionType.ATTACK)],
    )
    obs.current.players[0].prize = [1, 2]
    obs.current.players[1].prize = [1]

    _, plan = turn_plan.build_turn_plan(obs)

    assert plan.mode == "finish"


def test_crustle_kangaskhan_v2_evaluate_builds_records_with_v2_agent_name():
    module = load_module(
        "crustle_kangaskhan_v2_evaluate_module",
        ROOT / "agents" / "crustle_mega_kangaskhan_rule_rl_p1_v2" / "evaluate.py",
    )

    result = {
        "agent_a": "crustle_mega_kangaskhan_rule_rl_p1_v2",
        "agent_b": "mega_lucario_beginner",
        "winner": 0,
        "steps": 10,
        "turn": 3,
        "status": "success",
        "termination": {"reason_key": "prize_out", "reason_code": 1},
    }

    record = module._build_game_record(result, "mega_lucario_beginner", 0, "v2_test")

    assert record["outcome"] == "win"
    assert record["score"] == 1.0


def test_crustle_kangaskhan_v2_evaluate_runs_matches_with_v2_agent_name(monkeypatch):
    module = load_module(
        "crustle_kangaskhan_v2_evaluate_module_run_match",
        ROOT / "agents" / "crustle_mega_kangaskhan_rule_rl_p1_v2" / "evaluate.py",
    )

    calls = []

    def fake_play_match(left, right, verbose=False, capture_details=False):
        calls.append((left, right))
        return {
            "status": "success",
            "winner": 0,
            "agent_a": left,
            "agent_b": right,
            "steps": 10,
            "turn": 3,
            "termination": {"reason_key": "prize_out", "reason_code": 1},
        }

    monkeypatch.setattr(module, "play_match", fake_play_match)

    result, won = module._run_match("mega_lucario_beginner", 0)

    assert calls[0][0] == "crustle_mega_kangaskhan_rule_rl_p1_v2"
    assert won is True
    assert result["agent_a"] == "crustle_mega_kangaskhan_rule_rl_p1_v2"


def test_crustle_kangaskhan_v2_runtime_marks_hidden_id_ex_as_ex():
    runtime = _load_crustle_module("runtime", agent_name="crustle_mega_kangaskhan_rule_rl_p1_v2")

    hidden_lucario_ex = _fake_card(678, name="id:678", hp=340, max_hp=340)
    hidden_dragapult_ex = _fake_card(121, name="id:121", hp=320, max_hp=320)

    assert runtime.is_ex_card(hidden_lucario_ex) is True
    assert runtime.is_ex_card(hidden_dragapult_ex) is True


def test_crustle_kangaskhan_v2_matchup_profile_detects_hidden_id_lucario_and_dragapult():
    matchup_profile = _load_crustle_module("matchup_profile", agent_name="crustle_mega_kangaskhan_rule_rl_p1_v2")

    lucario_obs = _fake_obs(
        hand=[],
        active=_fake_card(756, name="Mega Kangaskhan ex"),
        bench=[],
        opponent_active=_fake_card(678, name="id:678", hp=340, max_hp=340),
    )
    dragapult_obs = _fake_obs(
        hand=[],
        active=_fake_card(756, name="Mega Kangaskhan ex"),
        bench=[],
        opponent_active=_fake_card(121, name="id:121", hp=320, max_hp=320),
    )

    lucario = matchup_profile.detect_matchup_profile(lucario_obs)
    dragapult = matchup_profile.detect_matchup_profile(dragapult_obs)

    assert lucario.name == "mega_lucario"
    assert lucario.prefers_crustle_wall is True
    assert dragapult.name == "dragapult_ex"
    assert dragapult.values_mist_energy is True


def test_crustle_kangaskhan_v2_turn_plan_prefers_crustle_setup_into_hidden_id_ex():
    runtime = _load_crustle_module("runtime", agent_name="crustle_mega_kangaskhan_rule_rl_p1_v2")
    turn_plan = _load_crustle_module("turn_plan", agent_name="crustle_mega_kangaskhan_rule_rl_p1_v2")
    from cg.api import OptionType

    obs = _fake_obs(
        hand=[_fake_card(runtime.CardIds.BUDDY_BUDDY_POFFIN, name="Buddy-Buddy Poffin")],
        active=_fake_card(runtime.CardIds.MEGA_KANGASKHAN_EX, name="Mega Kangaskhan ex", hp=230, max_hp=230, energies=[]),
        bench=[],
        opponent_active=_fake_card(678, name="id:678", hp=340, max_hp=340, energies=[1]),
        options=[SimpleNamespace(type=OptionType.PLAY, index=0)],
    )

    _, plan = turn_plan.build_turn_plan(obs)

    assert plan.mode in {"survival_setup", "setup_crustle", "setup_crustle_wall_now"}
    assert plan.mode != "kang_engine"


def test_crustle_kangaskhan_v2_rule_prior_avoids_switching_only_dwebble_active_before_wall_ready():
    runtime = _load_crustle_module("runtime", agent_name="crustle_mega_kangaskhan_rule_rl_p1_v2")
    rule_prior = _load_crustle_module("rule_prior", agent_name="crustle_mega_kangaskhan_rule_rl_p1_v2")
    from cg.api import OptionType

    switch = _fake_card(runtime.CardIds.SWITCH, name="Switch")
    obs = _fake_obs(
        hand=[switch],
        active=_fake_card(runtime.CardIds.MEGA_KANGASKHAN_EX, name="Mega Kangaskhan ex", hp=230, max_hp=230, energies=[]),
        bench=[_fake_card(runtime.CardIds.DWEBBLE, name="Dwebble", hp=70, max_hp=70, energies=[])],
        opponent_active=_fake_card(678, name="id:678", hp=300, max_hp=300, energies=[1, 1]),
        options=[
            SimpleNamespace(type=OptionType.PLAY, index=0),
            SimpleNamespace(type=OptionType.ABILITY, area=4, index=0),
            SimpleNamespace(type=OptionType.END),
        ],
    )
    obs.current.turn = 1

    switch_result = rule_prior.score_option(obs, obs.select.option[0])
    ability_result = rule_prior.score_option(obs, obs.select.option[1])

    assert ability_result["total_logit"] > switch_result["total_logit"]
    assert "avoid_switch_expose_dwebble" in switch_result["reason_tags"]


def test_crustle_kangaskhan_v2_selection_scorer_prefers_crustle_over_dwebble_for_switch():
    runtime = _load_crustle_module("runtime", agent_name="crustle_mega_kangaskhan_rule_rl_p1_v2")
    selection_scorer = _load_crustle_module("selection_scorer", agent_name="crustle_mega_kangaskhan_rule_rl_p1_v2")

    deck_state = SimpleNamespace(
        turn_plan=SimpleNamespace(switch_target_role="crustle"),
    )

    crustle_score, crustle_tag = selection_scorer.score_switch_target(runtime.CardIds.CRUSTLE, deck_state)
    dwebble_score, dwebble_tag = selection_scorer.score_switch_target(runtime.CardIds.DWEBBLE, deck_state)

    assert crustle_score > dwebble_score
    assert crustle_tag == "switch_plan_target"
    assert dwebble_tag == "avoid_expose_dwebble"


def test_crustle_kangaskhan_v2_rule_prior_prefers_petrel_over_attach_when_must_bench_basic():
    runtime = _load_crustle_module("runtime", agent_name="crustle_mega_kangaskhan_rule_rl_p1_v2")
    rule_prior = _load_crustle_module("rule_prior", agent_name="crustle_mega_kangaskhan_rule_rl_p1_v2")
    from cg.api import OptionType

    spiky = _fake_card(runtime.CardIds.SPIKY_ENERGY, name="Spiky Energy")
    petrel = _fake_card(runtime.CardIds.PETREL, name="Petrel")
    obs = _fake_obs(
        hand=[spiky, petrel],
        active=_fake_card(runtime.CardIds.MEGA_KANGASKHAN_EX, name="Mega Kangaskhan ex", hp=230, max_hp=230, energies=[]),
        bench=[],
        opponent_active=_fake_card(678, name="id:678", hp=300, max_hp=300, energies=[1, 1]),
        options=[
            SimpleNamespace(type=OptionType.ATTACH, index=0, inPlayArea=4, inPlayIndex=0),
            SimpleNamespace(type=OptionType.PLAY, index=1),
            SimpleNamespace(type=OptionType.ABILITY, area=4, index=0),
        ],
    )
    obs.current.turn = 1

    attach_result = rule_prior.score_option(obs, obs.select.option[0])
    petrel_result = rule_prior.score_option(obs, obs.select.option[1])
    ability_result = rule_prior.score_option(obs, obs.select.option[2])

    assert petrel_result["total_logit"] > attach_result["total_logit"]
    assert petrel_result["total_logit"] > ability_result["total_logit"]
    assert "attach_before_bench_forbidden" in attach_result["reason_tags"]
    assert "draw_before_bench_forbidden" in ability_result["reason_tags"]


def test_crustle_kangaskhan_v2_selection_scorer_petrel_prefers_poffin_in_survival_setup():
    runtime = _load_crustle_module("runtime", agent_name="crustle_mega_kangaskhan_rule_rl_p1_v2")
    selection_scorer = _load_crustle_module("selection_scorer", agent_name="crustle_mega_kangaskhan_rule_rl_p1_v2")

    deck_state = SimpleNamespace(
        turn_plan=SimpleNamespace(
            petrel_target_ids=[
                runtime.CardIds.BUDDY_BUDDY_POFFIN,
                runtime.CardIds.ULTRA_BALL,
                runtime.CardIds.HILDA,
            ]
        )
    )

    poffin_score, poffin_tag = selection_scorer.score_petrel_target(runtime.CardIds.BUDDY_BUDDY_POFFIN, deck_state)
    hilda_score, hilda_tag = selection_scorer.score_petrel_target(runtime.CardIds.HILDA, deck_state)
    ultra_score, ultra_tag = selection_scorer.score_petrel_target(runtime.CardIds.ULTRA_BALL, deck_state)

    assert poffin_score > ultra_score > hilda_score
    assert poffin_tag == "petrel_top_plan_target"
    assert ultra_tag == "petrel_plan_target"
    assert hilda_tag == "petrel_plan_target"


def test_crustle_kangaskhan_v2_selection_scorer_petrel_follows_turn_plan_heal_goal():
    runtime = _load_crustle_module("runtime", agent_name="crustle_mega_kangaskhan_rule_rl_p1_v2")
    selection_scorer = _load_crustle_module("selection_scorer", agent_name="crustle_mega_kangaskhan_rule_rl_p1_v2")

    deck_state = SimpleNamespace(
        turn_plan=SimpleNamespace(
            mode="tank_and_heal",
            heal_card=runtime.CardIds.JUMBO_ICE_CREAM,
            petrel_target_ids=[runtime.CardIds.JUMBO_ICE_CREAM, runtime.CardIds.HERO_CAPE],
        ),
    )

    jumbo_score, jumbo_tag = selection_scorer.score_petrel_target(runtime.CardIds.JUMBO_ICE_CREAM, deck_state)
    cape_score, cape_tag = selection_scorer.score_petrel_target(runtime.CardIds.HERO_CAPE, deck_state)

    assert jumbo_score > cape_score
    assert jumbo_tag == "petrel_heal_target"
    assert cape_tag == "petrel_plan_target"


def test_crustle_kangaskhan_v2_selection_scorer_does_not_use_primary_plan_fallback_without_turn_plan():
    runtime = _load_crustle_module("runtime", agent_name="crustle_mega_kangaskhan_rule_rl_p1_v2")
    selection_scorer = _load_crustle_module("selection_scorer", agent_name="crustle_mega_kangaskhan_rule_rl_p1_v2")

    deck_state = SimpleNamespace(primary_plan="tank_and_heal", must_bench_basic=False)

    jumbo_score, jumbo_tag = selection_scorer.score_petrel_target(runtime.CardIds.JUMBO_ICE_CREAM, deck_state)
    crustle_score, crustle_tag = selection_scorer.score_switch_target(runtime.CardIds.CRUSTLE, deck_state)

    assert jumbo_score < 0.0
    assert jumbo_tag is None
    assert crustle_score < 20.0
    assert crustle_tag is None


def test_crustle_kangaskhan_v2_turn_plan_prefers_dragapult_bench_protection_when_bench_at_risk():
    runtime = _load_crustle_module("runtime", agent_name="crustle_mega_kangaskhan_rule_rl_p1_v2")
    turn_plan = _load_crustle_module("turn_plan", agent_name="crustle_mega_kangaskhan_rule_rl_p1_v2")

    obs = _fake_obs(
        hand=[],
        active=_fake_card(runtime.CardIds.MEGA_KANGASKHAN_EX, name="Mega Kangaskhan ex", hp=230, max_hp=230, energies=[1]),
        bench=[_fake_card(runtime.CardIds.DWEBBLE, name="Dwebble", hp=40, max_hp=70, energies=[])],
        opponent_active=_fake_card(121, name="id:121", hp=320, max_hp=320, energies=[]),
        options=[],
    )
    obs.current.turn = 6
    obs.current.players[1].prize = [1, 2, 3, 4]

    _, plan = turn_plan.build_turn_plan(obs)

    assert plan.mode == "protect_bench_vs_dragapult"
    assert plan.search_goal in {"mist_or_evolve", "mist"}
    assert "bench_under_dragapult_pressure" in plan.reasons


def test_crustle_kangaskhan_v2_turn_plan_prefers_tank_and_heal_when_jumbo_escapes_ko():
    runtime = _load_crustle_module("runtime", agent_name="crustle_mega_kangaskhan_rule_rl_p1_v2")
    turn_plan = _load_crustle_module("turn_plan", agent_name="crustle_mega_kangaskhan_rule_rl_p1_v2")

    obs = _fake_obs(
        hand=[_fake_card(runtime.CardIds.JUMBO_ICE_CREAM, name="Jumbo Ice Cream")],
        active=_fake_card(
            runtime.CardIds.MEGA_KANGASKHAN_EX,
            name="Mega Kangaskhan ex",
            hp=220,
            max_hp=230,
            energies=[1, 1, 1],
        ),
        bench=[
            _fake_card(runtime.CardIds.DWEBBLE, name="Dwebble", hp=70, max_hp=70, energies=[]),
            _fake_card(runtime.CardIds.DWEBBLE, name="Dwebble", hp=70, max_hp=70, energies=[]),
        ],
        opponent_active=_fake_card(678, name="id:678", hp=340, max_hp=340, energies=[1, 1]),
        options=[],
    )
    obs.current.turn = 6
    obs.current.players[0].prize = [1, 2, 3]
    obs.current.players[1].prize = [1, 2, 3, 4]

    _, plan = turn_plan.build_turn_plan(obs)

    assert plan.mode == "tank_and_heal"
    assert plan.heal_card == runtime.CardIds.JUMBO_ICE_CREAM
    assert "jumbo_escape_ko" in plan.reasons


def test_crustle_kangaskhan_v2_line_evaluator_exposes_expanded_line_states():
    runtime = _load_crustle_module("runtime", agent_name="crustle_mega_kangaskhan_rule_rl_p1_v2")
    line_evaluator = _load_crustle_module("line_evaluator", agent_name="crustle_mega_kangaskhan_rule_rl_p1_v2")

    deck_state = SimpleNamespace(
        wall_online=False,
        dwebble_in_play=0,
        setup_missing_crustle=True,
        crustle_in_play=0,
        kangaskhan_in_play=1,
        active_is_kangaskhan=True,
        active_energy=2,
        bench_risk=True,
        heal_prevents_ko=True,
        bianca_window=False,
        disruption_window=True,
        gust_for_win=False,
        gust_for_prize=True,
        my_prizes_left=2,
        can_attack_now=True,
        must_bench_basic=False,
        active_is_crustle=False,
        active_under_ko_threat=True,
        gust_for_stall=False,
    )
    matchup = SimpleNamespace(
        name="dragapult_ex",
        prefers_crustle_wall=True,
        values_bench_protection=True,
    )
    active = _fake_card(runtime.CardIds.MEGA_KANGASKHAN_EX, name="Mega Kangaskhan ex", hp=60, max_hp=230, energies=[1, 1, 1])
    opponent_active = _fake_card(121, name="id:121", hp=320, max_hp=320, energies=[1, 1])

    line_states = line_evaluator.build_line_states(deck_state, matchup, active, opponent_active, deck_knowledge=None)
    names = {line.name for line in line_states}

    assert {"crustle_wall", "kang_tank", "heal_escape", "disruption", "close_game", "attack_continuity", "dragapult_protect"} <= names


def test_crustle_kangaskhan_v2_context_chooser_eri_discards_key_item_first():
    runtime = _load_crustle_module("runtime", agent_name="crustle_mega_kangaskhan_rule_rl_p1_v2")
    context_chooser = _load_crustle_module("context_chooser", agent_name="crustle_mega_kangaskhan_rule_rl_p1_v2")
    from cg.api import AreaType, OptionType, SelectContext

    eri = _fake_card(runtime.CardIds.ERI, name="Eri")
    switch = _fake_card(runtime.CardIds.SWITCH, name="Switch")
    grass = _fake_card(runtime.CardIds.BASIC_GRASS, name="Grass Energy")
    obs = _fake_obs(
        hand=[eri],
        active=_fake_card(runtime.CardIds.CRUSTLE, name="Crustle", hp=120, max_hp=120, energies=[1]),
        bench=[],
        opponent_active=_fake_card(678, name="id:678", hp=300, max_hp=300, energies=[1, 1]),
        effect=eri,
        context=SelectContext.DISCARD,
        options=[
            SimpleNamespace(type=OptionType.CARD, area=AreaType.HAND, playerIndex=1, index=0),
            SimpleNamespace(type=OptionType.CARD, area=AreaType.HAND, playerIndex=1, index=1),
        ],
    )
    obs.current.players[0].prize = [1, 2, 3]
    obs.current.players[1].prize = [1, 2, 3, 4, 5]
    obs.current.players[1].hand = [switch, grass]
    obs.current.players[1].handCount = 2
    deck_state = SimpleNamespace(primary_plan="wall_and_tax", matchup=SimpleNamespace(values_disruption=True))
    scored = [
        SimpleNamespace(index=0, total_logit=0.0, prior={"total_logit": 0.0}),
        SimpleNamespace(index=1, total_logit=0.0, prior={"total_logit": 0.0}),
    ]

    selected = context_chooser.choose_actions_by_context(obs, scored, deck_state, deck_knowledge=None)

    assert selected == [0]


def test_crustle_kangaskhan_v2_rule_prior_applies_turn_plan_required_tags():
    runtime = _load_crustle_module("runtime", agent_name="crustle_mega_kangaskhan_rule_rl_p1_v2")
    rule_prior = _load_crustle_module("rule_prior", agent_name="crustle_mega_kangaskhan_rule_rl_p1_v2")
    turn_plan = _load_crustle_module("turn_plan", agent_name="crustle_mega_kangaskhan_rule_rl_p1_v2")
    from cg.api import OptionType

    poffin = _fake_card(runtime.CardIds.BUDDY_BUDDY_POFFIN, name="Buddy-Buddy Poffin")
    lillie = _fake_card(runtime.CardIds.LILLIE, name="Lillie")
    obs = _fake_obs(
        hand=[poffin, lillie],
        active=_fake_card(runtime.CardIds.MEGA_KANGASKHAN_EX, name="Mega Kangaskhan ex", hp=230, max_hp=230, energies=[]),
        bench=[],
        opponent_active=_fake_card(678, name="id:678", hp=300, max_hp=300, energies=[1, 1]),
        options=[
            SimpleNamespace(type=OptionType.PLAY, index=0),
            SimpleNamespace(type=OptionType.PLAY, index=1),
        ],
    )
    obs.current.turn = 1
    obs.current.players[0].prize = [1, 2, 3, 4, 5, 6]
    obs.current.players[1].prize = [1, 2, 3, 4, 5, 6]

    _, plan = turn_plan.build_turn_plan(obs)
    assert plan.mode == "survival_setup"
    assert "open_setup_search" in plan.required_tags

    poffin_result = rule_prior.score_option(obs, obs.select.option[0])
    lillie_result = rule_prior.score_option(obs, obs.select.option[1])

    assert poffin_result["total_logit"] > lillie_result["total_logit"]
    assert "required_open_setup_search" in poffin_result["reason_tags"]


def test_crustle_kangaskhan_v2_debug_logger_writes_plan_and_top_actions(tmp_path: Path):
    runtime = _load_crustle_module("runtime", agent_name="crustle_mega_kangaskhan_rule_rl_p1_v2")
    debug_logger = _load_crustle_module("debug_logger", agent_name="crustle_mega_kangaskhan_rule_rl_p1_v2")
    from cg.api import OptionType, SelectContext

    poffin = _fake_card(runtime.CardIds.BUDDY_BUDDY_POFFIN, name="Buddy-Buddy Poffin")
    obs = _fake_obs(
        hand=[poffin],
        active=_fake_card(runtime.CardIds.MEGA_KANGASKHAN_EX, name="Mega Kangaskhan ex", hp=230, max_hp=230),
        bench=[],
        opponent_active=_fake_card(678, name="id:678", hp=340, max_hp=340, energies=[1]),
        options=[SimpleNamespace(type=OptionType.PLAY, index=0)],
        context=SelectContext.MAIN,
    )
    snapshot = SimpleNamespace(field_count=1, wall_online=False, active_under_ko_threat=False, bench_space=5)
    plan = SimpleNamespace(mode="survival_setup", reasons=["field_too_thin"])
    scored = [
        SimpleNamespace(
            index=0,
            total_logit=420.0,
            prior={"reason_tags": ["play_poffin", "search_basic"], "breakdown": {"survival_setup": 300.0}},
        )
    ]
    selected = [0]
    log_path = tmp_path / "rule_debug.jsonl"

    debug_logger.log_rule_decision(obs, snapshot, plan, scored, selected, path=log_path)

    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["mode"] == "survival_setup"
    assert payload["plan_reason"] == "field_too_thin"
    assert payload["selected"] == [0]
    assert payload["top_actions"][0]["desc"] == "PLAY Buddy-Buddy Poffin"


def test_crustle_kangaskhan_v2_finish_search_returns_verified_attack_finish():
    runtime = _load_crustle_module("runtime", agent_name="crustle_mega_kangaskhan_rule_rl_p1_v2")
    finish_search = _load_crustle_module("finish_search", agent_name="crustle_mega_kangaskhan_rule_rl_p1_v2")
    turn_plan = _load_crustle_module("turn_plan", agent_name="crustle_mega_kangaskhan_rule_rl_p1_v2")
    from cg.api import OptionType

    obs = _fake_obs(
        hand=[],
        active=_fake_card(
            runtime.CardIds.MEGA_KANGASKHAN_EX,
            name="Mega Kangaskhan ex",
            hp=230,
            max_hp=230,
            energies=[1, 1, 1],
        ),
        bench=[
            _fake_card(runtime.CardIds.DWEBBLE, name="Dwebble", hp=70, max_hp=70, energies=[]),
            _fake_card(runtime.CardIds.DWEBBLE, name="Dwebble", hp=70, max_hp=70, energies=[]),
        ],
        opponent_active=_fake_card(9901, name="Target ex", hp=180, max_hp=180, energies=[]),
        options=[SimpleNamespace(type=OptionType.ATTACK)],
    )
    obs.current.players[0].prize = [1]
    obs.current.players[1].prize = [1, 2, 3]
    snapshot, plan = turn_plan.build_turn_plan(obs)

    selected = finish_search.try_finish_search(obs, snapshot, plan, deck_knowledge=None)

    assert selected == [0]


def test_crustle_kangaskhan_v2_emergency_gate_keeps_only_basic_setup_actions():
    emergency_gate = _load_crustle_module("emergency_gate", agent_name="crustle_mega_kangaskhan_rule_rl_p1_v2")
    runtime = _load_crustle_module("runtime", agent_name="crustle_mega_kangaskhan_rule_rl_p1_v2")
    from cg.api import OptionType

    poffin = _fake_card(runtime.CardIds.BUDDY_BUDDY_POFFIN, name="Buddy-Buddy Poffin")
    obs = _fake_obs(
        hand=[poffin],
        active=_fake_card(runtime.CardIds.DWEBBLE, name="Dwebble", hp=70, max_hp=70, energies=[]),
        bench=[],
        opponent_active=_fake_card(678, name="id:678", hp=340, max_hp=340, energies=[1, 1]),
        options=[
            SimpleNamespace(type=OptionType.PLAY, index=0),
            SimpleNamespace(type=OptionType.ATTACK),
            SimpleNamespace(type=OptionType.END),
        ],
    )
    snapshot = SimpleNamespace()
    plan = SimpleNamespace(mode="survival_setup")
    scored = [
        SimpleNamespace(index=1, total_logit=500.0, prior={"reason_tags": ["attack_end_turn"]}),
        SimpleNamespace(index=0, total_logit=300.0, prior={"reason_tags": ["play_poffin", "search_basic"]}),
        SimpleNamespace(index=2, total_logit=100.0, prior={"reason_tags": ["end_turn"]}),
    ]

    filtered = emergency_gate.filter_emergency_actions(obs, scored, snapshot, plan)

    assert [item.index for item in filtered] == [0]


def test_crustle_kangaskhan_v2_finish_search_can_start_verified_petrel_finish():
    runtime = _load_crustle_module("runtime", agent_name="crustle_mega_kangaskhan_rule_rl_p1_v2")
    finish_search = _load_crustle_module("finish_search", agent_name="crustle_mega_kangaskhan_rule_rl_p1_v2")
    turn_plan = _load_crustle_module("turn_plan", agent_name="crustle_mega_kangaskhan_rule_rl_p1_v2")
    from cg.api import OptionType

    class FakeKnowledge:
        def deck_has(self, card_id):
            return card_id in {runtime.CardIds.BOSS_ORDERS, runtime.CardIds.LISIA}

    petrel = _fake_card(runtime.CardIds.PETREL, name="Petrel")
    obs = _fake_obs(
        hand=[petrel],
        active=_fake_card(
            runtime.CardIds.MEGA_KANGASKHAN_EX,
            name="Mega Kangaskhan ex",
            hp=230,
            max_hp=230,
            energies=[1, 1, 1],
        ),
        bench=[
            _fake_card(runtime.CardIds.DWEBBLE, name="Dwebble", hp=70, max_hp=70, energies=[]),
            _fake_card(runtime.CardIds.DWEBBLE, name="Dwebble", hp=70, max_hp=70, energies=[]),
        ],
        opponent_active=_fake_card(9902, name="Active ex", hp=250, max_hp=250, energies=[]),
        opponent_bench=[_fake_card(9903, name="Bench ex", hp=180, max_hp=180, energies=[])],
        options=[
            SimpleNamespace(type=OptionType.PLAY, index=0),
            SimpleNamespace(type=OptionType.ATTACK),
        ],
    )
    obs.current.players[0].prize = [1]
    obs.current.players[1].prize = [1, 2, 3]
    snapshot, plan = turn_plan.build_turn_plan(obs, deck_knowledge=FakeKnowledge())

    assert plan.mode == "finish"
    selected = finish_search.try_finish_search(obs, snapshot, plan, deck_knowledge=FakeKnowledge())

    assert selected == [0]


def test_crustle_kangaskhan_v2_turn_plan_enters_finish_for_switch_gust_bench_attack_line():
    runtime = _load_crustle_module("runtime", agent_name="crustle_mega_kangaskhan_rule_rl_p1_v2")
    turn_plan = _load_crustle_module("turn_plan", agent_name="crustle_mega_kangaskhan_rule_rl_p1_v2")
    from cg.api import OptionType

    switch = _fake_card(runtime.CardIds.SWITCH, name="Switch")
    boss = _fake_card(runtime.CardIds.BOSS_ORDERS, name="Boss's Orders")
    obs = _fake_obs(
        hand=[switch, boss],
        active=_fake_card(runtime.CardIds.DWEBBLE, name="Dwebble", hp=70, max_hp=70, energies=[]),
        bench=[
            _fake_card(
                runtime.CardIds.MEGA_KANGASKHAN_EX,
                name="Mega Kangaskhan ex",
                hp=230,
                max_hp=230,
                energies=[1, 1, 1],
            ),
            _fake_card(runtime.CardIds.DWEBBLE, name="Dwebble", hp=70, max_hp=70, energies=[]),
        ],
        opponent_active=_fake_card(9902, name="Active ex", hp=250, max_hp=250, energies=[]),
        opponent_bench=[_fake_card(9903, name="Bench ex", hp=180, max_hp=180, energies=[])],
        options=[
            SimpleNamespace(type=OptionType.PLAY, index=0),
            SimpleNamespace(type=OptionType.PLAY, index=1),
        ],
    )
    obs.current.players[0].prize = [1]
    obs.current.players[1].prize = [1, 2, 3]

    _, plan = turn_plan.build_turn_plan(obs)

    assert plan.mode == "finish"


def test_crustle_kangaskhan_v2_finish_search_starts_switch_line_for_verified_bench_finish():
    runtime = _load_crustle_module("runtime", agent_name="crustle_mega_kangaskhan_rule_rl_p1_v2")
    finish_search = _load_crustle_module("finish_search", agent_name="crustle_mega_kangaskhan_rule_rl_p1_v2")
    turn_plan = _load_crustle_module("turn_plan", agent_name="crustle_mega_kangaskhan_rule_rl_p1_v2")
    from cg.api import OptionType

    switch = _fake_card(runtime.CardIds.SWITCH, name="Switch")
    boss = _fake_card(runtime.CardIds.BOSS_ORDERS, name="Boss's Orders")
    obs = _fake_obs(
        hand=[switch, boss],
        active=_fake_card(runtime.CardIds.DWEBBLE, name="Dwebble", hp=70, max_hp=70, energies=[]),
        bench=[
            _fake_card(
                runtime.CardIds.MEGA_KANGASKHAN_EX,
                name="Mega Kangaskhan ex",
                hp=230,
                max_hp=230,
                energies=[1, 1, 1],
            ),
            _fake_card(runtime.CardIds.DWEBBLE, name="Dwebble", hp=70, max_hp=70, energies=[]),
        ],
        opponent_active=_fake_card(9904, name="Active ex", hp=250, max_hp=250, energies=[]),
        opponent_bench=[_fake_card(9905, name="Bench ex", hp=180, max_hp=180, energies=[])],
        options=[
            SimpleNamespace(type=OptionType.PLAY, index=0),
            SimpleNamespace(type=OptionType.PLAY, index=1),
        ],
    )
    obs.current.players[0].prize = [1]
    obs.current.players[1].prize = [1, 2, 3]
    snapshot, plan = turn_plan.build_turn_plan(obs)

    assert plan.mode == "finish"
    selected = finish_search.try_finish_search(obs, snapshot, plan, deck_knowledge=None)

    assert selected == [0]


def test_crustle_kangaskhan_v2_state_view_exposes_safe_draws():
    turn_plan = _load_crustle_module("turn_plan", agent_name="crustle_mega_kangaskhan_rule_rl_p1_v2")
    runtime = _load_crustle_module("runtime", agent_name="crustle_mega_kangaskhan_rule_rl_p1_v2")

    obs = _fake_obs(
        hand=[],
        active=_fake_card(runtime.CardIds.MEGA_KANGASKHAN_EX, name="Mega Kangaskhan ex", hp=230, max_hp=230),
        bench=[],
        opponent_active=_fake_card(678, name="id:678", hp=340, max_hp=340, energies=[1]),
        options=[],
    )
    obs.current.players[0].deckCount = 4
    obs.current.players[0].prize = [1, 2]

    snapshot, plan = turn_plan.build_turn_plan(obs)
    state_view = turn_plan.build_state_view(snapshot, plan)

    assert state_view.safe_draws == 1


def test_crustle_kangaskhan_v2_rule_prior_penalizes_run_errand_when_safe_draws_empty():
    runtime = _load_crustle_module("runtime", agent_name="crustle_mega_kangaskhan_rule_rl_p1_v2")
    rule_prior = _load_crustle_module("rule_prior", agent_name="crustle_mega_kangaskhan_rule_rl_p1_v2")
    from cg.api import OptionType

    active_kang = _fake_card(runtime.CardIds.MEGA_KANGASKHAN_EX, name="Mega Kangaskhan ex", hp=230, max_hp=230)
    obs = _fake_obs(
        hand=[],
        active=active_kang,
        bench=[
            _fake_card(runtime.CardIds.DWEBBLE, name="Dwebble", hp=70, max_hp=70, energies=[]),
            _fake_card(runtime.CardIds.DWEBBLE, name="Dwebble", hp=70, max_hp=70, energies=[]),
        ],
        opponent_active=_fake_card(9100, name="Unknown Attacker", hp=170, max_hp=170, energies=[1]),
        options=[
            SimpleNamespace(type=OptionType.ABILITY, area=4, index=0),
            SimpleNamespace(type=OptionType.END),
        ],
    )
    obs.current.players[0].deckCount = 2
    obs.current.players[0].prize = [1]
    obs.current.players[1].prize = [1, 2, 3, 4]
    obs.current.turn = 6

    ability_result = rule_prior.score_option(obs, obs.select.option[0])
    end_result = rule_prior.score_option(obs, obs.select.option[1])

    assert "low_deck_no_run_errand" in ability_result["reason_tags"]
    assert ability_result["total_logit"] < end_result["total_logit"]


def test_crustle_kangaskhan_v2_rule_prior_hilda_play_only_opens_search_not_route_completion():
    runtime = _load_crustle_module("runtime", agent_name="crustle_mega_kangaskhan_rule_rl_p1_v2")
    rule_prior = _load_crustle_module("rule_prior", agent_name="crustle_mega_kangaskhan_rule_rl_p1_v2")
    turn_plan = _load_crustle_module("turn_plan", agent_name="crustle_mega_kangaskhan_rule_rl_p1_v2")
    from cg.api import OptionType

    hilda = _fake_card(runtime.CardIds.HILDA, name="Hilda")
    crustle = _fake_card(runtime.CardIds.CRUSTLE, name="Crustle")
    obs = _fake_obs(
        hand=[hilda, crustle],
        active=_fake_card(runtime.CardIds.DWEBBLE, name="Dwebble", hp=70, max_hp=70, energies=[1]),
        bench=[
            _fake_card(runtime.CardIds.DWEBBLE, name="Dwebble", hp=70, max_hp=70, energies=[]),
            _fake_card(runtime.CardIds.MEGA_KANGASKHAN_EX, name="Mega Kangaskhan ex", hp=230, max_hp=230, energies=[]),
        ],
        opponent_active=_fake_card(9101, name="Lucario ex", hp=280, max_hp=280, energies=[1, 1]),
        options=[
            SimpleNamespace(type=OptionType.PLAY, index=0),
            SimpleNamespace(type=OptionType.EVOLVE, index=1),
        ],
    )

    _, plan = turn_plan.build_turn_plan(obs)
    assert plan.mode in {"setup_crustle_wall_now", "setup_crustle"}

    hilda_result = rule_prior.score_option(obs, obs.select.option[0])
    evolve_result = rule_prior.score_option(obs, obs.select.option[1])

    assert hilda_result["total_logit"] < evolve_result["total_logit"]
    assert "open_hilda_search" in hilda_result["reason_tags"]
    assert "plan_search_goal_hilda" in hilda_result["reason_tags"]
    assert "play_hilda" not in hilda_result["reason_tags"]
    assert "search_basic" not in hilda_result["reason_tags"]


def test_crustle_kangaskhan_v2_rule_prior_to_hand_uses_turn_plan_targets_not_generic_search():
    runtime = _load_crustle_module("runtime", agent_name="crustle_mega_kangaskhan_rule_rl_p1_v2")
    rule_prior = _load_crustle_module("rule_prior", agent_name="crustle_mega_kangaskhan_rule_rl_p1_v2")
    from cg.api import AreaType, OptionType, SelectContext

    ultra = _fake_card(runtime.CardIds.ULTRA_BALL, name="Ultra Ball")
    crustle = _fake_card(runtime.CardIds.CRUSTLE, name="Crustle")
    random_supporter = _fake_card(runtime.CardIds.LILLIE, name="Lillie")
    obs = _fake_obs(
        hand=[ultra],
        active=_fake_card(runtime.CardIds.MEGA_KANGASKHAN_EX, name="Mega Kangaskhan ex", hp=230, max_hp=230),
        bench=[_fake_card(runtime.CardIds.DWEBBLE, name="Dwebble", hp=70, max_hp=70, energies=[])],
        opponent_active=_fake_card(9102, name="Unknown ex", hp=290, max_hp=290, energies=[1]),
        select_deck=[crustle, random_supporter],
        options=[
            SimpleNamespace(type=OptionType.CARD, area=AreaType.DECK, index=0, playerIndex=0),
            SimpleNamespace(type=OptionType.CARD, area=AreaType.DECK, index=1, playerIndex=0),
        ],
        context=SelectContext.TO_HAND,
        effect=ultra,
    )

    crustle_result = rule_prior.score_option(obs, obs.select.option[0])
    random_result = rule_prior.score_option(obs, obs.select.option[1])

    assert crustle_result["total_logit"] > random_result["total_logit"]
    assert "plan_search_target" in crustle_result["reason_tags"]
    assert "generic_search_target" not in random_result["reason_tags"]


def test_crustle_kangaskhan_v2_turn_plan_exposes_explicit_plan_contract_fields():
    runtime = _load_crustle_module("runtime", agent_name="crustle_mega_kangaskhan_rule_rl_p1_v2")
    turn_plan = _load_crustle_module("turn_plan", agent_name="crustle_mega_kangaskhan_rule_rl_p1_v2")
    from cg.api import OptionType

    poffin = _fake_card(runtime.CardIds.BUDDY_BUDDY_POFFIN, name="Buddy-Buddy Poffin")
    obs = _fake_obs(
        hand=[poffin],
        active=_fake_card(runtime.CardIds.MEGA_KANGASKHAN_EX, name="Mega Kangaskhan ex", hp=230, max_hp=230),
        bench=[],
        opponent_active=_fake_card(9103, name="Dragapult ex", hp=320, max_hp=320, energies=[1]),
        options=[SimpleNamespace(type=OptionType.PLAY, index=0)],
    )
    obs.current.turn = 1

    _, plan = turn_plan.build_turn_plan(obs)

    assert plan.mode == "survival_setup"
    assert runtime.CardIds.DWEBBLE in plan.required_basic_ids
    assert runtime.CardIds.DWEBBLE in plan.search_target_ids
    assert runtime.CardIds.BUDDY_BUDDY_POFFIN in plan.petrel_target_ids
    assert plan.poffin_basic_ids
    assert plan.switch_target_role is not None


def test_crustle_kangaskhan_v2_survival_setup_hilda_prefers_dwebble_before_crustle_when_board_is_empty():
    runtime = _load_crustle_module("runtime", agent_name="crustle_mega_kangaskhan_rule_rl_p1_v2")
    turn_plan = _load_crustle_module("turn_plan", agent_name="crustle_mega_kangaskhan_rule_rl_p1_v2")
    from cg.api import OptionType

    hilda = _fake_card(runtime.CardIds.HILDA, name="Hilda")
    obs = _fake_obs(
        hand=[hilda],
        active=_fake_card(runtime.CardIds.MEGA_KANGASKHAN_EX, name="Mega Kangaskhan ex", hp=230, max_hp=230),
        bench=[],
        opponent_active=_fake_card(91031, name="Lucario ex", hp=280, max_hp=280, energies=[1, 1]),
        options=[SimpleNamespace(type=OptionType.PLAY, index=0)],
    )
    obs.current.turn = 1

    _, plan = turn_plan.build_turn_plan(obs)

    assert plan.mode == "survival_setup"
    assert plan.hilda_pair_preferences[0][0] == runtime.CardIds.DWEBBLE


def test_crustle_kangaskhan_v2_rule_prior_trainer_search_uses_plan_trainer_targets():
    runtime = _load_crustle_module("runtime", agent_name="crustle_mega_kangaskhan_rule_rl_p1_v2")
    rule_prior = _load_crustle_module("rule_prior", agent_name="crustle_mega_kangaskhan_rule_rl_p1_v2")
    from cg.api import AreaType, OptionType, SelectContext

    pokegear = _fake_card(runtime.CardIds.POKEGEAR, name="Pokegear")
    hilda = _fake_card(runtime.CardIds.HILDA, name="Hilda")
    eri = _fake_card(runtime.CardIds.ERI, name="Eri")
    obs = _fake_obs(
        hand=[pokegear],
        active=_fake_card(runtime.CardIds.MEGA_KANGASKHAN_EX, name="Mega Kangaskhan ex", hp=230, max_hp=230),
        bench=[_fake_card(runtime.CardIds.DWEBBLE, name="Dwebble", hp=70, max_hp=70, energies=[])],
        opponent_active=_fake_card(9104, name="Unknown ex", hp=290, max_hp=290, energies=[1]),
        select_deck=[hilda, eri],
        options=[
            SimpleNamespace(type=OptionType.CARD, area=AreaType.DECK, index=0, playerIndex=0),
            SimpleNamespace(type=OptionType.CARD, area=AreaType.DECK, index=1, playerIndex=0),
        ],
        context=SelectContext.TO_HAND,
        effect=pokegear,
    )

    hilda_result = rule_prior.score_option(obs, obs.select.option[0])
    eri_result = rule_prior.score_option(obs, obs.select.option[1])

    assert hilda_result["total_logit"] > eri_result["total_logit"]
    assert "plan_trainer_search_target" in hilda_result["reason_tags"]


def test_crustle_kangaskhan_v2_dragapult_wall_keeps_residual_threat():
    turn_plan = _load_crustle_module("turn_plan", agent_name="crustle_mega_kangaskhan_rule_rl_p1_v2")
    runtime = _load_crustle_module("runtime", agent_name="crustle_mega_kangaskhan_rule_rl_p1_v2")
    from cg.api import OptionType

    crustle = _fake_card(runtime.CardIds.CRUSTLE, name="Crustle", hp=140, max_hp=140, energies=[1])
    dragapult = _fake_card(121, name="Dragapult ex", hp=320, max_hp=320, energies=[1, 1])
    obs = _fake_obs(
        hand=[],
        active=crustle,
        bench=[_fake_card(runtime.CardIds.DWEBBLE, name="Dwebble", hp=70, max_hp=70, energies=[])],
        opponent_active=dragapult,
        options=[SimpleNamespace(type=OptionType.ATTACK)],
    )

    snapshot, _plan = turn_plan.build_turn_plan(obs)

    assert snapshot.wall_online is True
    assert snapshot.wall_valid is True
    assert snapshot.opponent_estimated_damage >= 40


def test_crustle_kangaskhan_v2_dragapult_bench_protection_overrides_wall_tax_when_bench_fragile():
    turn_plan = _load_crustle_module("turn_plan", agent_name="crustle_mega_kangaskhan_rule_rl_p1_v2")
    runtime = _load_crustle_module("runtime", agent_name="crustle_mega_kangaskhan_rule_rl_p1_v2")
    from cg.api import OptionType

    crustle = _fake_card(runtime.CardIds.CRUSTLE, name="Crustle", hp=140, max_hp=140, energies=[1])
    weak_dwebble = _fake_card(runtime.CardIds.DWEBBLE, name="Dwebble", hp=60, max_hp=70, energies=[])
    dragapult = _fake_card(121, name="Dragapult ex", hp=320, max_hp=320, energies=[1, 1])
    obs = _fake_obs(
        hand=[],
        active=crustle,
        bench=[weak_dwebble],
        opponent_active=dragapult,
        options=[SimpleNamespace(type=OptionType.ATTACK)],
    )

    _, plan = turn_plan.build_turn_plan(obs)

    assert plan.mode == "protect_bench_vs_dragapult"
