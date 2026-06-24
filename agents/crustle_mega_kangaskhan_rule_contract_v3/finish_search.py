from __future__ import annotations

from cg.api import OptionType


def try_finish_search_if_applicable(obs, snapshot, obligations, plan, deck_knowledge, allowed_indices):
    """Minimal deterministic finish verifier.

    This intentionally does not run broad forward search. It only lets a direct
    legal attack through when the plan has already verified an immediate win.
    """
    if getattr(plan, "objective", getattr(plan, "mode", "")) != "finish":
        return None
    allowed = set(allowed_indices or [])
    for i, option in enumerate(obs.select.option):
        if i in allowed and option.type == OptionType.ATTACK:
            return [i]
    return None
