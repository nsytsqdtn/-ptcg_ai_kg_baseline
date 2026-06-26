from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_notebook_uploader_html_matches_expected_flow():
    output_path = ROOT / "replay_systems" / "replay" / "visualizer.html"

    text = output_path.read_text(encoding="utf-8")

    assert '<input type="file" id="fileInput">' in text
    assert 'input.name = "json"' in text
    assert '"steps" in obj && Array.isArray(obj["steps"])' in text
    assert 'obj["steps"][0][0]["visualize"]' in text
    assert 'Array.isArray(obj["steps"]) && obj["steps"].length > 0' in text
    assert 'typeof obj["steps"][0] === "object"' in text
    assert 'JSON.stringify(obj["steps"])' in text
    assert 'https://ptcgvis.heroz.jp/Visualizer/Replay/0' in text
