from __future__ import annotations

from dataclasses import dataclass, field
from collections import Counter
from typing import Any
from types import SimpleNamespace

from cg.api import AreaType, OptionType
from runtime import CardIds, CORE_POKEMON, ENERGY_IDS, energy_count, get_card_name, is_basic_pokemon, is_ex_card, prize_count, damage_taken
from matchup_profile import detect_matchup_profile, MatchupProfile
from line_evaluator import build_line_states


@dataclass
class BoardSnapshot:
    obs: Any
    deck_knowledge: Any | None
    matchup: MatchupProfile
    state: Any
    my_index: int
    op_index: int
    my_state: Any
    op_state: Any
    active: Any | None
    opponent_active: Any | None
    field: list[Any]
    bench: list[Any]
    opponent_bench: list[Any]
    hand: list[Any]
    discard: list[Any]
    hand_counts: Counter[int]
    discard_counts: Counter[int]
    field_counts: Counter[int]
    bench_space: int
    field_count: int
    my_prizes_left: int
    opponent_prizes_left: int
    active_id: int | None
    opponent_active_is_ex: bool
    active_is_crustle: bool
    active_is_dwebble: bool
    active_is_kang: bool
    active_energy: int
    active_damage: int
    active_hp: int
    dwebble_in_play: int
    crustle_in_play: int
    kang_in_play: int
    wall_online: bool
    wall_valid: bool
    opponent_estimated_damage: int
    active_under_ko_threat: bool
    current_attack_damage: int
    can_attack_now: bool
    safe_draws: int
    gust_targets: list[Any] = field(default_factory=list)

    @classmethod
    def from_obs(cls, obs, deck_knowledge=None) -> "BoardSnapshot":
        state = obs.current
        yi = state.yourIndex
        oi = 1 - yi
        me = state.players[yi]
        op = state.players[oi]
        matchup = detect_matchup_profile(obs)
        active = me.active[0] if getattr(me, "active", None) else None
        opponent_active = op.active[0] if getattr(op, "active", None) else None
        bench = [c for c in getattr(me, "bench", []) or [] if c is not None]
        field = [c for c in ([active] if active is not None else []) + bench if c is not None]
        opponent_bench = [c for c in getattr(op, "bench", []) or [] if c is not None]
        hand = [c for c in getattr(me, "hand", []) or [] if c is not None]
        discard = [c for c in getattr(me, "discard", []) or [] if c is not None]
        hand_counts = Counter(c.id for c in hand)
        discard_counts = Counter(c.id for c in discard)
        field_counts = Counter(c.id for c in field)
        active_id = getattr(active, "id", None)
        active_is_crustle = active_id == CardIds.CRUSTLE
        active_is_dwebble = active_id == CardIds.DWEBBLE
        active_is_kang = active_id == CardIds.MEGA_KANGASKHAN_EX
        opponent_active_is_ex = is_ex_card(opponent_active)
        wall_online = active_is_crustle and (opponent_active_is_ex or matchup.prefers_crustle_wall)
        wall_valid = active_is_crustle and opponent_active_is_ex
        active_hp = getattr(active, "hp", 0) if active is not None else 0
        active_energy = energy_count(active)
        active_damage = damage_taken(active)
        opp_damage = estimate_opponent_damage(opponent_active, matchup)
        if wall_valid and matchup.prefers_crustle_wall:
            opp_damage = 0
        current_damage = estimate_current_attack_damage(active)
        can_attack_now = any(o.type == OptionType.ATTACK for o in getattr(obs.select, "option", []) or [])
        gust_targets = [c for c in [opponent_active] + opponent_bench if c is not None]
        return cls(
            obs=obs,
            deck_knowledge=deck_knowledge,
            matchup=matchup,
            state=state,
            my_index=yi,
            op_index=oi,
            my_state=me,
            op_state=op,
            active=active,
            opponent_active=opponent_active,
            field=field,
            bench=bench,
            opponent_bench=opponent_bench,
            hand=hand,
            discard=discard,
            hand_counts=hand_counts,
            discard_counts=discard_counts,
            field_counts=field_counts,
            bench_space=max(0, getattr(me, "benchMax", 5) - len(bench)),
            field_count=len(field),
            my_prizes_left=len(getattr(me, "prize", []) or []),
            opponent_prizes_left=len(getattr(op, "prize", []) or []),
            active_id=active_id,
            opponent_active_is_ex=opponent_active_is_ex,
            active_is_crustle=active_is_crustle,
            active_is_dwebble=active_is_dwebble,
            active_is_kang=active_is_kang,
            active_energy=active_energy,
            active_damage=active_damage,
            active_hp=active_hp,
            dwebble_in_play=field_counts[CardIds.DWEBBLE],
            crustle_in_play=field_counts[CardIds.CRUSTLE],
            kang_in_play=field_counts[CardIds.MEGA_KANGASKHAN_EX],
            wall_online=wall_online,
            wall_valid=wall_valid,
            opponent_estimated_damage=opp_damage,
            active_under_ko_threat=active is not None and opp_damage >= active_hp > 0,
            current_attack_damage=current_damage,
            can_attack_now=can_attack_now,
            safe_draws=max(0, getattr(me, "deckCount", 0) - len(getattr(me, "prize", []) or []) - 1),
            gust_targets=gust_targets,
        )


def estimate_opponent_damage(opponent_active, matchup: MatchupProfile) -> int:
    if opponent_active is None:
        return 0
    attached = energy_count(opponent_active)
    # Conservative rough threat model; used only for gates, not exact math.
    damage = 70 + 45 * attached
    if is_ex_card(opponent_active):
        damage += 40
    if matchup.name == "dragapult_ex":
        damage += 40
    if matchup.name == "mega_lucario":
        damage += 60
    return damage


def estimate_current_attack_damage(active) -> int:
    if active is None:
        return 0
    attached = energy_count(active)
    cid = getattr(active, "id", None)
    if cid == CardIds.CRUSTLE:
        return 120 if attached >= 3 or attached >= 1 else 0  # engine exposes legal attack separately; keep optimistic for target scoring
    if cid == CardIds.MEGA_KANGASKHAN_EX:
        return 200 if attached >= 3 else 0
    return 0


def estimate_attack_damage(card) -> int:
    return estimate_current_attack_damage(card)


def has_live_deck_card(deck_knowledge, card_id: int) -> bool | None:
    if deck_knowledge is None:
        return None
    return deck_knowledge.deck_has(card_id)


def search_goal_live(deck_knowledge, card_ids: set[int]) -> bool | None:
    if deck_knowledge is None:
        return None
    vals = [deck_knowledge.deck_has(cid) for cid in card_ids]
    known = [v for v in vals if v is not None]
    if not known:
        return None
    return any(known)


@dataclass
class TurnPlan:
    mode: str
    priority: int = 0
    active_goal: str = "keep"
    search_goal: str | None = None
    search_target_ids: list[int] = field(default_factory=list)
    required_basic_ids: set[int] = field(default_factory=set)
    target_field_count: int = 0
    wants_active_crustle: bool = False
    wants_crustle_evolution: bool = False
    wants_dwebble_ascension: bool = False
    wants_active_kang: bool = False
    wants_kang_draw: bool = False
    wants_kang_third_energy: bool = False
    hilda_pair_preferences: list[tuple[int, int]] = field(default_factory=list)
    petrel_target_ids: list[int] = field(default_factory=list)
    poffin_basic_ids: list[int] = field(default_factory=list)
    attach_target_role: str | None = None
    attach_energy_preference: list[int] = field(default_factory=list)
    attach_target: str | None = None
    attach_energy_type: int | None = None
    switch_target_role: str | None = None
    gust_target: int | None = None
    heal_card: int | None = None
    heal_target_role: str | None = None
    attack_now: bool = False
    reasons: list[str] = field(default_factory=list)
    required_tags: set[str] = field(default_factory=set)
    forbidden_tags: set[str] = field(default_factory=set)
    must_prevent_no_active: bool = False
    want_more_backup: bool = False
    values_mist_energy: bool = False
    direct_win_available: bool = False
    close_pressure: bool = False
    can_make_crustle_wall_this_turn: bool = False


def _active_prizes(snapshot: BoardSnapshot) -> int:
    return prize_count(snapshot.active) if snapshot.active is not None else 1


def _opponent_can_win_by_active_ko(snapshot: BoardSnapshot) -> bool:
    return snapshot.opponent_prizes_left <= _active_prizes(snapshot)


def must_prevent_no_active(snapshot: BoardSnapshot) -> bool:
    if snapshot.bench_space <= 0:
        return False
    if snapshot.field_count <= 1:
        return True
    if snapshot.active_under_ko_threat and snapshot.field_count < 3:
        return True
    if _opponent_can_win_by_active_ko(snapshot):
        return True
    return False


def want_more_backup(snapshot: BoardSnapshot) -> bool:
    turn = getattr(snapshot.state, "turn", 0)
    if snapshot.bench_space <= 0:
        return False
    if turn <= 5 and snapshot.field_count < 3:
        return True
    if snapshot.matchup.name == "dragapult_ex" and snapshot.field_count < 3:
        return True
    return False


def has_setup_action_available(snapshot: BoardSnapshot) -> bool:
    for option in getattr(snapshot.obs.select, "option", []) or []:
        if option.type != OptionType.PLAY:
            continue
        try:
            card = snapshot.hand[option.index]
        except Exception:
            continue
        if card.id in {CardIds.DWEBBLE, CardIds.MEGA_KANGASKHAN_EX, CardIds.BUDDY_BUDDY_POFFIN, CardIds.HILDA, CardIds.ULTRA_BALL, CardIds.PETREL, CardIds.POKEGEAR}:
            return True
    return False


def _target_can_be_ko(snapshot: BoardSnapshot, target) -> bool:
    return target is not None and snapshot.current_attack_damage >= getattr(target, "hp", 999) > 0


def _attacker_can_ko_target(attacker, target) -> bool:
    return target is not None and estimate_attack_damage(attacker) >= getattr(target, "hp", 999) > 0


def _has_switch_or_retreat(snapshot: BoardSnapshot) -> bool:
    for option in getattr(snapshot.obs.select, "option", []) or []:
        if option.type == OptionType.RETREAT:
            return True
        if option.type != OptionType.PLAY:
            continue
        try:
            card = snapshot.hand[option.index]
        except Exception:
            continue
        if getattr(card, "id", None) == CardIds.SWITCH:
            return True
    return False


def direct_win_available(snapshot: BoardSnapshot) -> bool:
    # Active KO wins now.
    if snapshot.can_attack_now and _target_can_be_ko(snapshot, snapshot.opponent_active) and prize_count(snapshot.opponent_active) >= snapshot.my_prizes_left:
        return True
    # Bench target can win if a gust card/effect is legal in current main action; later target selection is context-driven.
    hand_ids = set(snapshot.hand_counts)
    has_gust = bool(hand_ids & {CardIds.BOSS_ORDERS, CardIds.LISIA})
    if snapshot.can_attack_now and has_gust:
        for card in snapshot.opponent_bench:
            if _target_can_be_ko(snapshot, card) and prize_count(card) >= snapshot.my_prizes_left:
                return True
    if snapshot.can_attack_now and snapshot.hand_counts[CardIds.PETREL] > 0 and snapshot.deck_knowledge is not None:
        can_find_gust = (
            snapshot.deck_knowledge.deck_has(CardIds.BOSS_ORDERS) is True
            or snapshot.deck_knowledge.deck_has(CardIds.LISIA) is True
        )
        if can_find_gust:
            for card in snapshot.opponent_bench:
                if _target_can_be_ko(snapshot, card) and prize_count(card) >= snapshot.my_prizes_left:
                    return True
    if not _has_switch_or_retreat(snapshot):
        return False
    gust_live = has_gust or (
        snapshot.hand_counts[CardIds.PETREL] > 0
        and snapshot.deck_knowledge is not None
        and (
            snapshot.deck_knowledge.deck_has(CardIds.BOSS_ORDERS) is True
            or snapshot.deck_knowledge.deck_has(CardIds.LISIA) is True
        )
    )
    for attacker in snapshot.bench:
        if estimate_attack_damage(attacker) <= 0:
            continue
        if _attacker_can_ko_target(attacker, snapshot.opponent_active) and prize_count(snapshot.opponent_active) >= snapshot.my_prizes_left:
            return True
        if not gust_live:
            continue
        for card in snapshot.opponent_bench:
            if _attacker_can_ko_target(attacker, card) and prize_count(card) >= snapshot.my_prizes_left:
                return True
    return False


def can_make_crustle_wall_this_turn(snapshot: BoardSnapshot) -> bool:
    if snapshot.wall_online:
        return False
    if snapshot.active_is_dwebble and snapshot.can_attack_now:
        return True
    if snapshot.crustle_in_play > 0 and not snapshot.active_is_crustle:
        return True
    if snapshot.dwebble_in_play > 0:
        # if Crustle in hand or live in deck through Hilda/Ultra Ball, we can aim to evolve.
        if snapshot.hand_counts[CardIds.CRUSTLE] > 0:
            return True
        has_search = any(
            snapshot.hand_counts[card_id] > 0
            for card_id in {CardIds.HILDA, CardIds.ULTRA_BALL, CardIds.PETREL}
        )
        live = has_live_deck_card(snapshot.deck_knowledge, CardIds.CRUSTLE)
        return has_search and live is not False
    return False


def _jumbo_prevents_ko(snapshot: BoardSnapshot) -> bool:
    return (
        snapshot.active is not None
        and snapshot.active_is_kang
        and snapshot.active_energy >= 3
        and snapshot.hand_counts[CardIds.JUMBO_ICE_CREAM] > 0
        and snapshot.active_hp <= snapshot.opponent_estimated_damage < snapshot.active_hp + 80
    )


def _bianca_prevents_ko(snapshot: BoardSnapshot) -> bool:
    return (
        snapshot.active is not None
        and snapshot.active_is_kang
        and snapshot.hand_counts[CardIds.BIANCA_DEVOTION] > 0
        and getattr(snapshot.active, "hp", 999) <= 30
        and snapshot.opponent_estimated_damage >= getattr(snapshot.active, "hp", 999)
    )


def _heal_escape_card(snapshot: BoardSnapshot) -> int | None:
    if _jumbo_prevents_ko(snapshot):
        return CardIds.JUMBO_ICE_CREAM
    if _bianca_prevents_ko(snapshot):
        return CardIds.BIANCA_DEVOTION
    return None


def build_turn_plan(obs, deck_knowledge=None) -> tuple[BoardSnapshot, TurnPlan]:
    s = BoardSnapshot.from_obs(obs, deck_knowledge)
    reasons: list[str] = []
    can_win = direct_win_available(s)
    close_pressure = s.my_prizes_left <= 2
    wall_this_turn = can_make_crustle_wall_this_turn(s)
    prevent_no_active = must_prevent_no_active(s)
    wants_backup = want_more_backup(s)
    heal_escape_card = _heal_escape_card(s)
    default_hilda_pairs = [
        (CardIds.CRUSTLE, CardIds.GROW_GRASS_ENERGY),
        (CardIds.DWEBBLE, CardIds.GROW_GRASS_ENERGY),
        (CardIds.MEGA_KANGASKHAN_EX, CardIds.SPIKY_ENERGY),
    ]
    if s.matchup.values_mist_energy:
        default_hilda_pairs.insert(1, (CardIds.DWEBBLE, CardIds.MIST_ENERGY))
        default_hilda_pairs.insert(2, (CardIds.CRUSTLE, CardIds.MIST_ENERGY))

    if can_win:
        return s, TurnPlan(
            mode="finish",
            priority=100,
            attack_now=True,
            reasons=["verified_win_candidate"],
            required_tags={"attack_finish"},
            forbidden_tags={"waste_setup"},
            petrel_target_ids=[CardIds.BOSS_ORDERS, CardIds.LISIA],
            search_target_ids=[],
            switch_target_role="best_attacker",
            direct_win_available=True,
            close_pressure=close_pressure,
            values_mist_energy=s.matchup.values_mist_energy,
        )

    if prevent_no_active:
        reasons.append("must_prevent_no_active")
        required_basic_ids = {CardIds.DWEBBLE}
        if s.kang_in_play == 0:
            required_basic_ids.add(CardIds.MEGA_KANGASKHAN_EX)
        return s, TurnPlan(
            mode="survival_setup",
            priority=95,
            active_goal="keep",
            search_goal="basic_setup",
            search_target_ids=[CardIds.DWEBBLE, CardIds.MEGA_KANGASKHAN_EX, CardIds.CRUSTLE, CardIds.GROW_GRASS_ENERGY, CardIds.MIST_ENERGY, CardIds.BASIC_GRASS],
            required_basic_ids=required_basic_ids,
            target_field_count=3,
            hilda_pair_preferences=default_hilda_pairs,
            petrel_target_ids=[CardIds.BUDDY_BUDDY_POFFIN, CardIds.HILDA, CardIds.ULTRA_BALL, CardIds.SWITCH],
            poffin_basic_ids=[CardIds.DWEBBLE, CardIds.MEGA_KANGASKHAN_EX],
            attach_target_role="none",
            switch_target_role="safest_wall_or_tank",
            reasons=reasons,
            required_tags={"bench_basic", "search_basic"},
            forbidden_tags={"attack_end_turn", "retreat", "waste_supporter", "waste_gust"},
            must_prevent_no_active=True,
            want_more_backup=wants_backup,
            close_pressure=close_pressure,
            can_make_crustle_wall_this_turn=wall_this_turn,
            values_mist_energy=s.matchup.values_mist_energy,
        )

    if s.active_under_ko_threat and s.active_is_kang:
        if heal_escape_card is not None:
            return s, TurnPlan(
                mode="tank_and_heal",
                priority=88,
                active_goal="kang",
                wants_active_kang=True,
                wants_kang_draw=True,
                wants_kang_third_energy=s.active_energy < 3,
                search_goal="heal_escape",
                search_target_ids=[CardIds.MIST_ENERGY, CardIds.SPIKY_ENERGY, CardIds.GROW_GRASS_ENERGY, CardIds.BASIC_GRASS],
                petrel_target_ids=[heal_escape_card, CardIds.SWITCH, CardIds.HERO_CAPE, CardIds.COMMUNITY_CENTER],
                attach_target_role="active_kang",
                attach_energy_preference=[CardIds.SPIKY_ENERGY, CardIds.MIST_ENERGY, CardIds.BASIC_GRASS, CardIds.GROW_GRASS_ENERGY],
                switch_target_role="kang",
                heal_card=heal_escape_card,
                heal_target_role="active_kang",
                reasons=["jumbo_escape_ko" if heal_escape_card == CardIds.JUMBO_ICE_CREAM else "bianca_escape_ko"],
                required_tags={"heal_escape", "attach_kang_energy"},
                close_pressure=close_pressure,
                values_mist_energy=s.matchup.values_mist_energy,
            )
        return s, TurnPlan(
            mode="prevent_loss",
            priority=90,
            heal_card=CardIds.JUMBO_ICE_CREAM,
            search_goal="heal_or_switch_or_basic",
            search_target_ids=[CardIds.DWEBBLE, CardIds.MEGA_KANGASKHAN_EX, CardIds.MIST_ENERGY, CardIds.SPIKY_ENERGY],
            petrel_target_ids=[CardIds.JUMBO_ICE_CREAM, CardIds.BIANCA_DEVOTION, CardIds.SWITCH, CardIds.BUDDY_BUDDY_POFFIN],
            attach_target_role="active_kang",
            attach_energy_preference=[CardIds.SPIKY_ENERGY, CardIds.MIST_ENERGY],
            switch_target_role="safest_wall_or_tank",
            heal_target_role="active_kang",
            reasons=["active_ko_threat"],
            required_tags={"heal_escape", "switch_safe"},
            close_pressure=close_pressure,
            values_mist_energy=s.matchup.values_mist_energy,
        )

    if s.wall_online and s.wall_valid:
        search_goal = "mist" if s.matchup.values_mist_energy else "disruption_or_heal"
        targets = [CardIds.ERI, CardIds.XEROSIC, CardIds.HAND_TRIMMER, CardIds.HANDHELD_FAN, CardIds.JUMBO_ICE_CREAM]
        if s.matchup.values_mist_energy:
            targets.insert(0, CardIds.MIST_ENERGY)
        return s, TurnPlan(
            mode="wall_and_tax",
            priority=80,
            active_goal="crustle",
            wants_active_crustle=True,
            wants_crustle_evolution=True,
            search_goal=search_goal,
            search_target_ids=[CardIds.MIST_ENERGY, CardIds.GROW_GRASS_ENERGY, CardIds.BASIC_GRASS],
            hilda_pair_preferences=default_hilda_pairs,
            petrel_target_ids=targets,
            attach_target_role="active_crustle",
            attach_energy_preference=[CardIds.MIST_ENERGY, CardIds.SPIKY_ENERGY, CardIds.GROW_GRASS_ENERGY, CardIds.BASIC_GRASS],
            switch_target_role="crustle",
            reasons=["wall_online"],
            required_tags={"keep_wall", "disruption_live"},
            forbidden_tags={"expose_dwebble"},
            close_pressure=close_pressure,
            values_mist_energy=s.matchup.values_mist_energy,
        )

    if s.matchup.name == "dragapult_ex" and s.matchup.values_bench_protection and any(
        getattr(card, "id", None) in {CardIds.DWEBBLE, CardIds.CRUSTLE, CardIds.MEGA_KANGASKHAN_EX}
        and getattr(card, "hp", 999) <= 80
        for card in s.bench
    ):
        return s, TurnPlan(
            mode="protect_bench_vs_dragapult",
            priority=88,
            active_goal="stabilize_bench",
            search_goal="mist_or_evolve",
            search_target_ids=[CardIds.MIST_ENERGY, CardIds.CRUSTLE, CardIds.DWEBBLE, CardIds.GROW_GRASS_ENERGY, CardIds.BASIC_GRASS],
            required_basic_ids={CardIds.DWEBBLE},
            wants_crustle_evolution=True,
            hilda_pair_preferences=default_hilda_pairs,
            petrel_target_ids=[CardIds.HILDA, CardIds.BUDDY_BUDDY_POFFIN, CardIds.ULTRA_BALL, CardIds.SWITCH],
            poffin_basic_ids=[CardIds.DWEBBLE, CardIds.MEGA_KANGASKHAN_EX],
            attach_target_role="bench_core",
            attach_energy_preference=[CardIds.MIST_ENERGY, CardIds.GROW_GRASS_ENERGY, CardIds.BASIC_GRASS, CardIds.SPIKY_ENERGY],
            switch_target_role="crustle_or_kang",
            reasons=["bench_under_dragapult_pressure"],
            required_tags={"mist_protect", "evolve_crustle", "bench_basic"},
            forbidden_tags={"waste_gust"},
            close_pressure=close_pressure,
            can_make_crustle_wall_this_turn=wall_this_turn,
            values_mist_energy=True,
        )

    if wall_this_turn and s.matchup.prefers_crustle_wall:
        return s, TurnPlan(
            mode="setup_crustle_wall_now",
            priority=85,
            active_goal="crustle",
            search_goal="crustle_piece",
            search_target_ids=[CardIds.CRUSTLE, CardIds.DWEBBLE, CardIds.GROW_GRASS_ENERGY, CardIds.BASIC_GRASS, CardIds.MIST_ENERGY],
            required_basic_ids={CardIds.DWEBBLE},
            wants_active_crustle=True,
            wants_crustle_evolution=True,
            wants_dwebble_ascension=s.active_is_dwebble,
            hilda_pair_preferences=default_hilda_pairs,
            petrel_target_ids=[CardIds.HILDA, CardIds.BUDDY_BUDDY_POFFIN, CardIds.ULTRA_BALL, CardIds.SWITCH],
            poffin_basic_ids=[CardIds.DWEBBLE, CardIds.MEGA_KANGASKHAN_EX],
            attach_target_role="crustle_line",
            attach_energy_preference=[CardIds.GROW_GRASS_ENERGY, CardIds.BASIC_GRASS, CardIds.MIST_ENERGY, CardIds.SPIKY_ENERGY],
            switch_target_role="crustle",
            reasons=["wall_can_be_made"],
            required_tags={"evolve_crustle", "switch_crustle_setup"},
            forbidden_tags={"waste_gust"},
            can_make_crustle_wall_this_turn=True,
            close_pressure=close_pressure,
            values_mist_energy=s.matchup.values_mist_energy,
        )

    if s.matchup.name == "dragapult_ex" and s.matchup.values_bench_protection:
        if s.dwebble_in_play == 0 or s.crustle_in_play == 0:
            return s, TurnPlan(
                mode="setup_crustle",
                priority=75,
                active_goal="crustle",
                search_goal="crustle_piece",
                search_target_ids=[CardIds.DWEBBLE, CardIds.CRUSTLE, CardIds.MIST_ENERGY, CardIds.GROW_GRASS_ENERGY, CardIds.BASIC_GRASS],
                required_basic_ids={CardIds.DWEBBLE},
                wants_crustle_evolution=True,
                hilda_pair_preferences=default_hilda_pairs,
                petrel_target_ids=[CardIds.HILDA, CardIds.BUDDY_BUDDY_POFFIN, CardIds.ULTRA_BALL],
                poffin_basic_ids=[CardIds.DWEBBLE, CardIds.MEGA_KANGASKHAN_EX],
                attach_target_role="crustle_line",
                attach_energy_preference=[CardIds.MIST_ENERGY, CardIds.GROW_GRASS_ENERGY, CardIds.BASIC_GRASS],
                switch_target_role="crustle",
                reasons=["dragapult_wall_plus_mist"],
                required_tags={"bench_dwebble", "evolve_crustle", "mist_protect"},
                close_pressure=close_pressure,
                values_mist_energy=True,
            )

    if s.crustle_in_play == 0 and (s.matchup.prefers_crustle_wall or s.opponent_active_is_ex):
        return s, TurnPlan(
            mode="setup_crustle",
            priority=75,
            active_goal="crustle",
            search_goal="crustle_piece",
            search_target_ids=[CardIds.DWEBBLE, CardIds.CRUSTLE, CardIds.GROW_GRASS_ENERGY, CardIds.BASIC_GRASS, CardIds.MIST_ENERGY],
            required_basic_ids={CardIds.DWEBBLE},
            wants_crustle_evolution=True,
            hilda_pair_preferences=default_hilda_pairs,
            petrel_target_ids=[CardIds.HILDA, CardIds.BUDDY_BUDDY_POFFIN, CardIds.ULTRA_BALL],
            poffin_basic_ids=[CardIds.DWEBBLE, CardIds.MEGA_KANGASKHAN_EX],
            attach_target_role="crustle_line",
            attach_energy_preference=[CardIds.GROW_GRASS_ENERGY, CardIds.BASIC_GRASS, CardIds.MIST_ENERGY],
            switch_target_role="crustle",
            reasons=["need_crustle_wall"],
            required_tags={"bench_dwebble", "evolve_crustle"},
            close_pressure=close_pressure,
            values_mist_energy=s.matchup.values_mist_energy,
        )

    if wants_backup:
        return s, TurnPlan(
            mode="setup_backup",
            priority=58,
            active_goal="stabilize",
            search_goal="basic_setup",
            search_target_ids=[CardIds.DWEBBLE, CardIds.MEGA_KANGASKHAN_EX, CardIds.CRUSTLE, CardIds.MIST_ENERGY, CardIds.GROW_GRASS_ENERGY],
            required_basic_ids={CardIds.DWEBBLE, CardIds.MEGA_KANGASKHAN_EX},
            target_field_count=3,
            hilda_pair_preferences=default_hilda_pairs,
            petrel_target_ids=[CardIds.BUDDY_BUDDY_POFFIN, CardIds.HILDA, CardIds.ULTRA_BALL],
            poffin_basic_ids=[CardIds.DWEBBLE, CardIds.MEGA_KANGASKHAN_EX],
            attach_target_role="best_setup_target",
            attach_energy_preference=[CardIds.MIST_ENERGY, CardIds.GROW_GRASS_ENERGY, CardIds.BASIC_GRASS, CardIds.SPIKY_ENERGY],
            switch_target_role="safest_wall_or_tank",
            reasons=["want_more_backup"],
            want_more_backup=True,
            close_pressure=close_pressure,
            values_mist_energy=s.matchup.values_mist_energy,
        )

    if s.active_is_kang or s.kang_in_play > 0:
        if s.active_energy < 2:
            return s, TurnPlan(
                mode="attack_continuity",
                priority=60,
                active_goal="kang",
                wants_active_kang=True,
                wants_kang_draw=s.active_is_kang,
                wants_kang_third_energy=True,
                search_goal="kang_attack_pieces",
                search_target_ids=[CardIds.MEGA_KANGASKHAN_EX, CardIds.SPIKY_ENERGY, CardIds.MIST_ENERGY, CardIds.GROW_GRASS_ENERGY, CardIds.BASIC_GRASS],
                hilda_pair_preferences=default_hilda_pairs,
                petrel_target_ids=[CardIds.HILDA, CardIds.LILLIE, CardIds.ULTRA_BALL, CardIds.JUMBO_ICE_CREAM],
                attach_target_role="active_kang",
                attach_energy_preference=[CardIds.SPIKY_ENERGY, CardIds.MIST_ENERGY, CardIds.GROW_GRASS_ENERGY, CardIds.BASIC_GRASS],
                switch_target_role="kang",
                reasons=["attack_continuity_risk"],
                required_tags={"attach_kang_energy"},
                close_pressure=close_pressure,
                values_mist_energy=s.matchup.values_mist_energy,
            )
        return s, TurnPlan(
            mode="kang_engine",
            priority=65,
            active_goal="kang",
            wants_active_kang=True,
            wants_kang_draw=True,
            wants_kang_third_energy=s.active_energy < 3,
            search_goal="kang_engine",
            search_target_ids=[CardIds.MEGA_KANGASKHAN_EX, CardIds.SPIKY_ENERGY, CardIds.MIST_ENERGY, CardIds.GROW_GRASS_ENERGY, CardIds.BASIC_GRASS],
            hilda_pair_preferences=default_hilda_pairs,
            petrel_target_ids=[CardIds.HILDA, CardIds.LILLIE, CardIds.ULTRA_BALL, CardIds.JUMBO_ICE_CREAM],
            attach_target_role="active_kang",
            attach_energy_preference=[CardIds.SPIKY_ENERGY, CardIds.MIST_ENERGY, CardIds.GROW_GRASS_ENERGY, CardIds.BASIC_GRASS],
            switch_target_role="kang",
            reasons=["kang_engine_available"],
            required_tags={"run_errand", "attach_kang_energy"},
            close_pressure=close_pressure,
            values_mist_energy=s.matchup.values_mist_energy,
        )

    if s.kang_in_play == 0:
        return s, TurnPlan(
            mode="setup_kangaskhan",
            priority=55,
            active_goal="kang",
            search_goal="kang",
            search_target_ids=[CardIds.MEGA_KANGASKHAN_EX, CardIds.SPIKY_ENERGY, CardIds.MIST_ENERGY, CardIds.GROW_GRASS_ENERGY, CardIds.BASIC_GRASS],
            required_basic_ids={CardIds.MEGA_KANGASKHAN_EX},
            hilda_pair_preferences=default_hilda_pairs,
            petrel_target_ids=[CardIds.HILDA, CardIds.LILLIE, CardIds.ULTRA_BALL, CardIds.JUMBO_ICE_CREAM],
            poffin_basic_ids=[CardIds.MEGA_KANGASKHAN_EX, CardIds.DWEBBLE],
            attach_target_role="kang_line",
            attach_energy_preference=[CardIds.SPIKY_ENERGY, CardIds.MIST_ENERGY, CardIds.GROW_GRASS_ENERGY, CardIds.BASIC_GRASS],
            switch_target_role="kang",
            reasons=["need_kang_engine"],
            required_tags={"bench_kang"},
            close_pressure=close_pressure,
            values_mist_energy=s.matchup.values_mist_energy,
        )

    if close_pressure:
        return s, TurnPlan(
            mode="close_pressure",
            priority=50,
            active_goal="attack",
            search_goal="gust",
            attack_now=True,
            search_target_ids=[],
            petrel_target_ids=[CardIds.BOSS_ORDERS, CardIds.LISIA, CardIds.ERI, CardIds.XEROSIC],
            switch_target_role="best_attacker",
            reasons=["close_pressure"],
            required_tags={"boss_for_prize", "gust_low_hp", "gust_multi_prize"},
            close_pressure=True,
            values_mist_energy=s.matchup.values_mist_energy,
        )

    return s, TurnPlan(
        mode="stabilize",
        priority=10,
        active_goal="keep",
        search_goal="resource",
        search_target_ids=[CardIds.DWEBBLE, CardIds.MEGA_KANGASKHAN_EX, CardIds.CRUSTLE, CardIds.MIST_ENERGY, CardIds.GROW_GRASS_ENERGY],
        hilda_pair_preferences=default_hilda_pairs,
        petrel_target_ids=[CardIds.HILDA, CardIds.LILLIE, CardIds.ULTRA_BALL],
        poffin_basic_ids=[CardIds.DWEBBLE, CardIds.MEGA_KANGASKHAN_EX],
        attach_target_role="best_setup_target",
        attach_energy_preference=[CardIds.MIST_ENERGY, CardIds.GROW_GRASS_ENERGY, CardIds.BASIC_GRASS, CardIds.SPIKY_ENERGY],
        switch_target_role="safest_wall_or_tank",
        reasons=["default_stabilize"],
        values_mist_energy=s.matchup.values_mist_energy,
    )


def _gust_flags(snapshot) -> tuple[bool, bool, bool, bool]:
    if not snapshot.can_attack_now:
        return False, False, False, False
    gust_for_win = False
    gust_for_prize = False
    gust_for_stall = False
    for target in snapshot.opponent_bench:
        hp = getattr(target, "hp", 999)
        can_ko = snapshot.current_attack_damage >= hp > 0
        if can_ko and prize_count(target) >= snapshot.my_prizes_left:
            gust_for_win = True
        if can_ko and (prize_count(target) >= 2 or hp <= 120):
            gust_for_prize = True
        if not can_ko and hp > 120 and energy_count(target) == 0:
            gust_for_stall = True
    return gust_for_win or gust_for_prize or gust_for_stall, gust_for_win, gust_for_prize, gust_for_stall


def _bench_risk(snapshot) -> bool:
    if not snapshot.matchup.values_bench_protection:
        return False
    for card in snapshot.bench:
        if getattr(card, "id", None) in {CardIds.DWEBBLE, CardIds.CRUSTLE, CardIds.MEGA_KANGASKHAN_EX} and getattr(card, "hp", 999) <= 80:
            return True
    return False


def build_state_view(snapshot: BoardSnapshot, plan: TurnPlan, deck_knowledge=None):
    active = snapshot.active
    setup_missing_crustle = snapshot.crustle_in_play == 0
    setup_missing_kangaskhan = snapshot.kang_in_play == 0
    bench_basic_count = sum(1 for c in snapshot.bench if is_basic_pokemon(c))
    field_basic_count = sum(1 for c in snapshot.field if is_basic_pokemon(c))
    empty_bench = len(snapshot.bench) == 0
    only_one = snapshot.field_count <= 1
    active_prizes = prize_count(active)
    opponent_can_win_by_active_ko = snapshot.opponent_prizes_left <= active_prizes
    prevent_loss = snapshot.active_under_ko_threat and (only_one or opponent_can_win_by_active_ko)
    heal_prevents = active is not None and snapshot.active_hp <= snapshot.opponent_estimated_damage < snapshot.active_hp + 80
    jumbo = active is not None and snapshot.active_energy >= 3 and heal_prevents
    bianca = active is not None and getattr(active, "hp", 999) <= 30 and snapshot.opponent_estimated_damage >= getattr(active, "hp", 999)
    heal_window = jumbo or bianca
    disruption_window = getattr(snapshot.op_state, "handCount", 0) >= 5 or (snapshot.wall_online and snapshot.matchup.values_disruption)
    gust_window, gust_for_win, gust_for_prize, gust_for_stall = _gust_flags(snapshot)
    bench_risk = _bench_risk(snapshot)
    phase = "midgame"
    if plan.mode == "finish":
        phase = "close_game"
    elif plan.mode in {"survival_setup", "setup_crustle_wall_now", "setup_crustle", "setup_kangaskhan", "protect_bench_vs_dragapult"}:
        phase = "setup"
    elif plan.mode == "prevent_loss":
        phase = "prevent_loss"
    elif plan.mode == "wall_and_tax":
        phase = "wall_lock"
    elif plan.mode in {"kang_engine", "tank_and_heal", "attack_continuity"}:
        phase = "tank_cycle"
    elif plan.mode in {"disruption_loop", "close_pressure"}:
        phase = "disruption"

    temp = SimpleNamespace(
        wall_online=snapshot.wall_online,
        dwebble_in_play=snapshot.dwebble_in_play,
        setup_missing_crustle=setup_missing_crustle,
        crustle_in_play=snapshot.crustle_in_play,
        kangaskhan_in_play=snapshot.kang_in_play,
        active_is_kangaskhan=snapshot.active_is_kang,
        active_energy=snapshot.active_energy,
        bench_risk=bench_risk,
        heal_prevents_ko=heal_prevents,
        bianca_window=bianca,
        disruption_window=disruption_window,
        gust_for_win=gust_for_win,
        gust_for_prize=gust_for_prize,
        my_prizes_left=snapshot.my_prizes_left,
        can_attack_now=snapshot.can_attack_now,
        must_bench_basic=plan.must_prevent_no_active,
        active_is_crustle=snapshot.active_is_crustle,
        active_under_ko_threat=snapshot.active_under_ko_threat,
        gust_for_stall=gust_for_stall,
    )
    line_states = build_line_states(temp, snapshot.matchup, active, snapshot.opponent_active, deck_knowledge=deck_knowledge)
    tags = [plan.mode] + list(plan.reasons) + snapshot.matchup.tags
    if setup_missing_crustle:
        tags.append("crustle_not_online")
    if snapshot.wall_online:
        tags.append("wall_online")
    if snapshot.active_is_kang:
        tags.append("kang_active")
    if heal_prevents:
        tags.append("heal_prevents_ko")
    if bench_risk:
        tags.append("bench_risk")
    if plan.must_prevent_no_active:
        tags.append("must_bench_basic")
    if snapshot.matchup.values_mist_energy:
        tags.append("mist_matchup")
    return SimpleNamespace(
        phase=phase,
        primary_plan=plan.mode,
        matchup=snapshot.matchup,
        opponent_active_is_ex=snapshot.opponent_active_is_ex,
        active_id=snapshot.active_id,
        active_name=get_card_name(active) if active is not None else None,
        active_energy=snapshot.active_energy,
        active_damage=damage_taken(active),
        active_remaining_hp=snapshot.active_hp,
        opponent_estimated_damage=snapshot.opponent_estimated_damage,
        dwebble_in_play=snapshot.dwebble_in_play,
        crustle_in_play=snapshot.crustle_in_play,
        kangaskhan_in_play=snapshot.kang_in_play,
        needs_setup=setup_missing_crustle or setup_missing_kangaskhan,
        can_attack_now=snapshot.can_attack_now,
        my_prizes_left=snapshot.my_prizes_left,
        opponent_prizes_left=snapshot.opponent_prizes_left,
        prize_diff=snapshot.my_prizes_left - snapshot.opponent_prizes_left,
        bench_space=snapshot.bench_space,
        field_count=snapshot.field_count,
        field_basic_count=field_basic_count,
        bench_basic_count=bench_basic_count,
        empty_bench=empty_bench,
        only_one_pokemon_in_play=only_one,
        must_bench_basic=plan.must_prevent_no_active,
        setup_missing_crustle=setup_missing_crustle,
        setup_missing_kangaskhan=setup_missing_kangaskhan,
        wall_is_valid=snapshot.wall_valid,
        active_is_crustle=snapshot.active_is_crustle,
        active_is_kangaskhan=snapshot.active_is_kang,
        active_is_dwebble=snapshot.active_is_dwebble,
        wall_online=snapshot.wall_online,
        bench_risk=bench_risk,
        active_under_ko_threat=snapshot.active_under_ko_threat,
        heal_window=heal_window,
        heal_prevents_ko=heal_prevents,
        jumbo_heal_option=jumbo,
        jumbo_prevents_ko=jumbo,
        bianca_prevents_ko=bianca,
        has_effective_heal=heal_window,
        bianca_window=bianca,
        disruption_window=disruption_window,
        gust_window=gust_window,
        gust_for_win=gust_for_win,
        gust_for_prize=gust_for_prize,
        gust_for_stall=gust_for_stall,
        prevent_loss=prevent_loss,
        close_game=plan.mode == "finish",
        close_pressure=plan.close_pressure,
        direct_win_available=plan.direct_win_available,
        can_make_crustle_wall_this_turn=plan.can_make_crustle_wall_this_turn,
        can_run_errand_or_attack=snapshot.active_is_kang,
        current_attack_damage=snapshot.current_attack_damage,
        safe_draws=snapshot.safe_draws,
        plan_priority=plan.priority,
        line_states=line_states,
        state_tags=tags,
        turn_plan=plan,
    )
