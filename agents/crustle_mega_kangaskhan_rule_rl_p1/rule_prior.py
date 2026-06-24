from __future__ import annotations

from cg.api import AreaType, OptionType, SelectContext

from deck_state import analyze_deck_state
from line_evaluator import score_line_progress
from runtime import (
    CardIds,
    damage_taken,
    energy_count,
    is_basic_pokemon,
    make_rule_prior_result,
)
from selection_scorer import (
    score_gust_target,
    score_petrel_play,
    score_hilda_target,
    score_petrel_target,
    score_poffin_target,
    score_switch_target,
    score_ultra_ball_discard,
    infer_pair_card_id,
)


def _my_card(obs, area, index, player_index):
    player_state = obs.current.players[player_index]
    if area == AreaType.HAND:
        return player_state.hand[index]
    if area == AreaType.DECK:
        return obs.select.deck[index]
    if area == AreaType.ACTIVE:
        return player_state.active[index]
    if area == AreaType.BENCH:
        return player_state.bench[index]
    if area == AreaType.DISCARD:
        return player_state.discard[index]
    if area == AreaType.LOOKING:
        return obs.current.looking[index]
    return None


def _line_weight(deck_state) -> tuple[str, float]:
    weights = deck_state.plan_scores
    primary = deck_state.primary_plan
    return primary, max(1.0, weights.get(primary, 0.0) * 100.0)


def _deck_has(deck_knowledge, card_id: int):
    if deck_knowledge is None:
        return None
    return deck_knowledge.deck_has(card_id)


def _search_target_availability(deck_knowledge, card_ids: set[int]) -> bool | None:
    known_values = [_deck_has(deck_knowledge, card_id) for card_id in card_ids]
    live_values = [value for value in known_values if value is not None]
    if not live_values:
        return None
    return any(live_values)


def _score_energy_attach(card_id: int, target, target_area, deck_state, add):
    if target is None:
        return
    if card_id == CardIds.GROW_GRASS_ENERGY:
        if target.id in {CardIds.CRUSTLE, CardIds.DWEBBLE}:
            add("attack_continuity", 110.0, "grow_grass_crustle")
        elif target.id == CardIds.MEGA_KANGASKHAN_EX:
            add("resource", 20.0, "grow_grass_kang_fallback")
    elif card_id == CardIds.MIST_ENERGY:
        if deck_state.matchup.values_mist_energy and target.id in {CardIds.CRUSTLE, CardIds.DWEBBLE, CardIds.MEGA_KANGASKHAN_EX}:
            add("survival", 105.0, "mist_protection")
        else:
            add("resource", 35.0, "mist_generic")
    elif card_id == CardIds.SPIKY_ENERGY:
        if target_area == AreaType.ACTIVE:
            add("survival", 96.0, "spiky_tank")
        else:
            add("survival", 22.0, "spiky_bench_fallback")
    elif card_id == CardIds.BASIC_GRASS:
        if target.id in {CardIds.CRUSTLE, CardIds.DWEBBLE}:
            add("attack_continuity", 88.0, "basic_grass_crustle")
        else:
            add("resource", 30.0, "basic_grass_fallback")


def _score_play_card(card, deck_state, active, state, add, deck_knowledge=None):
    primary_plan, line_bonus = _line_weight(deck_state)
    hand_ids = {getattr(hand_card, "id", None) for hand_card in getattr(state.players[state.yourIndex], "hand", []) if hand_card is not None}
    discard_ids = {getattr(discard_card, "id", None) for discard_card in getattr(state.players[state.yourIndex], "discard", []) if discard_card is not None}
    if deck_state.must_bench_basic:
        if card.id in {CardIds.DWEBBLE, CardIds.MEGA_KANGASKHAN_EX} and deck_state.bench_space > 0:
            add("survival", 155.0, "must_bench_basic")
        elif card.id == CardIds.BUDDY_BUDDY_POFFIN:
            add("survival", 150.0, "must_bench_basic_search")
        elif card.id in {CardIds.HILDA, CardIds.ULTRA_BALL}:
            add("survival", 118.0, "must_bench_basic_search")
        elif card.id == CardIds.PETREL:
            add("survival", 40.0, "must_bench_basic_search")
        elif card.id == CardIds.POKEGEAR:
            add("survival", 70.0, "must_bench_basic_search")
        elif card.id not in {CardIds.SWITCH, CardIds.JUMBO_ICE_CREAM, CardIds.BIANCA_DEVOTION, CardIds.BOSS_ORDERS, CardIds.LISIA}:
            add("risk", -40.0, "delay_bench_basic")
    if card.id == CardIds.DWEBBLE:
        add("setup", 120.0 if primary_plan == "setup_crustle" else 55.0, "play_dwebble")
    elif card.id == CardIds.CRUSTLE:
        add("setup", 118.0 if primary_plan in {"setup_crustle", "wall_and_tax"} else 40.0, "play_crustle")
    elif card.id == CardIds.MEGA_KANGASKHAN_EX:
        add("setup", 114.0 if primary_plan == "setup_kangaskhan" else 42.0, "play_kang")
    elif card.id == CardIds.BUDDY_BUDDY_POFFIN:
        if deck_state.must_bench_basic:
            add("survival", 190.0, "must_poffin_basic")
        add("setup", 110.0 if deck_state.setup_missing_crustle and deck_state.bench_space > 0 else 15.0, "poffin")
        poffin_live = _search_target_availability(deck_knowledge, {CardIds.DWEBBLE, CardIds.MEGA_KANGASKHAN_EX})
        if poffin_live is False:
            add("risk", -450.0, "dead_poffin")
    elif card.id == CardIds.HILDA:
        add("setup", 102.0 if primary_plan in {"setup_crustle", "setup_kangaskhan"} else 45.0, "hilda")
        if primary_plan in {"setup_crustle", "setup_crustle_wall_now", "wall_and_tax"}:
            crustle_live = _search_target_availability(deck_knowledge, {CardIds.CRUSTLE, CardIds.DWEBBLE})
            energy_live = _search_target_availability(deck_knowledge, {CardIds.GROW_GRASS_ENERGY, CardIds.BASIC_GRASS})
            if crustle_live is False or energy_live is False:
                add("risk", -360.0, "dead_hilda_crustle_line")
        elif primary_plan in {"setup_kangaskhan", "tank_and_heal"}:
            kang_live = _search_target_availability(deck_knowledge, {CardIds.MEGA_KANGASKHAN_EX})
            if kang_live is False:
                add("risk", -320.0, "dead_hilda_kang_line")
    elif card.id == CardIds.PETREL:
        value, tag = score_petrel_play(deck_state, state, hand_ids=hand_ids, discard_ids=discard_ids)
        if tag == "petrel_no_clear_target":
            add("risk", value, tag)
        else:
            add("resource", value if not state.supporterPlayed else -60.0, tag or "petrel")
    elif card.id == CardIds.LILLIE:
        add("resource", 85.0 if primary_plan in {"stabilize", "setup_kangaskhan"} and not state.supporterPlayed else -40.0, "lillie")
    elif card.id == CardIds.POKEGEAR:
        add("resource", 70.0 if not state.supporterPlayed else 10.0, "pokegear")
    elif card.id == CardIds.ULTRA_BALL:
        add("setup", 96.0 if primary_plan in {"setup_crustle", "setup_kangaskhan"} else 35.0, "ultra_ball")
        if primary_plan in {"setup_crustle", "setup_crustle_wall_now"}:
            search_live = _search_target_availability(deck_knowledge, {CardIds.CRUSTLE, CardIds.DWEBBLE})
            if search_live is False:
                add("risk", -340.0, "ultra_ball_no_crustle_line")
        elif primary_plan in {"setup_kangaskhan", "tank_and_heal"}:
            search_live = _search_target_availability(deck_knowledge, {CardIds.MEGA_KANGASKHAN_EX})
            if search_live is False:
                add("risk", -320.0, "ultra_ball_no_kang")
    elif card.id == CardIds.SWITCH:
        add("survival", 118.0 if primary_plan == "wall_and_tax" and deck_state.crustle_in_play > 0 else 28.0, "switch")
    elif card.id == CardIds.JUMBO_ICE_CREAM:
        add("survival", 120.0 if deck_state.jumbo_heal_option else -18.0, "jumbo")
    elif card.id == CardIds.BIANCA_DEVOTION:
        add("survival", 125.0 if deck_state.bianca_window else -20.0, "bianca")
    elif card.id == CardIds.BOSS_ORDERS:
        if deck_state.gust_for_win:
            add("prize", 140.0, "boss_for_win")
        elif deck_state.gust_for_prize:
            add("prize", 92.0, "boss_for_prize")
        elif deck_state.gust_for_stall:
            add("disruption", 66.0, "boss_for_stall")
        else:
            add("risk", -28.0, "wasted_boss")
    elif card.id == CardIds.LISIA:
        if deck_state.gust_for_win:
            add("prize", 132.0, "lisia_for_win")
        elif deck_state.gust_for_prize:
            add("prize", 86.0, "lisia_for_prize")
        elif deck_state.gust_for_stall:
            add("disruption", 64.0, "lisia_for_stall")
        else:
            add("risk", -24.0, "wasted_lisia")
    elif card.id == CardIds.ERI:
        add("disruption", 90.0 if deck_state.primary_plan in {"wall_and_tax", "disruption_loop"} and deck_state.disruption_window else 12.0, "eri")
    elif card.id == CardIds.XEROSIC:
        add("disruption", 94.0 if deck_state.primary_plan in {"wall_and_tax", "disruption_loop"} and deck_state.disruption_window else 14.0, "xerosic")
    elif card.id == CardIds.HAND_TRIMMER:
        add("disruption", 82.0 if deck_state.disruption_window else 10.0, "trimmer")
    elif card.id == CardIds.HERO_CAPE:
        add("survival", 106.0 if deck_state.primary_plan == "tank_and_heal" else 36.0, "hero_cape")
    elif card.id == CardIds.HANDHELD_FAN:
        add("disruption", 100.0 if deck_state.primary_plan == "wall_and_tax" else 26.0, "fan")
    elif card.id == CardIds.COMMUNITY_CENTER:
        add("survival", 72.0 if active is not None and damage_taken(active) > 0 else 6.0, "community_center")
    elif card.id == CardIds.ROCKET_FACTORY:
        add("resource", 40.0, "rocket_factory")
    elif card.id == CardIds.FESTIVAL_GROUNDS:
        add("generic", 8.0)
    elif card.id in {CardIds.GROW_GRASS_ENERGY, CardIds.MIST_ENERGY, CardIds.SPIKY_ENERGY, CardIds.BASIC_GRASS}:
        add("attack_continuity", 28.0 + line_bonus * 0.1, "energy_card")
    if deck_state.matchup.name == "unknown" and card.id in {CardIds.BOSS_ORDERS, CardIds.LISIA, CardIds.XEROSIC, CardIds.HAND_TRIMMER}:
        add("risk", -14.0, "preserve_unknown_resource")


def _has_legal_basic_or_search_setup(obs, my_state) -> bool:
    for candidate in obs.select.option:
        if candidate.type != OptionType.PLAY:
            continue
        card = my_state.hand[candidate.index]
        if card.id in {
            CardIds.DWEBBLE,
            CardIds.MEGA_KANGASKHAN_EX,
            CardIds.BUDDY_BUDDY_POFFIN,
            CardIds.HILDA,
            CardIds.ULTRA_BALL,
        }:
            return True
    return False


def _score_card_choice(obs, card, option, context, my_index, deck_state, add):
    effect_id = getattr(getattr(obs.select, "effect", None), "id", None)
    paired_card_id = infer_pair_card_id(getattr(obs.current, "looking", None))
    candidate_ids = {
        getattr(candidate, "id", None)
        for candidate in list(getattr(obs.select, "deck", []) or []) + list(getattr(obs.current, "looking", []) or [])
        if candidate is not None
    }
    if context == SelectContext.SETUP_ACTIVE_POKEMON:
        if card.id == CardIds.DWEBBLE:
            add("setup", 110.0 if deck_state.matchup.prefers_crustle_wall else 75.0, "setup_dwebble")
        elif card.id == CardIds.MEGA_KANGASKHAN_EX:
            add("setup", 108.0 if not deck_state.matchup.prefers_crustle_wall else 78.0, "setup_kang")
    elif context in (SelectContext.SETUP_BENCH_POKEMON, SelectContext.TO_BENCH, SelectContext.TO_HAND):
        if effect_id == CardIds.HILDA or context == SelectContext.SETUP_BENCH_POKEMON:
            value, tag = score_hilda_target(
                card.id,
                deck_state,
                deck_state.matchup,
                paired_card_id=paired_card_id,
                candidate_ids=candidate_ids,
            )
            add("setup", value, tag)
        if effect_id == CardIds.BUDDY_BUDDY_POFFIN or context in (SelectContext.SETUP_BENCH_POKEMON, SelectContext.TO_BENCH):
            poffin_value, poffin_tag = score_poffin_target(card.id, deck_state, deck_state.matchup)
            add("setup", poffin_value, poffin_tag)
        if context == SelectContext.TO_HAND and effect_id == CardIds.PETREL:
            petrel_score, petrel_tag = score_petrel_target(card.id, deck_state)
            add("resource", petrel_score, petrel_tag)
    elif context in (SelectContext.SWITCH, SelectContext.TO_ACTIVE):
        if option.playerIndex == my_index:
            value, tag = score_switch_target(card.id, deck_state)
            add("survival", value, tag)
        else:
            value, tag = score_gust_target(card, deck_state)
            add("prize", value, tag)
            if context == SelectContext.TO_ACTIVE and is_basic_pokemon(card):
                add("disruption", 10.0, "gust_basic_stall")
    elif context == SelectContext.ATTACH_FROM:
        value, tag = score_hilda_target(
            card.id,
            deck_state,
            deck_state.matchup,
            paired_card_id=paired_card_id,
            candidate_ids=candidate_ids,
        )
        add("attack_continuity", value, tag)
        if card.id in {CardIds.GROW_GRASS_ENERGY, CardIds.MIST_ENERGY, CardIds.SPIKY_ENERGY, CardIds.BASIC_GRASS}:
            add("attack_continuity", value + 8.0, tag)
    elif context == SelectContext.DISCARD and option.playerIndex == my_index and option.area == AreaType.HAND:
        if effect_id == CardIds.ULTRA_BALL:
            discard_score, discard_tag = score_ultra_ball_discard(card.id, deck_state)
            add("risk", discard_score, discard_tag)


def score_option(obs, option, deck_knowledge=None) -> dict:
    state = obs.current
    my_index = state.yourIndex
    my_state = state.players[my_index]
    deck_state = analyze_deck_state(obs, deck_knowledge=deck_knowledge)
    active = my_state.active[0] if my_state.active else None
    opponent_active = state.players[1 - my_index].active[0] if state.players[1 - my_index].active else None
    breakdown: dict[str, float] = {}
    tags = list(deck_state.state_tags)

    def add(name: str, value: float, tag: str | None = None):
        breakdown[name] = breakdown.get(name, 0.0) + value
        if tag and (value > 0 or name in {"risk", "sequencing"}):
            tags.append(tag)

    context = obs.select.context
    add("resource", deck_state.plan_scores.get(deck_state.primary_plan, 0.0) * 10.0, deck_state.primary_plan)

    if option.type == OptionType.YES:
        add("generic", 1.0)
    elif option.type == OptionType.NUMBER:
        add("generic", float(getattr(option, "number", 0)))
    elif option.type == OptionType.CARD:
        card = _my_card(obs, option.area, option.index, option.playerIndex)
        if card is None:
            return make_rule_prior_result(0.0, {}, [])
        _score_card_choice(obs, card, option, context, my_index, deck_state, add)
    elif option.type == OptionType.PLAY:
        card = my_state.hand[option.index]
        _score_play_card(card, deck_state, active, state, add, deck_knowledge=deck_knowledge)
    elif option.type == OptionType.ATTACH:
        card = my_state.hand[option.index]
        target = _my_card(obs, option.inPlayArea, option.inPlayIndex, my_index)
        if target is None:
            return make_rule_prior_result(0.0, {}, [])
        _score_energy_attach(card.id, target, option.inPlayArea, deck_state, add)
        if card.id == CardIds.HERO_CAPE:
            add("survival", 112.0 if target.id == CardIds.MEGA_KANGASKHAN_EX else 40.0, "hero_target")
        elif card.id == CardIds.HANDHELD_FAN:
            add("disruption", 96.0 if option.inPlayArea == AreaType.ACTIVE and deck_state.primary_plan == "wall_and_tax" else 25.0, "fan_target")
    elif option.type == OptionType.EVOLVE:
        card = my_state.hand[option.index]
        if card.id == CardIds.CRUSTLE:
            add("setup", 132.0 if deck_state.primary_plan in {"setup_crustle", "wall_and_tax"} else 60.0, "evolve_crustle")
    elif option.type == OptionType.ABILITY:
        card = _my_card(obs, option.area, option.index, my_index)
        if card is None:
            return make_rule_prior_result(0.0, {}, [])
        if card.id == CardIds.MEGA_KANGASKHAN_EX:
            add("resource", 116.0 if deck_state.primary_plan in {"setup_kangaskhan", "tank_and_heal", "stabilize"} else 42.0, "run_errand")
        else:
            add("generic", 12.0)
        if deck_state.must_bench_basic:
            add("sequencing", -90.0, "delay_bench_basic")
    elif option.type == OptionType.RETREAT:
        if deck_state.primary_plan == "wall_and_tax":
            add("survival", 126.0, "retreat_to_wall")
        elif deck_state.primary_plan == "tank_and_heal":
            add("resource", 78.0, "retreat_to_kang")
        elif deck_state.primary_plan == "prevent_loss":
            add("survival", 92.0, "retreat_prevent_loss")
        else:
            add("risk", -8.0)
    elif option.type == OptionType.ATTACK:
        if active is not None:
            if deck_state.close_game:
                add("prize", 120.0, "attack_close_game")
            elif active.id == CardIds.DWEBBLE:
                if len([card for card in my_state.active + my_state.bench if card is not None]) <= 1 and _has_legal_basic_or_search_setup(obs, my_state):
                    add("sequencing", -10000.0, "ascension_before_bench_forbidden")
                add("setup", 108.0 if deck_state.primary_plan == "setup_crustle" else 30.0, "ascension")
            elif active.id == CardIds.CRUSTLE:
                add("survival", 92.0 if deck_state.wall_online else 36.0, "crustle_attack")
                if opponent_active is not None and getattr(opponent_active, "hp", 999) <= 120:
                    add("prize", 70.0, "crustle_ko")
            elif active.id == CardIds.MEGA_KANGASKHAN_EX:
                add("attack_continuity", 106.0 if deck_state.primary_plan in {"tank_and_heal", "close_game"} else 48.0, "kang_attack")
                if opponent_active is not None and getattr(opponent_active, "hp", 999) <= 200:
                    add("prize", 90.0, "kang_ko")

    if option.type == OptionType.ATTACK and deck_state.primary_plan in {"setup_crustle", "setup_kangaskhan", "survival_setup", "setup_crustle_wall_now"}:
        add("sequencing", -10.0, "premature_attack")
    if option.type == OptionType.PLAY and deck_state.primary_plan == "wall_and_tax" and breakdown.get("survival", 0.0) <= 0.0:
        add("sequencing", -8.0, "off_plan_play")
    if deck_state.must_bench_basic and option.type in {OptionType.END, OptionType.ATTACK, OptionType.RETREAT}:
        add("sequencing", -120.0, "delay_bench_basic")
    if deck_state.must_bench_basic and option.type == OptionType.ATTACH:
        add("sequencing", -70.0, "delay_bench_basic")
    if option.type == OptionType.ATTACK and deck_state.primary_plan in {"survival_setup", "setup_crustle_wall_now", "protect_bench_vs_dragapult"}:
        add("sequencing", -50.0, "attack_before_setup")

    action_tags: set[str] = set()
    if option.type == OptionType.PLAY:
        card = my_state.hand[option.index]
        if card.id == CardIds.BUDDY_BUDDY_POFFIN:
            action_tags.add("poffin_setup")
        elif card.id == CardIds.DWEBBLE:
            action_tags.add("bench_dwebble")
        elif card.id == CardIds.MEGA_KANGASKHAN_EX:
            action_tags.add("bench_kang")
        elif card.id == CardIds.HILDA:
            action_tags.add("hilda_crustle_grow")
        elif card.id == CardIds.JUMBO_ICE_CREAM and deck_state.jumbo_prevents_ko:
            action_tags.add("jumbo_heal")
        elif card.id == CardIds.BIANCA_DEVOTION and deck_state.bianca_prevents_ko:
            action_tags.add("bianca_heal")
    elif option.type == OptionType.ATTACK and active is not None and active.id == CardIds.DWEBBLE:
        action_tags.add("ascension")
    elif option.type == OptionType.EVOLVE:
        action_tags.add("evolve_crustle")
    elif option.type == OptionType.ATTACH:
        card = my_state.hand[option.index]
        if card.id == CardIds.MIST_ENERGY:
            action_tags.add("mist_protect")
        elif card.id == CardIds.SPIKY_ENERGY and option.inPlayArea == AreaType.ACTIVE:
            action_tags.add("spiky_active")
    line_progress = score_line_progress(action_tags, deck_state.line_states)
    if line_progress != 0.0:
        add("line_progress", line_progress, "line_progress")

    total_logit = sum(breakdown.values())
    return make_rule_prior_result(total_logit, breakdown, tags)
