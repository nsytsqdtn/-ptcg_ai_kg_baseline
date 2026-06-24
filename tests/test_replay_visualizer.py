from pathlib import Path
import importlib.util
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


def test_generate_html_from_steps(tmp_path: Path):
    visualizer = load_module("notebook_replay_visualizer", ROOT / "replay_systems" / "notebook_visualizer.py")

    steps = [
        {
            "step": 1,
            "select": None,
            "logs": [],
            "current": {
                "turn": 1,
                "turnActionCount": 1,
                "yourIndex": 0,
                "firstPlayer": 0,
                "supporterPlayed": False,
                "stadiumPlayed": False,
                "energyAttached": False,
                "retreated": False,
                "result": -1,
                "stadium": [],
                "lookingCount": 0,
                "looking": None,
                "players": [
                    {
                        "active": [],
                        "bench": [],
                        "benchMax": 5,
                        "deckCount": 60,
                        "discard": [],
                        "prize": [],
                        "handCount": 0,
                        "hand": [],
                        "deck": [],
                        "poisoned": False,
                        "burned": False,
                        "asleep": False,
                        "paralyzed": False,
                        "confused": False,
                    },
                    {
                        "active": [],
                        "bench": [],
                        "benchMax": 5,
                        "deckCount": 60,
                        "discard": [],
                        "prize": [],
                        "handCount": 0,
                        "hand": [],
                        "deck": [],
                        "poisoned": False,
                        "burned": False,
                        "asleep": False,
                        "paralyzed": False,
                        "confused": False,
                    },
                ],
            },
            "selected": [],
        }
    ]

    output_path = tmp_path / "viewer.html"
    visualizer.generate_html(steps, output_path)

    text = output_path.read_text(encoding="utf-8")
    assert "<title>PTCG Battle Replay v2</title>" in text
    assert 'id="eval-strip"' in text
    assert 'id="decision-list"' in text


def test_generate_html_includes_local_card_image_map(tmp_path: Path):
    visualizer = load_module("notebook_replay_visualizer_images", ROOT / "replay_systems" / "notebook_visualizer.py")

    steps = [{"current": {"turn": 0, "yourIndex": 0, "result": -1, "stadium": [], "players": [{"active": [], "bench": [], "discard": [], "prize": [], "deckCount": 60, "handCount": 0, "hand": []}, {"active": [], "bench": [], "discard": [], "prize": [], "deckCount": 60, "handCount": 0, "hand": []}]}, "logs": [], "select": None, "selected": []}]
    output_path = tmp_path / "viewer.html"

    visualizer.generate_html(steps, output_path)

    text = output_path.read_text(encoding="utf-8")
    assert "const CARD_IMAGE_MAP =" in text
    assert "card_images/" in text
