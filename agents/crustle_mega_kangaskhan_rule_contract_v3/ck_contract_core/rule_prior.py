from __future__ import annotations

from cg.api import OptionType

from .runtime import CardIds, ENERGY_IDS, make_rule_prior_result
from .deck_state import analyze_deck_state


def score_option(obs, option, deck_knowledge=None) -> dict:
    """Compatibility scorer for legacy callers.

    The live agent path uses inference.score_actions over ClassifiedAction objects.
    This function intentionally only understands the current objective names and
    does not contain old plan branches.
    """
    deck_state = analyze_deck_state(obs, deck_knowledge=deck_knowledge)
    objective = deck_state.objective
    breakdown: dict[str, float] = {}
    tags = [objective]

    def add(name: str, value: float, tag: str):
        breakdown[name] = breakdown.get(name, 0.0) + value
        tags.append(tag)

    try:
        yi = obs.current.yourIndex
        me = obs.current.players[yi]
        if option.type == OptionType.PLAY:
            card = me.hand[option.index]
            cid = card.id
            if cid in {CardIds.DWEBBLE, CardIds.MEGA_KANGASKHAN_EX}:
                add("board", 300, "bench_basic")
            if cid in {CardIds.BUDDY_BUDDY_POFFIN, CardIds.HILDA, CardIds.PETREL, CardIds.ULTRA_BALL, CardIds.POKEGEAR}:
                add("search", 220, "play_search")
            if cid in {CardIds.ERI, CardIds.XEROSIC, CardIds.HAND_TRIMMER, CardIds.HANDHELD_FAN}:
                add("control", 260 if objective in {"wall_control", "resource_lock"} else 90, "disruption")
            if cid in {CardIds.JUMBO_ICE_CREAM, CardIds.BIANCA_DEVOTION}:
                add("survival", 200 if objective == "prevent_loss" else 90, "heal")
            if cid in {CardIds.BOSS_ORDERS, CardIds.LISIA}:
                add("tempo", 240 if objective in {"finish", "pressure_prize"} else 80, "gust")
        elif option.type == OptionType.ATTACH:
            card = me.hand[option.index]
            if card.id in ENERGY_IDS:
                add("energy", 180, "attach_energy")
                if card.id == CardIds.MIST_ENERGY and objective == "protect_bench_core":
                    add("energy", 500, "mist_core")
                if card.id == CardIds.GROW_GRASS_ENERGY and objective == "setup_crustle_wall":
                    add("energy", 420, "crustle_energy")
                if card.id == CardIds.SPIKY_ENERGY and objective == "wall_control":
                    add("energy", 320, "spiky_wall")
        elif option.type == OptionType.EVOLVE:
            card = me.hand[option.index]
            if card.id == CardIds.CRUSTLE:
                add("wall", 800 if objective == "setup_crustle_wall" else 250, "evolve_crustle")
        elif option.type == OptionType.ATTACK:
            add("attack", 900 if objective in {"finish", "pressure_prize"} else 180, "attack")
        elif option.type == OptionType.RETREAT:
            add("switch", 140, "retreat")
        elif option.type == OptionType.END:
            add("end", -30, "end_turn")
        else:
            add("generic", 1, "generic")
    except Exception:
        add("generic", 0, "fallback")
    return make_rule_prior_result(sum(breakdown.values()), breakdown, tags)
