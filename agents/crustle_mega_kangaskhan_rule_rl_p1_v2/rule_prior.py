from __future__ import annotations

from cg.api import AreaType, OptionType, SelectContext

from line_evaluator import score_line_progress
from turn_plan import build_state_view, build_turn_plan
from runtime import CardIds, ENERGY_IDS, damage_taken, energy_count, is_basic_pokemon, make_rule_prior_result, prize_count
from selection_scorer import score_gust_target, score_ultra_ball_discard


SUPPORTERS = {CardIds.BOSS_ORDERS, CardIds.ERI, CardIds.BIANCA_DEVOTION, CardIds.XEROSIC, CardIds.LISIA, CardIds.PETREL, CardIds.HILDA, CardIds.LILLIE}
CORE_SEARCH = {CardIds.BUDDY_BUDDY_POFFIN, CardIds.HILDA, CardIds.ULTRA_BALL, CardIds.PETREL, CardIds.POKEGEAR}
HEAL_CARDS = {CardIds.JUMBO_ICE_CREAM, CardIds.BIANCA_DEVOTION}
DISRUPTION_CARDS = {CardIds.ERI, CardIds.XEROSIC, CardIds.HAND_TRIMMER, CardIds.HANDHELD_FAN}


def _plan_targets(deck_state) -> set[int]:
    plan = getattr(deck_state, "turn_plan", None)
    if plan is None:
        return set()
    return set(getattr(plan, "search_target_ids", []) or [])


def _plan_petrel_targets(deck_state) -> set[int]:
    plan = getattr(deck_state, "turn_plan", None)
    if plan is None:
        return set()
    return set(getattr(plan, "petrel_target_ids", []) or [])


def _plan_hilda_pairs(deck_state) -> list[tuple[int, int]]:
    plan = getattr(deck_state, "turn_plan", None)
    if plan is None:
        return []
    return list(getattr(plan, "hilda_pair_preferences", []) or [])


def _plan_poffin_targets(deck_state) -> list[int]:
    plan = getattr(deck_state, "turn_plan", None)
    if plan is None:
        return []
    return list(getattr(plan, "poffin_basic_ids", []) or [])


def _plan_attach_prefers(deck_state, card_id: int) -> bool:
    plan = getattr(deck_state, "turn_plan", None)
    if plan is None:
        return False
    return card_id in set(getattr(plan, "attach_energy_preference", []) or [])


def _plan_switch_role(deck_state) -> str | None:
    plan = getattr(deck_state, "turn_plan", None)
    if plan is None:
        return None
    return getattr(plan, "switch_target_role", None)


def _target_role(card_id: int) -> str:
    if card_id == CardIds.CRUSTLE:
        return "crustle"
    if card_id == CardIds.DWEBBLE:
        return "dwebble"
    if card_id == CardIds.MEGA_KANGASKHAN_EX:
        return "kang"
    return "other"


def _hilda_choice_score(card_id: int, deck_state) -> tuple[float, str | None]:
    best = (-30.0, None)
    for pokemon_id, energy_id in _plan_hilda_pairs(deck_state):
        if card_id == pokemon_id:
            return 180.0, "plan_hilda_pair_pokemon"
        if card_id == energy_id:
            best = max(best, (165.0, "plan_hilda_pair_energy"), key=lambda x: x[0])
    if card_id in _plan_targets(deck_state):
        return 95.0, "plan_search_target"
    return -20.0, None


def _petrel_choice_score(card_id: int, deck_state) -> tuple[float, str | None]:
    if card_id in _plan_petrel_targets(deck_state):
        return 185.0, "plan_petrel_target"
    return -25.0, None


def _poffin_choice_score(card_id: int, deck_state) -> tuple[float, str | None]:
    targets = _plan_poffin_targets(deck_state)
    if card_id in targets:
        return 180.0 - 10.0 * targets.index(card_id), "plan_poffin_target"
    return -35.0, None


def _switch_choice_score(card_id: int, deck_state) -> tuple[float, str | None]:
    role = _plan_switch_role(deck_state)
    target = _target_role(card_id)
    if role == "crustle" and card_id == CardIds.CRUSTLE:
        return 170.0, "plan_switch_target"
    if role == "kang" and card_id == CardIds.MEGA_KANGASKHAN_EX:
        return 170.0, "plan_switch_target"
    if role == "best_attacker" and card_id == CardIds.MEGA_KANGASKHAN_EX:
        return 150.0, "plan_switch_target"
    if role == "crustle_or_kang" and target in {"crustle", "kang"}:
        return 150.0 if target == "crustle" else 140.0, "plan_switch_target"
    if role == "safest_wall_or_tank" and target in {"crustle", "kang"}:
        return 145.0 if target == "crustle" else 135.0, "plan_switch_target"
    if role == "none":
        return -120.0, "forbidden_switch_target"
    if card_id == CardIds.DWEBBLE:
        return -60.0, "avoid_expose_dwebble"
    return -10.0, None


def _get_card(obs, area, index, player_index):
    try:
        ps = obs.current.players[player_index]
        if area == AreaType.HAND:
            return ps.hand[index]
        if area == AreaType.DECK:
            return obs.select.deck[index]
        if area == AreaType.ACTIVE:
            return ps.active[index]
        if area == AreaType.BENCH:
            return ps.bench[index]
        if area == AreaType.DISCARD:
            return ps.discard[index]
        if area == AreaType.LOOKING:
            return obs.current.looking[index]
    except Exception:
        return None
    return None


def _deck_has(deck_knowledge, card_id: int) -> bool | None:
    if deck_knowledge is None:
        return None
    return deck_knowledge.deck_has(card_id)


def _any_live(deck_knowledge, ids: set[int]) -> bool | None:
    if deck_knowledge is None:
        return None
    vals = [_deck_has(deck_knowledge, cid) for cid in ids]
    known = [v for v in vals if v is not None]
    if not known:
        return None
    return any(known)


def _safe_draws(my_state) -> int:
    return getattr(my_state, "deckCount", 0) - len(getattr(my_state, "prize", []) or []) - 1


def _low_deck_gate(deck_state, add, *, hard_threshold: int = 0, soft_threshold: int = 2, hard_tag: str, soft_tag: str, hard_penalty: float = -140.0, soft_penalty: float = -60.0) -> None:
    safe_draws = getattr(deck_state, "safe_draws", None)
    if safe_draws is None:
        return
    if safe_draws <= hard_threshold and not getattr(deck_state, "close_game", False):
        add("resource", hard_penalty, hard_tag)
    elif safe_draws <= soft_threshold and not getattr(deck_state, "close_game", False):
        add("resource", soft_penalty, soft_tag)


def _supporter_available(state) -> bool:
    return not getattr(state, "supporterPlayed", False)


def _energy_attached(state) -> bool:
    return bool(getattr(state, "energyAttached", False))


def _line_tags_for_card_choice(effect_id, card_id, deck_state) -> set[str]:
    tags: set[str] = set()
    if effect_id == CardIds.HILDA:
        if card_id == CardIds.DWEBBLE:
            tags.add("hilda_target_dwebble")
        elif card_id == CardIds.CRUSTLE:
            tags.add("hilda_target_crustle")
        elif card_id == CardIds.MEGA_KANGASKHAN_EX:
            tags.add("hilda_target_kang")
        elif card_id == CardIds.GROW_GRASS_ENERGY:
            tags.add("hilda_target_growing_grass")
        elif card_id == CardIds.BASIC_GRASS:
            tags.add("hilda_target_basic_grass")
        elif card_id == CardIds.MIST_ENERGY:
            tags.add("hilda_target_mist")
    if effect_id == CardIds.BUDDY_BUDDY_POFFIN:
        if card_id == CardIds.DWEBBLE:
            tags.add("poffin_target_dwebble")
        elif card_id == CardIds.MEGA_KANGASKHAN_EX:
            tags.add("poffin_target_kang")
    if effect_id == CardIds.ULTRA_BALL:
        if card_id == CardIds.DWEBBLE:
            tags.add("ultra_ball_target_dwebble")
        elif card_id == CardIds.CRUSTLE:
            tags.add("ultra_ball_target_crustle")
        elif card_id == CardIds.MEGA_KANGASKHAN_EX:
            tags.add("ultra_ball_target_kang")
    return tags


def _score_energy_attach(card_id: int, target, target_area, deck_state, add):
    if target is None:
        return
    target_id = getattr(target, "id", None)
    if card_id == CardIds.GROW_GRASS_ENERGY:
        if target_id in {CardIds.DWEBBLE, CardIds.CRUSTLE}:
            add("attack_continuity", 130.0, "grow_grass_to_crustle_line")
            add("line_progress", 25.0, "hilda_target_growing_grass")
        elif target_id == CardIds.MEGA_KANGASKHAN_EX:
            add("resource", 18.0, "grow_grass_kang_fallback")
        else:
            add("resource", -20.0, "bad_grow_grass_target")
    elif card_id == CardIds.MIST_ENERGY:
        if _plan_attach_prefers(deck_state, card_id) and target_id in {CardIds.DWEBBLE, CardIds.CRUSTLE, CardIds.MEGA_KANGASKHAN_EX}:
            add("survival", 135.0, "mist_protect")
        elif target_id in {CardIds.CRUSTLE, CardIds.MEGA_KANGASKHAN_EX}:
            add("survival", 48.0, "mist_core")
        else:
            add("resource", -8.0, "low_value_mist")
    elif card_id == CardIds.SPIKY_ENERGY:
        if target_area == AreaType.ACTIVE and target_id in {CardIds.CRUSTLE, CardIds.MEGA_KANGASKHAN_EX}:
            add("survival", 105.0, "spiky_active")
        elif target_id == CardIds.MEGA_KANGASKHAN_EX:
            add("resource", 42.0, "spiky_kang_charge")
        else:
            add("resource", 5.0, "spiky_fallback")
    elif card_id == CardIds.BASIC_GRASS:
        if target_id in {CardIds.DWEBBLE, CardIds.CRUSTLE}:
            add("attack_continuity", 98.0, "basic_grass_crustle")
        else:
            add("resource", 18.0, "basic_grass_fallback")


def _score_play_card(obs, card, deck_state, state, active, add, deck_knowledge=None):
    plan = getattr(deck_state, "turn_plan", None)
    my_state = state.players[state.yourIndex]
    safe_draws = getattr(deck_state, "safe_draws", _safe_draws(my_state))
    supporter_ok = _supporter_available(state)
    search_targets = _plan_targets(deck_state)
    petrel_targets = _plan_petrel_targets(deck_state)
    poffin_targets = set(_plan_poffin_targets(deck_state))

    if deck_state.must_bench_basic:
        if card.id in {CardIds.DWEBBLE, CardIds.MEGA_KANGASKHAN_EX} and deck_state.bench_space > 0:
            add("survival", 500.0, "hard_bench_basic")
        elif card.id in {CardIds.BUDDY_BUDDY_POFFIN, CardIds.HILDA, CardIds.ULTRA_BALL, CardIds.PETREL, CardIds.POKEGEAR}:
            add("survival", 430.0, "hard_setup_search")
        elif card.id not in HEAL_CARDS:
            add("sequencing", -250.0, "off_plan_before_bench")

    if card.id == CardIds.DWEBBLE:
        add("setup", 240.0 if card.id in getattr(plan, "required_basic_ids", set()) else 90.0, "play_dwebble")
    elif card.id == CardIds.MEGA_KANGASKHAN_EX:
        add("setup", 230.0 if card.id in getattr(plan, "required_basic_ids", set()) else 85.0, "play_kang")
    elif card.id == CardIds.CRUSTLE:
        add("setup", 110.0 if getattr(plan, "wants_crustle_evolution", False) else 20.0, "play_crustle")
    elif card.id == CardIds.BUDDY_BUDDY_POFFIN:
        live = _any_live(deck_knowledge, {CardIds.DWEBBLE, CardIds.MEGA_KANGASKHAN_EX})
        if live is False:
            add("resource", -220.0, "poffin_no_live_basic")
        else:
            if getattr(plan, "mode", None) == "survival_setup":
                add("setup", 140.0 if poffin_targets else 20.0, "play_poffin_search_open")
            else:
                add("setup", 65.0 if poffin_targets else 10.0, "play_poffin_search_open")
    elif card.id == CardIds.HILDA:
        if not supporter_ok:
            add("resource", -300.0, "supporter_already_used")
        elif safe_draws < 1:
            add("resource", -130.0, "low_deck_no_hilda")
        else:
            _low_deck_gate(deck_state, add, hard_tag="low_deck_no_hilda", soft_tag="thin_deck_hilda")
            live = _any_live(deck_knowledge, {CardIds.DWEBBLE, CardIds.CRUSTLE, CardIds.MEGA_KANGASKHAN_EX, CardIds.GROW_GRASS_ENERGY, CardIds.MIST_ENERGY, CardIds.BASIC_GRASS})
            if live is False:
                add("setup", -180.0, "hilda_no_live_target")
            else:
                if getattr(plan, "mode", None) == "survival_setup":
                    add("setup", 12.0 if getattr(plan, "search_goal", None) else 2.0, "play_hilda_search_open")
                else:
                    add("setup", 28.0 if getattr(plan, "search_goal", None) else 4.0, "play_hilda_search_open")
                if getattr(plan, "search_goal", None) is not None:
                    add("plan_alignment", 18.0, f"plan_search_goal_hilda")
    elif card.id == CardIds.ULTRA_BALL:
        live = _any_live(deck_knowledge, {CardIds.DWEBBLE, CardIds.CRUSTLE, CardIds.MEGA_KANGASKHAN_EX})
        if live is False:
            add("resource", -220.0, "ultra_no_live_core")
        else:
            if getattr(plan, "mode", None) == "survival_setup":
                add("setup", 85.0 if search_targets else 18.0, "play_ultra_ball_search_open")
            else:
                add("setup", 45.0 if search_targets else 12.0, "play_ultra_ball_search_open")
            add("risk", -45.0, "ultra_discard_cost")
    elif card.id == CardIds.POKEGEAR:
        if safe_draws < 1:
            add("resource", -120.0, "low_deck_no_pokegear")
        else:
            _low_deck_gate(deck_state, add, hard_tag="low_deck_no_pokegear", soft_tag="thin_deck_pokegear", soft_penalty=-50.0)
            add("resource", 35.0 if supporter_ok else -25.0, "play_pokegear")
    elif card.id == CardIds.PETREL:
        if not supporter_ok:
            add("resource", -300.0, "supporter_already_used")
        else:
            _low_deck_gate(deck_state, add, hard_tag="low_deck_no_petrel", soft_tag="thin_deck_petrel", soft_penalty=-55.0)
            live = _any_live(deck_knowledge, petrel_targets)
            if live is False:
                add("resource", -160.0, "petrel_no_live_target")
            else:
                if getattr(plan, "mode", None) == "survival_setup":
                    add("resource", 35.0 if petrel_targets else 6.0, "play_petrel_search_open")
                else:
                    add("resource", 32.0 if petrel_targets else 6.0, "play_petrel_search_open")
    elif card.id == CardIds.LILLIE:
        if not supporter_ok:
            add("resource", -300.0, "supporter_already_used")
        elif deck_state.must_bench_basic:
            add("resource", -80.0, "lillie_after_bench")
        elif safe_draws <= 1:
            add("resource", -160.0, "low_deck_no_lillie")
        else:
            _low_deck_gate(deck_state, add, hard_tag="low_deck_no_lillie", soft_tag="thin_deck_lillie", soft_penalty=-70.0)
            add("resource", 90.0 if CardIds.LILLIE in search_targets else 25.0, "play_lillie")
    elif card.id == CardIds.BOSS_ORDERS:
        if not supporter_ok:
            add("resource", -300.0, "supporter_already_used")
        elif getattr(plan, "mode", None) == "finish" or deck_state.gust_for_win:
            add("prize", 240.0, "boss_for_win")
        elif deck_state.gust_for_prize:
            add("prize", 125.0, "boss_for_prize")
        elif deck_state.gust_for_stall and getattr(plan, "gust_target", None) is not None:
            add("disruption", 90.0, "boss_for_stall")
        else:
            add("resource", -90.0, "preserve_boss")
    elif card.id == CardIds.LISIA:
        if not supporter_ok:
            add("resource", -300.0, "supporter_already_used")
        elif getattr(plan, "mode", None) == "finish" or deck_state.gust_for_win:
            add("prize", 220.0, "lisia_for_win")
        elif deck_state.matchup.values_gust_on_setup_targets:
            add("disruption", 105.0, "lisia_setup_target")
        else:
            add("resource", -70.0, "preserve_lisia")
    elif card.id == CardIds.JUMBO_ICE_CREAM:
        if deck_state.jumbo_prevents_ko:
            add("survival", 230.0, "jumbo_prevents_ko")
        elif active is not None and damage_taken(active) >= 80 and energy_count(active) >= 3:
            add("survival", 60.0, "jumbo_value_heal")
        else:
            add("resource", -65.0, "wasted_jumbo")
    elif card.id == CardIds.BIANCA_DEVOTION:
        if not supporter_ok:
            add("resource", -300.0, "supporter_already_used")
        elif deck_state.bianca_prevents_ko:
            add("survival", 225.0, "bianca_prevents_ko")
        else:
            add("resource", -80.0, "preserve_bianca")
    elif card.id == CardIds.SWITCH:
        safe_targets = [c for c in getattr(my_state, "bench", []) or [] if c is not None]
        only_target_is_dwebble = len(safe_targets) == 1 and getattr(safe_targets[0], "id", None) == CardIds.DWEBBLE
        if (
            only_target_is_dwebble
            and deck_state.active_is_kangaskhan
            and not deck_state.can_make_crustle_wall_this_turn
        ):
            add("sequencing", -220.0, "avoid_switch_expose_dwebble")
        elif getattr(plan, "switch_target_role", None):
            add("survival", 55.0, "play_switch_plan")
        else:
            add("resource", -25.0, "preserve_switch")
    elif card.id in DISRUPTION_CARDS:
        if card.id in search_targets or card.id in petrel_targets:
            add("disruption", 120.0, "play_disruption")
        else:
            add("resource", -45.0, "early_disruption")
    elif card.id == CardIds.HERO_CAPE:
        if card.id in search_targets or deck_state.active_is_kangaskhan:
            add("survival", 135.0, "play_hero_cape")
        else:
            add("survival", 35.0, "hero_cape_fallback")
    elif card.id in {CardIds.COMMUNITY_CENTER, CardIds.ROCKET_FACTORY, CardIds.FESTIVAL_GROUNDS}:
        add("resource", 35.0 if card.id in search_targets or getattr(plan, "mode", None) in {"wall_and_tax", "kang_engine"} else 5.0, "play_stadium")
    elif card.id in ENERGY_IDS:
        add("resource", 12.0, "energy_in_hand")


def _score_card_choice(obs, card, option, context, my_index, deck_state, add, deck_knowledge=None):
    effect_id = getattr(getattr(obs.select, "effect", None), "id", None)
    if option.area == AreaType.DECK and _deck_has(deck_knowledge, card.id) is False:
        add("resource", -10000.0, "known_not_in_deck")
    if context == SelectContext.SETUP_ACTIVE_POKEMON:
        if card.id == CardIds.DWEBBLE:
            add("setup", 130.0 if deck_state.matchup.prefers_crustle_wall else 90.0, "setup_active_dwebble")
        elif card.id == CardIds.MEGA_KANGASKHAN_EX:
            add("setup", 125.0, "setup_active_kang")
    elif context in {SelectContext.SETUP_BENCH_POKEMON, SelectContext.TO_BENCH}:
        if card.id == CardIds.DWEBBLE:
            add("setup", 220.0 if deck_state.dwebble_in_play == 0 else 120.0, "bench_dwebble")
        elif card.id == CardIds.MEGA_KANGASKHAN_EX:
            add("setup", 205.0 if deck_state.kangaskhan_in_play == 0 else 90.0, "bench_kang")
    elif context == SelectContext.TO_HAND:
        if effect_id == CardIds.HILDA:
            value, tag = _hilda_choice_score(card.id, deck_state)
            add("setup", value, tag)
        elif effect_id == CardIds.PETREL:
            value, tag = _petrel_choice_score(card.id, deck_state)
            add("resource", value, tag)
        elif effect_id == CardIds.BUDDY_BUDDY_POFFIN:
            value, tag = _poffin_choice_score(card.id, deck_state)
            add("setup", value, tag)
        else:
            if card.id in _plan_targets(deck_state):
                add("setup", 145.0, "plan_search_target")
            else:
                add("resource", -25.0, "off_plan_search_target")
    elif context in {SelectContext.SWITCH, SelectContext.TO_ACTIVE}:
        if option.playerIndex == my_index:
            value, tag = _switch_choice_score(card.id, deck_state)
            add("survival", value, tag)
        else:
            value, tag = score_gust_target(card, deck_state)
            add("prize", value, tag)
    elif context == SelectContext.ATTACH_FROM:
        if card.id in ENERGY_IDS:
            if _plan_attach_prefers(deck_state, card.id):
                add("attack_continuity", 140.0, "plan_attach_energy")
            else:
                add("attack_continuity", -20.0, "off_plan_attach_energy")
    elif context == SelectContext.DISCARD and option.playerIndex == my_index and option.area == AreaType.HAND:
        if effect_id == CardIds.ULTRA_BALL:
            score, tag = score_ultra_ball_discard(card.id, deck_state)
            add("risk", score, tag)
    # True route progress only from actual selected targets, not from PLAY Hilda.
    for tag in _line_tags_for_card_choice(effect_id, card.id, deck_state):
        add("line_progress", 1.0, tag)


def _has_legal_setup_before_attack(obs, my_state) -> bool:
    for option in getattr(obs.select, "option", []) or []:
        if option.type != OptionType.PLAY:
            continue
        try:
            card = my_state.hand[option.index]
        except Exception:
            continue
        if card.id in {CardIds.DWEBBLE, CardIds.MEGA_KANGASKHAN_EX, CardIds.BUDDY_BUDDY_POFFIN, CardIds.HILDA, CardIds.ULTRA_BALL, CardIds.PETREL, CardIds.POKEGEAR}:
            return True
    return False


def _has_urgent_setup_play(obs, my_state) -> bool:
    return _has_legal_setup_before_attack(obs, my_state)


def _apply_turn_plan_constraints(deck_state, action_tags: set[str], add) -> None:
    plan = getattr(deck_state, "turn_plan", None)
    if plan is None:
        return
    matched_required = sorted(action_tags & set(getattr(plan, "required_tags", set()) or set()))
    matched_forbidden = sorted(action_tags & set(getattr(plan, "forbidden_tags", set()) or set()))
    for tag in matched_required:
        add("plan_alignment", 85.0, f"required_{tag}")
    for tag in matched_forbidden:
        add("plan_alignment", -140.0, f"forbidden_{tag}")


def score_option_for_plan(obs, option, snapshot, plan, deck_knowledge=None) -> dict:
    state = obs.current
    my_index = state.yourIndex
    my_state = state.players[my_index]
    deck_state = build_state_view(snapshot, plan, deck_knowledge=deck_knowledge)
    active = my_state.active[0] if getattr(my_state, "active", None) else None
    opponent_active = state.players[1 - my_index].active[0] if state.players[1 - my_index].active else None
    breakdown: dict[str, float] = {}
    tags = list(deck_state.state_tags)

    def add(name: str, value: float, tag: str | None = None):
        breakdown[name] = breakdown.get(name, 0.0) + float(value)
        if tag:
            tags.append(tag)

    add("plan", float(getattr(deck_state, "plan_priority", 0.0)), deck_state.primary_plan)
    context = obs.select.context
    action_tags: set[str] = set()

    if option.type == OptionType.YES:
        add("generic", 1.0)
    elif option.type == OptionType.NO:
        add("generic", 0.0)
    elif option.type == OptionType.NUMBER:
        add("generic", float(getattr(option, "number", 0)))
    elif option.type == OptionType.CARD:
        card = _get_card(obs, option.area, option.index, option.playerIndex)
        if card is None:
            return make_rule_prior_result(0.0, {}, [])
        _score_card_choice(obs, card, option, context, my_index, deck_state, add, deck_knowledge=deck_knowledge)
        action_tags |= _line_tags_for_card_choice(getattr(getattr(obs.select, "effect", None), "id", None), card.id, deck_state)
    elif option.type == OptionType.PLAY:
        card = my_state.hand[option.index]
        _score_play_card(obs, card, deck_state, state, active, add, deck_knowledge=deck_knowledge)
        if card.id == CardIds.DWEBBLE:
            action_tags |= {"bench_dwebble", "bench_basic", "play_dwebble"}
        elif card.id == CardIds.MEGA_KANGASKHAN_EX:
            action_tags |= {"bench_kang", "bench_basic", "play_kang"}
        elif card.id == CardIds.BUDDY_BUDDY_POFFIN:
            action_tags |= {"play_poffin", "search_basic"}
        elif card.id == CardIds.HILDA:
            action_tags.add("play_hilda")
            if getattr(plan, "search_goal", None):
                action_tags.add("search_basic")
        elif card.id == CardIds.ULTRA_BALL:
            action_tags |= {"play_ultra_ball", "search_basic"}
        elif card.id == CardIds.PETREL:
            action_tags.add("play_petrel")
            if getattr(plan, "search_goal", None):
                action_tags.add("search_basic")
            if _plan_petrel_targets(deck_state):
                action_tags.add("disruption_live")
        elif card.id == CardIds.SWITCH:
            action_tags.add("switch_safe")
        elif card.id == CardIds.JUMBO_ICE_CREAM and deck_state.jumbo_prevents_ko:
            action_tags.add("heal_escape")
        elif card.id == CardIds.BIANCA_DEVOTION and deck_state.bianca_prevents_ko:
            action_tags.add("heal_escape")
        elif card.id in DISRUPTION_CARDS:
            action_tags.add("disruption_live")
    elif option.type == OptionType.ATTACH:
        card = my_state.hand[option.index]
        target = _get_card(obs, option.inPlayArea, option.inPlayIndex, my_index)
        if target is None:
            return make_rule_prior_result(0.0, {}, [])
        _score_energy_attach(card.id, target, option.inPlayArea, deck_state, add)
        if deck_state.must_bench_basic and deck_state.field_count <= 1 and _has_urgent_setup_play(obs, my_state):
            add("sequencing", -520.0, "attach_before_bench_forbidden")
        if card.id == CardIds.MIST_ENERGY:
            action_tags.add("mist_protect")
        if card.id in ENERGY_IDS and getattr(target, "id", None) == CardIds.MEGA_KANGASKHAN_EX:
            action_tags.add("attach_kang_energy")
        if card.id == CardIds.HERO_CAPE:
            add("survival", 155.0 if getattr(target, "id", None) == CardIds.MEGA_KANGASKHAN_EX else 45.0, "hero_cape_target")
        elif card.id == CardIds.HANDHELD_FAN:
            add("disruption", 120.0 if option.inPlayArea == AreaType.ACTIVE and deck_state.primary_plan == "wall_and_tax" else 35.0, "fan_target")
            action_tags.add("disruption_live")
    elif option.type == OptionType.EVOLVE:
        card = my_state.hand[option.index]
        if card.id == CardIds.CRUSTLE:
            add("setup", 260.0 if getattr(plan, "wants_crustle_evolution", False) else 110.0, "evolve_crustle")
            action_tags.add("evolve_crustle")
        else:
            add("setup", 50.0, "evolve_other")
    elif option.type == OptionType.ABILITY:
        card = _get_card(obs, option.area, option.index, my_index)
        if card is None:
            return make_rule_prior_result(0.0, {}, [])
        if card.id == CardIds.MEGA_KANGASKHAN_EX:
            if deck_state.must_bench_basic:
                penalty = -420.0 if deck_state.field_count <= 1 and _has_urgent_setup_play(obs, my_state) else -180.0
                add("sequencing", penalty, "draw_before_bench_forbidden" if penalty < -200.0 else "draw_after_bench")
            elif getattr(deck_state, "safe_draws", _safe_draws(my_state)) <= 0 and not deck_state.close_game:
                add("resource", -140.0, "low_deck_no_run_errand")
            else:
                _low_deck_gate(deck_state, add, hard_tag="low_deck_no_run_errand", soft_tag="thin_deck_run_errand", soft_penalty=-75.0)
                add("resource", 170.0 if getattr(plan, "wants_kang_draw", False) else 65.0, "run_errand")
                action_tags.add("run_errand")
        else:
            add("generic", 15.0, "ability")
    elif option.type == OptionType.RETREAT:
        if getattr(plan, "switch_target_role", None) in {"crustle", "crustle_or_kang", "safest_wall_or_tank"}:
            add("survival", 140.0, "retreat_to_wall")
            action_tags.add("switch_safe")
        elif getattr(plan, "switch_target_role", None) in {"kang", "best_attacker"}:
            add("resource", 95.0, "retreat_to_kang")
        elif getattr(plan, "mode", None) == "prevent_loss":
            add("survival", 100.0, "retreat_prevent_loss")
            action_tags |= {"retreat", "heal_escape"}
        else:
            add("risk", -35.0, "unplanned_retreat")
            action_tags.add("retreat")
    elif option.type == OptionType.ATTACK:
        if active is not None:
            if deck_state.close_game:
                add("prize", 260.0, "attack_finish")
                action_tags.add("attack_finish")
            elif active.id == CardIds.DWEBBLE:
                if deck_state.field_count <= 1 and _has_legal_setup_before_attack(obs, my_state):
                    add("sequencing", -10000.0, "ascension_before_bench_forbidden")
                    action_tags.add("attack_end_turn")
                else:
                    add("setup", 210.0 if getattr(plan, "wants_dwebble_ascension", False) else 60.0, "ascension")
                    action_tags.add("ascension")
            elif active.id == CardIds.CRUSTLE:
                add("survival", 145.0 if deck_state.wall_online else 60.0, "crustle_attack")
                action_tags |= {"crustle_attack", "keep_wall"}
                if opponent_active is not None and getattr(opponent_active, "hp", 999) <= 120:
                    add("prize", 90.0, "crustle_ko")
            elif active.id == CardIds.MEGA_KANGASKHAN_EX:
                add("attack_continuity", 135.0 if getattr(plan, "wants_active_kang", False) or getattr(plan, "mode", None) in {"finish", "close_pressure"} else 55.0, "kang_attack")
                action_tags.add("kang_attack")
                if opponent_active is not None and getattr(opponent_active, "hp", 999) <= 200:
                    add("prize", 100.0, "kang_ko")
            action_tags.add("attack_end_turn")
    elif option.type == OptionType.END:
        add("generic", -30.0, "end_turn")
        action_tags.add("attack_end_turn")

    # Hard sequencing guards.
    if deck_state.must_bench_basic and option.type in {OptionType.ATTACK, OptionType.RETREAT, OptionType.END}:
        add("sequencing", -650.0, "forbidden_before_bench")
    if deck_state.must_bench_basic and option.type == OptionType.ATTACH:
        add("sequencing", -220.0, "attach_after_bench")
    if option.type == OptionType.PLAY and getattr(plan, "mode", None) == "wall_and_tax" and not (breakdown.get("survival", 0) > 0 or breakdown.get("disruption", 0) > 0 or breakdown.get("attack_continuity", 0) > 0):
        add("sequencing", -40.0, "off_plan_play")

    line_progress = score_line_progress(action_tags, deck_state.line_states)
    if line_progress:
        add("line_progress", line_progress, "line_progress")
    _apply_turn_plan_constraints(deck_state, action_tags, add)

    total = sum(breakdown.values())
    return make_rule_prior_result(total, breakdown, tags)


def score_option(obs, option, deck_knowledge=None) -> dict:
    snapshot, plan = build_turn_plan(obs, deck_knowledge=deck_knowledge)
    return score_option_for_plan(obs, option, snapshot, plan, deck_knowledge=deck_knowledge)
