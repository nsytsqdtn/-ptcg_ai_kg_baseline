from pathlib import Path
import importlib.util
import sys
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
AGENT_NAME = "crustle_mega_kangaskhan_rule_contract_v3"


def load_module(name: str, path: Path):
    root_str = str(ROOT)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_agent_module(name: str):
    agent_dir = ROOT / "agents" / AGENT_NAME
    agent_dir_str = str(agent_dir)
    if agent_dir_str not in sys.path:
        sys.path.insert(0, agent_dir_str)
    return load_module(f"{AGENT_NAME}_{name}", agent_dir / f"{name}.py")


def fake_card(card_id: int, *, name: str, hp: int = 100, max_hp: int = 100, energies=None):
    return SimpleNamespace(
        id=card_id,
        name=name,
        hp=hp,
        maxHp=max_hp,
        energies=list(energies or []),
        tools=[],
    )


def fake_obs(
    *,
    hand,
    active,
    bench,
    opponent_active,
    opponent_bench=None,
    options=None,
):
    current = SimpleNamespace(
        yourIndex=0,
        supporterPlayed=False,
        energyAttached=False,
        firstPlayer=0,
        turn=1,
        result=-1,
        players=[
            SimpleNamespace(
                hand=list(hand),
                active=[active] if active is not None else [],
                bench=list(bench),
                discard=[],
                deckCount=40,
                prize=[1, 2],
                handCount=len(hand),
                benchMax=5,
            ),
            SimpleNamespace(
                hand=[],
                active=[opponent_active] if opponent_active is not None else [],
                bench=list(opponent_bench or []),
                discard=[],
                deckCount=40,
                prize=[1, 2, 3, 4],
                handCount=6,
                benchMax=5,
            ),
        ],
        looking=[],
    )
    return SimpleNamespace(
        current=current,
        select=SimpleNamespace(
            option=list(options or []),
            context=None,
            deck=[],
            maxCount=1,
            minCount=0,
            effect=None,
            source=None,
        ),
    )


def test_contract_v3_evaluate_targets_current_agent(monkeypatch):
    module = load_agent_module("evaluate")
    calls = []

    def fake_play_match(left, right, verbose=False, capture_details=False):
        calls.append((left, right))
        return {
            "status": "success",
            "winner": 0,
            "agent_a": left,
            "agent_b": right,
            "steps": 1,
            "turn": 1,
            "termination": {"reason_key": "prize_out", "reason_code": 1},
        }

    monkeypatch.setattr(module, "play_match", fake_play_match)

    result, won = module._run_match("mega_lucario_beginner", 0)

    assert calls == [(AGENT_NAME, "mega_lucario_beginner")]
    assert result["agent_a"] == AGENT_NAME
    assert won is True


def test_contract_v3_turn_plan_does_not_fall_back_to_take_prize_close_pressure():
    turn_plan = load_agent_module("turn_plan")
    runtime = load_agent_module("runtime")

    active = fake_card(
        runtime.CardIds.MEGA_KANGASKHAN_EX,
        name="Mega Kangaskhan ex",
        hp=220,
        max_hp=220,
        energies=[1, 2, 3],
    )
    opponent_active = fake_card(
        999001,
        name="Lucario",
        hp=180,
        max_hp=180,
        energies=[1, 2],
    )
    obs = fake_obs(
        hand=[],
        active=active,
        bench=[fake_card(runtime.CardIds.DWEBBLE, name="Dwebble", hp=70, max_hp=70)],
        opponent_active=opponent_active,
        options=[SimpleNamespace(type=turn_plan.OptionType.ATTACK)],
    )

    _, plan = turn_plan.build_turn_plan(obs)

    assert plan.objective != "take_prize"
    assert not hasattr(plan, "close_pressure")
    assert plan.attack_now is False


def test_contract_v3_search_route_does_not_treat_unknown_deck_cards_as_live():
    search_routes = load_agent_module("search_routes")
    runtime = load_agent_module("runtime")

    class UnknownKnowledge:
        def deck_has(self, _card_id):
            return None

    plan = SimpleNamespace(
        objective="setup_crustle_wall",
        hilda_pair_preferences=((runtime.CardIds.CRUSTLE, runtime.CardIds.GROW_GRASS_ENERGY),),
        poffin_basic_ids=(),
        petrel_target_ids=(),
        search_target_ids=(),
    )
    obligations = SimpleNamespace(must_add_backup=False)

    route = search_routes.resolve_search_route(
        runtime.CardIds.HILDA,
        plan,
        obligations,
        UnknownKnowledge(),
    )

    assert route.live is False
    assert route.targets == ()


def test_contract_v3_rule_prior_prefers_mist_attach_in_dragapult_bench_protect_plan():
    rule_prior = load_agent_module("rule_prior")
    runtime = load_agent_module("runtime")

    active = fake_card(
        runtime.CardIds.CRUSTLE,
        name="Crustle",
        hp=120,
        max_hp=120,
        energies=[1],
    )
    bench = [
        fake_card(runtime.CardIds.DWEBBLE, name="Dwebble", hp=70, max_hp=70),
        fake_card(runtime.CardIds.MEGA_KANGASKHAN_EX, name="Mega Kangaskhan ex", hp=280, max_hp=300),
    ]
    opponent_active = fake_card(
        999002,
        name="Dragapult ex",
        hp=320,
        max_hp=320,
        energies=[1, 2],
    )
    hand = [
        fake_card(runtime.CardIds.MIST_ENERGY, name="Mist Energy"),
        fake_card(runtime.CardIds.SPIKY_ENERGY, name="Spiky Energy"),
    ]
    mist_attach = SimpleNamespace(
        type=rule_prior.OptionType.ATTACH,
        area=rule_prior.AreaType.HAND,
        index=0,
        inPlayArea=rule_prior.AreaType.BENCH,
        inPlayIndex=0,
    )
    spiky_attach = SimpleNamespace(
        type=rule_prior.OptionType.ATTACH,
        area=rule_prior.AreaType.HAND,
        index=1,
        inPlayArea=rule_prior.AreaType.BENCH,
        inPlayIndex=0,
    )
    obs = fake_obs(
        hand=hand,
        active=active,
        bench=bench,
        opponent_active=opponent_active,
        options=[mist_attach, spiky_attach],
    )

    mist_score = rule_prior.score_option(obs, mist_attach)
    spiky_score = rule_prior.score_option(obs, spiky_attach)

    assert mist_score["total_logit"] > spiky_score["total_logit"]
