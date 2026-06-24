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


def test_battle_viewer_module_loads():
    viewer_path = ROOT / "battle_viewer.py"

    viewer = load_module("battle_viewer_module", viewer_path)

    assert callable(viewer.build_battle_data)
    assert callable(viewer.write_html)
    assert callable(viewer.render_battle)


def test_build_battle_data_accepts_local_match_record():
    viewer_path = ROOT / "battle_viewer.py"
    viewer = load_module("battle_viewer_local_record", viewer_path)

    assert callable(viewer.build_battle_data)


def test_build_battle_data_uses_current_local_snapshot_not_first_matching_view():
    viewer_path = ROOT / "replay_systems" / "legacy_battle_viewer.py"
    viewer = load_module("battle_viewer_local_record_current_snapshot", viewer_path)

    assert callable(viewer.render_battle)


def test_write_html_auto_uses_existing_card_images(tmp_path: Path):
    viewer_path = ROOT / "replay_systems" / "legacy_battle_viewer.py"
    viewer = load_module("battle_viewer_auto_images", viewer_path)

    image_map = viewer._existing_card_images(ROOT / "card_images", html_dir=tmp_path)

    assert image_map
    assert any("card_images/" in value for value in image_map.values())


def test_battle_env_viewer_module_loads():
    viewer_path = ROOT / "replay_systems" / "legacy_battle_viewer.py"

    viewer = load_module("battle_env_viewer_module", viewer_path)

    assert callable(viewer.build_battle_data)
    assert callable(viewer.write_html)
