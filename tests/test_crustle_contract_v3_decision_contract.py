from pathlib import Path
import importlib
import sys
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
AGENT_DIR = ROOT / "agents" / "crustle_mega_kangaskhan_rule_contract_v3"

for path in (ROOT, AGENT_DIR):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

decision_contract = importlib.import_module("ck_contract_core.decision_contract")
SelectContext = importlib.import_module("cg.api").SelectContext


def make_action(*, index: int, tags: set[str], reason: list[str] | None = None):
    return SimpleNamespace(index=index, tags=set(tags), reason=list(reason or []), card_id=None)


def test_decision_contract_relaxes_plan_before_obligations():
    obs = SimpleNamespace(select=SimpleNamespace(context=SelectContext.MAIN))
    snapshot = SimpleNamespace(field_count=1, active_under_ko_threat=False)
    obligations = SimpleNamespace(
        must_not_end_turn=True,
        must_not_attack=False,
        must_not_retreat=False,
        must_not_draw=False,
        must_add_backup=False,
        must_preserve_wall=False,
    )
    plan = SimpleNamespace(objective="setup_crustle_wall")
    deck_knowledge = SimpleNamespace()
    classified = [
        make_action(index=0, tags={"end_turn"}),
        make_action(index=1, tags={"draw_deck"}),
    ]

    allowed = decision_contract.apply_decision_contract(
        obs,
        classified,
        snapshot,
        obligations,
        plan,
        deck_knowledge,
    )

    assert [action.index for action in allowed] == [1]
    assert "violates_obligations" in classified[0].reason
    assert "violates_plan_contract" in classified[1].reason
