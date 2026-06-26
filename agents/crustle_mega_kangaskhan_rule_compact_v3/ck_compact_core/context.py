from __future__ import annotations

from cg.api import AreaType, OptionType

from .actions import ActionView
from .runtime import CardIds, ENERGY_IDS


def choose_context_action(obs, state, actions: list[ActionView], selected_plan: str, setup, tempo, prize, scored=None) -> list[int]:
    ctx = state.context_name
    effect_id = _effect_card_id(obs, state)
    if _is_setup_context(ctx):
        return _pick(actions, _score_initial_basic(actions))
    if effect_id == CardIds.BUDDY_BUDDY_POFFIN:
        return _pick(actions, _score_poffin(actions, setup))
    if effect_id == CardIds.HILDA:
        return _pick_multi(actions, _score_hilda(actions, selected_plan, setup, tempo, prize), state.select_min, state.select_max)
    if effect_id == CardIds.PETREL:
        return _pick_multi(actions, _score_petrel(actions, selected_plan, setup, tempo, prize), state.select_min, state.select_max)
    if effect_id == CardIds.POKEGEAR:
        return _pick(actions, _score_pokegear(actions, selected_plan, setup, tempo, prize))
    if effect_id == CardIds.ULTRA_BALL and ctx == "DISCARD":
        return _pick_multi(actions, _score_ultra_discard(actions, state, selected_plan, setup, tempo, prize), state.select_min, state.select_max)
    if _has_opponent_targets(actions):
        return _pick(actions, _score_gust_target(actions, state, prize))
    if _is_switch_context(ctx):
        return _pick(actions, _score_switch_target(actions, state, selected_plan, setup, tempo, prize))
    if ctx in {"TO_HAND", "LOOK", "NOT_MOVE", "DECK"} or any(a.kind == "CARD" for a in actions):
        return _pick_multi(actions, _score_to_hand(actions, selected_plan, setup, tempo, prize), state.select_min, state.select_max)
    if _is_yes_no(actions):
        return _pick(actions, {a.index: (50 if _looks_yes(a) and not state.deck_danger else 0) for a in actions})
    if scored:
        return [scored[0].index]
    return [actions[0].index] if actions else []


def _effect_card_id(obs, state) -> int | None:
    # Sim uses current.effect / select.effect inconsistently across actions. Try common fields.
    for obj in [getattr(obs.select, "effect", None), getattr(obs.current, "effect", None), getattr(obs.current, "effectCard", None)]:
        cid = getattr(obj, "id", obj if isinstance(obj, int) else None)
        if cid is not None:
            return int(cid)
    # Fall back to the last played card if simulator exposes it.
    return None


def _is_setup_context(ctx: str) -> bool:
    return ctx in {"SETUP_ACTIVE_POKEMON", "SETUP_BENCH_POKEMON", "TO_FIELD", "TO_BENCH"}


def _is_switch_context(ctx: str) -> bool:
    return ctx in {"SWITCH", "TO_ACTIVE", "RETREAT"}


def _has_opponent_targets(actions: list[ActionView]) -> bool:
    return any(a.has("opponent_target") or a.has("gust_target") for a in actions)


def _is_yes_no(actions: list[ActionView]) -> bool:
    names = {a.kind.upper() for a in actions}
    return bool(names) and names <= {"YES", "NO"}


def _looks_yes(action: ActionView) -> bool:
    return action.kind.upper() == "YES" or str(getattr(action.option, "type", "")).upper().endswith("YES")


def _pick(actions: list[ActionView], scores: dict[int, float]) -> list[int]:
    if not actions:
        return []
    best = max(actions, key=lambda a: (scores.get(a.index, 0), -a.index))
    return [best.index]


def _pick_multi(actions: list[ActionView], scores: dict[int, float], minc: int, maxc: int) -> list[int]:
    if not actions:
        return []
    ordered = sorted(actions, key=lambda a: (scores.get(a.index, 0), -a.index), reverse=True)
    selected = [a.index for a in ordered if scores.get(a.index, 0) >= 0][:maxc]
    if len(selected) < minc:
        for a in ordered:
            if a.index not in selected:
                selected.append(a.index)
            if len(selected) >= minc:
                break
    return selected[:maxc]


def _score_initial_basic(actions: list[ActionView]) -> dict[int, float]:
    out = {}
    for a in actions:
        v = 0
        if a.card_id == CardIds.DWEBBLE:
            v += 1000
        if a.card_id == CardIds.MEGA_KANGASKHAN_EX:
            v += 760
        out[a.index] = v
    return out


def _score_poffin(actions, setup) -> dict[int, float]:
    out = {}
    for a in actions:
        v = -20
        if a.card_id == CardIds.DWEBBLE:
            v = 1000
        elif setup.need_backup and a.has("bench_basic"):
            v = 200
        out[a.index] = v
    return out


def _score_hilda(actions, selected_plan, setup, tempo, prize) -> dict[int, float]:
    out = {}
    for a in actions:
        v = 0
        if a.card_id == CardIds.CRUSTLE:
            v += 1050 if setup.need_crustle or selected_plan == "setup" else 650
        if a.card_id == CardIds.GROW_GRASS_ENERGY:
            v += 870 if setup.need_energy_for_crustle or tempo.payoff in {"build_attacker", "setup"} else 520
        if a.card_id == CardIds.BASIC_GRASS:
            v += 790 if setup.need_energy_for_crustle else 460
        if a.card_id == CardIds.MIST_ENERGY:
            v += 820 if tempo.payoff == "protect_bench" else 430
        if a.card_id == CardIds.SPIKY_ENERGY:
            v += 380
        out[a.index] = v
    return out


def _score_petrel(actions, selected_plan, setup, tempo, prize) -> dict[int, float]:
    out = {}
    for a in actions:
        cid = a.card_id; v = 0
        if selected_plan == "setup" or tempo.payoff == "setup":
            if cid == CardIds.BUDDY_BUDDY_POFFIN and setup.need_backup:
                v += 1050
            if cid == CardIds.HILDA and (setup.need_crustle or setup.need_energy_for_crustle):
                v += 950
            if cid == CardIds.ULTRA_BALL:
                v += 780
            if cid == CardIds.POKEGEAR:
                v += 430
        if selected_plan in {"prize", "win_prize", "tempo_prize"} or prize.available:
            if cid == CardIds.BOSS_ORDERS:
                v += 860
            if cid == CardIds.LISIA:
                v += 760
            if cid == CardIds.SWITCH and prize.need_switch:
                v += 820
        if tempo.payoff == "heal":
            if cid == CardIds.JUMBO_ICE_CREAM:
                v += 1000
            if cid == CardIds.BIANCA_DEVOTION:
                v += 900
        if tempo.payoff == "protect_bench":
            if cid == CardIds.JUMBO_ICE_CREAM:
                v += 780
            if cid == CardIds.ERI:
                v += 720
            if cid == CardIds.HAND_TRIMMER:
                v += 680
        if tempo.payoff == "disrupt_energy":
            if cid == CardIds.XEROSIC:
                v += 1000
            if cid == CardIds.HANDHELD_FAN:
                v += 850
            if cid == CardIds.BOSS_ORDERS:
                v += 650
        if tempo.payoff == "disrupt_hand":
            if cid == CardIds.ERI:
                v += 1000
            if cid == CardIds.HAND_TRIMMER:
                v += 900
            if cid == CardIds.XEROSIC:
                v += 780
        if v == 0 and cid in {CardIds.PETREL, CardIds.POKEGEAR, CardIds.HILDA, CardIds.JUMBO_ICE_CREAM}:
            v += 120
        out[a.index] = v
    return out


def _score_pokegear(actions, selected_plan, setup, tempo, prize) -> dict[int, float]:
    out = {}
    for a in actions:
        cid = a.card_id; v = 0
        if selected_plan == "setup":
            if cid == CardIds.HILDA:
                v += 920
            if cid == CardIds.PETREL:
                v += 820
            if cid == CardIds.LILLIE and not setup.need_backup:
                v += 360
        elif selected_plan in {"prize", "win_prize", "tempo_prize"}:
            if cid == CardIds.BOSS_ORDERS:
                v += 1000
            if cid == CardIds.LISIA:
                v += 900
            if cid == CardIds.PETREL:
                v += 650
        else:
            if tempo.payoff == "disrupt_hand" and cid == CardIds.ERI:
                v += 850
            if tempo.payoff == "disrupt_energy" and cid == CardIds.XEROSIC:
                v += 850
            if cid == CardIds.PETREL:
                v += 760
            if cid == CardIds.HILDA:
                v += 520
        out[a.index] = v
    return out


def _score_ultra_discard(actions, state, selected_plan, setup, tempo, prize) -> dict[int, float]:
    out = {}
    protected = {CardIds.DWEBBLE, CardIds.CRUSTLE, CardIds.MEGA_KANGASKHAN_EX, CardIds.PETREL, CardIds.HILDA, CardIds.BOSS_ORDERS, CardIds.LISIA, CardIds.MIST_ENERGY, CardIds.GROW_GRASS_ENERGY, CardIds.BASIC_GRASS}
    for a in actions:
        cid = a.card_id; v = 0
        if cid in protected:
            v -= 700
        if cid in {CardIds.COMMUNITY_CENTER, CardIds.FESTIVAL_GROUNDS, CardIds.ROCKET_FACTORY}:
            v += 180
        if cid == CardIds.LILLIE and (state.deck_danger or setup.need_backup):
            v += 260
        if cid == CardIds.SPIKY_ENERGY:
            v += 80
        out[a.index] = v
    return out


def _score_to_hand(actions, selected_plan, setup, tempo, prize) -> dict[int, float]:
    out = {}
    for a in actions:
        cid = a.card_id; v = 0
        if selected_plan == "setup" or tempo.payoff == "setup":
            if setup.need_crustle and cid == CardIds.CRUSTLE:
                v += 1050
            if setup.need_dwebble and cid == CardIds.DWEBBLE:
                v += 980
            if setup.need_energy_for_crustle and cid in {CardIds.GROW_GRASS_ENERGY, CardIds.BASIC_GRASS}:
                v += 780
            if cid == CardIds.MIST_ENERGY:
                v += 520
        if selected_plan in {"prize", "win_prize", "tempo_prize"} or prize.available:
            if prize.need_energy and cid in ENERGY_IDS:
                v += 980
            if prize.need_switch and cid == CardIds.SWITCH:
                v += 850
            if prize.route == "boss" and cid == CardIds.BOSS_ORDERS:
                v += 900
            if prize.route == "lisia" and cid == CardIds.LISIA:
                v += 860
            if cid == prize.attacker_card_id:
                v += 520
        if tempo.payoff == "protect_bench" and cid == CardIds.MIST_ENERGY:
            v += 900
        if tempo.payoff == "heal" and cid == CardIds.JUMBO_ICE_CREAM:
            v += 900
        if tempo.payoff == "disrupt_energy" and cid == CardIds.XEROSIC:
            v += 850
        if tempo.payoff == "disrupt_hand" and cid in {CardIds.ERI, CardIds.HAND_TRIMMER}:
            v += 840
        out[a.index] = v
    return out


def _score_gust_target(actions, state, prize) -> dict[int, float]:
    out = {}
    dmg = state.active_attack_damage
    for a in actions:
        v = 0
        if prize.available and a.target_id == prize.target_card_id:
            v += 1250
        if a.target_id is not None and dmg > 0:
            # Action target HP is not always directly represented; use name/card id match against known targets.
            for t in state.opponent_targets:
                if t.card_id == a.target_id:
                    if dmg >= t.hp:
                        v += 550 + t.prize_value * 260
                    else:
                        v += max(0, 180 - t.hp * 0.3)
        out[a.index] = v
    return out


def _score_switch_target(actions, state, selected_plan, setup, tempo, prize) -> dict[int, float]:
    out = {}
    for a in actions:
        cid = a.card_id or a.target_id; v = 0
        if setup.need_crustle_active and cid == CardIds.CRUSTLE:
            v += 1000
        if prize.available and cid == prize.attacker_card_id:
            v += 1000
        if tempo.payoff in {"protect_bench", "disrupt_energy"} and cid == CardIds.CRUSTLE and state.opponent_active_is_ex:
            v += 760
        if cid == CardIds.CRUSTLE:
            v += 600
        if cid == CardIds.MEGA_KANGASKHAN_EX:
            v += 420
        if cid == CardIds.DWEBBLE:
            v += 280
        out[a.index] = v
    return out
