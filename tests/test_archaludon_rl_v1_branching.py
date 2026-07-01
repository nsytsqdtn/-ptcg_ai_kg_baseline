import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_DEFAULT_OPPONENTS = [
    "alakazam_rule_based",
    "alakazam_rule_rl_numeric_v4",
    "archaludon_rule_based",
    "crustle_mega_kangaskhan_rule_contract_v1",
    "day2_beater_rule_based",
    "dragapult_rule_based",
    "lucario_anti_crustle_lab",
    "lucario_baseline_1084_5",
    "mega_lucario_beginner",
    "mega_lucario_ex_v63",
    "multiply_agent_best_940",
]


def load_module(name: str, path: Path):
    root_str = str(ROOT)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
    module_dir = str(path.parent)
    if module_dir not in sys.path:
        sys.path.insert(0, module_dir)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_hidden_from_visualize_extracts_hidden_zones():
    module = load_module("archaludon_rl_v1_branch_train_hidden", ROOT / "agents" / "archaludon_rl_v1" / "train_rl.py")
    obs = SimpleNamespace(
        current=SimpleNamespace(
            yourIndex=0,
            players=[
                SimpleNamespace(active=[SimpleNamespace(id=169)]),
                SimpleNamespace(active=[None]),
            ],
        ),
    )
    visualize_frames = [
        {
            "current": {
                "players": [
                    {
                        "deck": [{"id": 8}, {"id": 190}],
                        "prize": [{"id": 1182}, {"id": 1227}],
                        "hand": [{"id": 1121}],
                        "active": [{"id": 169}],
                    },
                    {
                        "deck": [{"id": 304}, {"id": 678}],
                        "prize": [{"id": 1}, {"id": 2}],
                        "hand": [{"id": 3}, {"id": 4}],
                        "active": [{"id": 304}],
                    },
                ]
            }
        }
    ]

    hidden = module.hidden_from_visualize(obs, visualize_frames)

    assert hidden == {
        "your_deck": [8, 190],
        "your_prize": [1182, 1227],
        "opponent_deck": [304, 678],
        "opponent_prize": [1, 2],
        "opponent_hand": [3, 4],
        "opponent_active": [304],
    }


def test_evaluate_branching_records_counterfactual_returns(monkeypatch):
    module = load_module("archaludon_rl_v1_branch_train_eval", ROOT / "agents" / "archaludon_rl_v1" / "train_rl.py")
    obs = SimpleNamespace(current=SimpleNamespace(yourIndex=0, result=-1))
    row = {
        "context": "TO_HAND",
        "branch_candidate": True,
        "branch_options": [2, 5],
        "selected": [2],
    }

    released = []
    ended = []

    monkeypatch.setattr(module, "to_observation_class", lambda obs_dict: obs_dict)
    monkeypatch.setattr(module, "visualize_data", lambda: "[]")
    monkeypatch.setattr(module, "hidden_from_visualize", lambda _obs, _frames, **kwargs: {
        "your_deck": [1],
        "your_prize": [2],
        "opponent_deck": [3],
        "opponent_prize": [4],
        "opponent_hand": [5],
        "opponent_active": [],
    })
    monkeypatch.setattr(
        module,
        "search_begin",
        lambda *args, **kwargs: SimpleNamespace(searchId=10, observation=obs),
    )

    def fake_search_step(search_id, select):
        return SimpleNamespace(searchId=search_id * 10 + select[0], observation=SimpleNamespace(current=SimpleNamespace(result=-1)))

    monkeypatch.setattr(module, "search_step", fake_search_step)
    monkeypatch.setattr(module, "search_release", lambda search_id: released.append(search_id))
    monkeypatch.setattr(module, "search_end", lambda: ended.append(True))
    monkeypatch.setattr(
        module,
        "rollout_search_state",
        lambda state, agent_side, policy_agent, opponent_agent, max_steps: {
            "winner": 0 if state.searchId == 102 else 1,
            "steps": 7,
            "return": 0.75 if state.searchId == 102 else -0.25,
        },
    )

    branch = module.evaluate_counterfactual_branching(
        obs_dict=obs,
        row=row,
        agent_side=0,
        policy_agent=lambda _obs: [0],
        opponent_agent=lambda _obs: [0],
        max_branch_options=2,
        rollout_max_steps=20,
    )

    assert branch["counterfactual_branching"] is True
    assert branch["branch_option_lists"] == [[2], [5]]
    assert branch["branch_returns"] == [0.75, -0.25]
    assert branch["branch_winners"] == [0, 1]
    assert sorted(released) == [10, 102, 105]
    assert ended == [True]


def test_mark_branch_candidates_accepts_numeric_context_codes():
    module = load_module("archaludon_rl_v1_branch_train_context", ROOT / "agents" / "archaludon_rl_v1" / "train_rl.py")
    row = {
        "context": "7",
        "options": [
            {"option_index": 0, "rule_score": 12000, "final_score": 12000},
            {"option_index": 1, "rule_score": 9000, "final_score": 9000},
        ],
    }

    module.mark_branch_candidates(row)

    assert row["branch_candidate"] is True
    assert row["branch_options"] == [0, 1]


def test_hidden_from_visualize_backfills_missing_hidden_cards_from_known_deck():
    module = load_module("archaludon_rl_v1_branch_train_backfill", ROOT / "agents" / "archaludon_rl_v1" / "train_rl.py")
    obs = SimpleNamespace(
        current=SimpleNamespace(
            yourIndex=0,
            players=[
                SimpleNamespace(prize=[1, 2], deckCount=2, active=[SimpleNamespace(id=169)]),
                SimpleNamespace(prize=[1, 2], deckCount=2, active=[SimpleNamespace(id=304)]),
            ],
        ),
    )
    visualize_frames = [
        {
            "current": {
                "players": [
                    {
                        "deck": [{"id": 8}],
                        "prize": [],
                        "hand": [{"id": 1121}],
                        "active": [{"id": 169}],
                        "bench": [],
                        "discard": [],
                    },
                    {
                        "deck": [{"id": 304}],
                        "prize": [],
                        "hand": [{"id": 1182}],
                        "active": [{"id": 304}],
                        "bench": [],
                        "discard": [],
                    },
                ]
            }
        }
    ]

    hidden = module.hidden_from_visualize(
        obs,
        visualize_frames,
        your_full_deck=[8, 190, 1121, 169, 1182, 1227],
        opponent_full_deck=[304, 678, 1182, 304, 8, 1122],
    )

    assert len(hidden["your_deck"]) == 2
    assert len(hidden["your_prize"]) == 2
    assert len(hidden["opponent_deck"]) == 2
    assert len(hidden["opponent_prize"]) == 2


def test_branch_target_probs_prefers_higher_return():
    module = load_module("archaludon_rl_v1_branch_train_targets", ROOT / "agents" / "archaludon_rl_v1" / "train_rl.py")

    probs = module.branch_target_probs([0.0, 1.0, -1.0], temperature=0.5)

    assert len(probs) == 3
    assert abs(sum(probs) - 1.0) < 1e-6
    assert probs[1] > probs[0] > probs[2]


def test_branch_combo_logits_sum_member_option_logits():
    module = load_module("archaludon_rl_v1_branch_train_combo", ROOT / "agents" / "archaludon_rl_v1" / "train_rl.py")

    logits = [0.2, 0.5, -0.1]
    option_rows = [{"option_index": 4}, {"option_index": 7}, {"option_index": 9}]
    combo_logits = module.branch_combo_logits(logits, [[4], [7, 9]], option_rows)

    assert combo_logits == [0.2, 0.4]


def test_eval_and_train_default_opponents_match_expected_pool():
    eval_module = load_module("archaludon_rl_v1_eval_defaults", ROOT / "agents" / "archaludon_rl_v1" / "eval_agent.py")
    train_module = load_module("archaludon_rl_v1_train_defaults", ROOT / "agents" / "archaludon_rl_v1" / "train_rl.py")

    assert eval_module.DEFAULT_OPPONENTS == EXPECTED_DEFAULT_OPPONENTS
    assert train_module.DEFAULT_OPPONENTS == EXPECTED_DEFAULT_OPPONENTS


def test_build_opponent_schedule_repeats_each_opponent_fixed_times():
    train_module = load_module("archaludon_rl_v1_train_schedule", ROOT / "agents" / "archaludon_rl_v1" / "train_rl.py")

    schedule = train_module.build_opponent_schedule(["a", "b", "c"], games=2, seed=123)

    assert len(schedule) == 6
    assert sorted(schedule) == ["a", "a", "b", "b", "c", "c"]


def test_shaped_reward_penalizes_low_deck_more_for_resource_context():
    train_module = load_module("archaludon_rl_v1_train_reward_context", ROOT / "agents" / "archaludon_rl_v1" / "train_rl.py")
    prev_obs = SimpleNamespace(
        current=SimpleNamespace(
            result=-1,
            players=[
                SimpleNamespace(prize=[1, 2, 3], deckCount=20),
                SimpleNamespace(prize=[1, 2, 3], deckCount=20),
            ],
        )
    )
    next_obs = SimpleNamespace(
        current=SimpleNamespace(
            result=-1,
            players=[
                SimpleNamespace(prize=[1, 2, 3], deckCount=4),
                SimpleNamespace(prize=[1, 2, 3], deckCount=20),
            ],
        )
    )
    resource_row = {"context": "TO_HAND", "options": [{"reason": "Explorer: take supporter"}]}
    neutral_row = {"context": "MAIN", "options": [{"reason": "generic play"}]}

    resource_reward = train_module.shaped_reward(prev_obs, next_obs, 0, decision_row=resource_row)
    neutral_reward = train_module.shaped_reward(prev_obs, next_obs, 0, decision_row=neutral_row)

    assert resource_reward < neutral_reward


def test_branch_rollout_steps_prefers_longer_resource_horizon():
    train_module = load_module("archaludon_rl_v1_train_branch_horizon", ROOT / "agents" / "archaludon_rl_v1" / "train_rl.py")

    assert train_module.branch_rollout_steps_for_row({"context": "TO_HAND"}, 40) == 80
    assert train_module.branch_rollout_steps_for_row({"context": "HEAL"}, 40) == 40


def test_training_row_weight_only_opens_safe_contexts():
    train_module = load_module("archaludon_rl_v1_train_row_weight", ROOT / "agents" / "archaludon_rl_v1" / "train_rl.py")

    assert train_module.training_row_weight({"context": "HEAL", "options": [{"card_id": 1147}]}) == 1.0
    assert train_module.training_row_weight({"context": "TO_HAND", "options": [{"card_id": 1185}]}) == 0.0
    assert train_module.training_row_weight({"context": "MAIN", "options": [{"card_id": 1185}]}) == 0.0


def test_shaped_reward_adds_extra_penalty_for_deck_out_loss():
    train_module = load_module("archaludon_rl_v1_train_deck_out_penalty", ROOT / "agents" / "archaludon_rl_v1" / "train_rl.py")
    prev_obs = SimpleNamespace(
        current=SimpleNamespace(
            result=-1,
            players=[
                SimpleNamespace(prize=[1, 2, 3], deckCount=1),
                SimpleNamespace(prize=[1, 2, 3], deckCount=10),
            ],
        )
    )
    next_obs = SimpleNamespace(
        current=SimpleNamespace(
            result=1,
            players=[
                SimpleNamespace(prize=[1, 2, 3], deckCount=0),
                SimpleNamespace(prize=[1, 2, 3], deckCount=10),
            ],
        )
    )

    reward = train_module.shaped_reward(prev_obs, next_obs, 0, decision_row={"context": "TO_HAND"})

    assert reward <= -1.5
