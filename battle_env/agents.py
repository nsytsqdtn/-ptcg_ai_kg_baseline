from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AGENTS_ROOT = ROOT / "agents"
PACKAGE_ROOT = Path(__file__).resolve().parent
package_root_str = str(PACKAGE_ROOT)
if package_root_str not in sys.path:
    sys.path.insert(0, package_root_str)


def resolve_agent(agent_ref: str | Path) -> Path:
    if isinstance(agent_ref, Path):
        return agent_ref.resolve()
    ref_path = Path(agent_ref)
    if ref_path.exists():
        return ref_path.resolve()
    candidate_dir = AGENTS_ROOT / agent_ref
    for filename in ("main.py", "agent.py"):
        candidate = candidate_dir / filename
        if candidate.exists():
            return candidate.resolve()
    raise FileNotFoundError(f"Unknown agent reference: {agent_ref}")


def load_agent_module(agent_path: Path):
    module_name = f"agent_{agent_path.parent.name}"
    spec = importlib.util.spec_from_file_location(module_name, agent_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module
