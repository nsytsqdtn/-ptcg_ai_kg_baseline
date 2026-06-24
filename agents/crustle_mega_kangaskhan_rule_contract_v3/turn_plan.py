from __future__ import annotations

from dataclasses import dataclass, field
from collections import Counter
from types import SimpleNamespace
from typing import Any

from cg.api import OptionType
from runtime import CardIds, energy_count, is_ex_card, prize_count, damage_taken
from matchup_profile import detect_matchup_profile, MatchupProfile


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
    supporter_available: bool
    can_win_now: bool
    core_bench_at_risk: bool
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
        wall_valid = active_is_crustle and opponent_active_is_ex
        wall_online = active_is_crustle and (opponent_active_is_ex or matchup.prefers_crustle_wall)
        active_hp = getattr(active, "hp", 0) if active is not None else 0
        active_energy = energy_count(active)
        active_damage = damage_taken(active)
        opp_damage = estimate_opponent_damage(opponent_active, matchup)
        if wall_valid and matchup.prefers_crustle_wall:
            if matchup.name == "dragapult_ex":
                opp_damage = max(40, int(opp_damage * 0.25))
            else:
                opp_damage = 0
        current_damage = estimate_current_attack_damage(active)
        can_attack_now = any(o.type == OptionType.ATTACK for o in getattr(obs.select, "option", []) or [])
        gust_targets = [c for c in [opponent_active] + opponent_bench if c is not None]
        prize_count_me = len(getattr(me, "prize", []) or [])
        safe_draws = max(0, getattr(me, "deckCount", 0) - prize_count_me - 1)
        core_bench_at_risk = any(
            getattr(card, "id", None) in {CardIds.DWEBBLE, CardIds.CRUSTLE, CardIds.MEGA_KANGASKHAN_EX}
            and getattr(card, "hp", 999) <= 80
            for card in bench
        )
        tmp = cls(
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
            my_prizes_left=prize_count_me,
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
            safe_draws=safe_draws,
            supporter_available=not getattr(state, "supporterPlayed", False),
            can_win_now=False,
            core_bench_at_risk=core_bench_at_risk,
            gust_targets=gust_targets,
        )
        tmp.can_win_now = direct_win_available(tmp)
        return tmp


def estimate_opponent_damage(opponent_active, matchup: MatchupProfile) -> int:
    if opponent_active is None:
        return 0
    attached = energy_count(opponent_active)
    damage = 70 + 45 * attached
    if is_ex_card(opponent_active):
        damage += 40
    if matchup.threat.has_fast_prize_pressure:
        damage += 70
    if matchup.threat.has_bench_spread:
        damage += 40
    return damage


def estimate_current_attack_damage(active) -> int:
    if active is None:
        return 0
    attached = energy_count(active)
    cid = getattr(active, "id", None)
    if cid == CardIds.CRUSTLE:
        return 120 if attached >= 1 else 0
    if cid == CardIds.MEGA_KANGASKHAN_EX:
        return 200 if attached >= 3 else 0
    return 0


def has_live_deck_card(deck_knowledge, card_id: int) -> bool | None:
    if deck_knowledge is None:
        return None
    return deck_knowledge.deck_has(card_id)


def _target_can_be_ko(snapshot: BoardSnapshot, target) -> bool:
    return target is not None and snapshot.current_attack_damage >= getattr(target, "hp", 999) > 0


def direct_win_available(snapshot: BoardSnapshot) -> bool:
    if not snapshot.can_attack_now:
        return False
    if _target_can_be_ko(snapshot, snapshot.opponent_active) and prize_count(snapshot.opponent_active) >= snapshot.my_prizes_left:
        return True
    hand_ids = set(snapshot.hand_counts)
    has_gust = bool(hand_ids & {CardIds.BOSS_ORDERS, CardIds.LISIA})
    if has_gust:
        for card in snapshot.opponent_bench:
            if _target_can_be_ko(snapshot, card) and prize_count(card) >= snapshot.my_prizes_left:
                return True
    return False


def can_take_prize(snapshot: BoardSnapshot) -> bool:
    if not snapshot.can_attack_now:
        return False
    if _target_can_be_ko(snapshot, snapshot.opponent_active):
        return True
    return any(_target_can_be_ko(snapshot, card) for card in snapshot.opponent_bench)


def can_make_crustle_wall_this_turn(snapshot: BoardSnapshot) -> bool:
    if snapshot.wall_online:
        return False
    if snapshot.active_is_dwebble:
        return True
    if snapshot.crustle_in_play > 0 and not snapshot.active_is_crustle:
        return True
    if snapshot.dwebble_in_play > 0:
        if snapshot.hand_counts[CardIds.CRUSTLE] > 0:
            return True
        live = has_live_deck_card(snapshot.deck_knowledge, CardIds.CRUSTLE)
        return live is not False
    return False


def kang_engine_allowed(snapshot, obligations) -> bool:
    if getattr(obligations, "must_add_backup", False):
        return False
    if getattr(obligations, "must_not_draw", False):
        return False
    if snapshot.field_count < 2:
        return False
    if snapshot.active_under_ko_threat and snapshot.field_count < 3:
        return False
    if not (snapshot.wall_online or snapshot.dwebble_in_play > 0 or snapshot.crustle_in_play > 0):
        return False
    return True


@dataclass(frozen=True)
class TurnPlan:
    objective: str
    priority: int = 0
    active_goal: str | None = None
    search_goal: str | None = None
    attack_goal: str | None = None
    disruption_goal: str | None = None
    search_target_ids: tuple[int, ...] = ()
    poffin_basic_ids: tuple[int, ...] = ()
    hilda_pair_preferences: tuple[tuple[int, int], ...] = ()
    petrel_target_ids: tuple[int, ...] = ()
    attach_energy_preference: tuple[int, ...] = ()
    attach_target_role: str | None = None
    switch_target_role: str | None = None
    gust_target_role: str | None = None
    heal_card_id: int | None = None
    can_win_now: bool = False
    reasons: tuple[str, ...] = ()

    # Compatibility with older modules.
    @property
    def mode(self) -> str:
        return self.objective

    @property
    def must_prevent_no_active(self) -> bool:
        return self.objective == "setup_backup" or "must_prevent_no_active" in self.reasons

    @property
    def direct_win_available(self) -> bool:
        return self.can_win_now

    @property
    def can_make_crustle_wall_this_turn(self) -> bool:
        return self.objective == "setup_crustle_wall" or "wall_can_be_made" in self.reasons

    @property
    def heal_card(self):
        return self.heal_card_id

    @property
    def attack_now(self) -> bool:
        return self.objective == "finish"


def build_plan_from_snapshot(snapshot: BoardSnapshot, obligations, deck_knowledge=None) -> TurnPlan:
    wall_this_turn = can_make_crustle_wall_this_turn(snapshot)

    if snapshot.can_win_now:
        return TurnPlan(
            objective="finish",
            priority=100,
            attack_goal="win_now",
            petrel_target_ids=(CardIds.BOSS_ORDERS, CardIds.LISIA),
            can_win_now=True,
            reasons=("verified_win_candidate",),
        )

    if getattr(obligations, "must_add_backup", False):
        return TurnPlan(
            objective="setup_backup",
            priority=95,
            active_goal="keep",
            search_goal="basic",
            search_target_ids=(CardIds.DWEBBLE, CardIds.MEGA_KANGASKHAN_EX, CardIds.CRUSTLE),
            poffin_basic_ids=(CardIds.DWEBBLE, CardIds.MEGA_KANGASKHAN_EX),
            hilda_pair_preferences=((CardIds.DWEBBLE, CardIds.GROW_GRASS_ENERGY), (CardIds.MEGA_KANGASKHAN_EX, CardIds.SPIKY_ENERGY), (CardIds.DWEBBLE, CardIds.MIST_ENERGY)),
            petrel_target_ids=(CardIds.BUDDY_BUDDY_POFFIN, CardIds.HILDA, CardIds.ULTRA_BALL),
            reasons=("must_prevent_no_active", "must_add_backup"),
        )

    if snapshot.active_under_ko_threat and snapshot.active_is_kang:
        return TurnPlan(
            objective="prevent_loss",
            priority=90,
            active_goal="preserve_core",
            search_goal="heal_or_switch",
            heal_card_id=CardIds.JUMBO_ICE_CREAM,
            petrel_target_ids=(CardIds.JUMBO_ICE_CREAM, CardIds.BIANCA_DEVOTION, CardIds.SWITCH),
            reasons=("active_ko_threat",),
        )

    if snapshot.matchup.threat.has_bench_spread and snapshot.core_bench_at_risk:
        return TurnPlan(
            objective="protect_bench_core",
            priority=86,
            search_goal="mist_or_wall",
            search_target_ids=(CardIds.MIST_ENERGY, CardIds.DWEBBLE, CardIds.CRUSTLE, CardIds.MEGA_KANGASKHAN_EX),
            hilda_pair_preferences=((CardIds.DWEBBLE, CardIds.MIST_ENERGY), (CardIds.CRUSTLE, CardIds.MIST_ENERGY), (CardIds.MEGA_KANGASKHAN_EX, CardIds.MIST_ENERGY)),
            attach_energy_preference=(CardIds.MIST_ENERGY, CardIds.GROW_GRASS_ENERGY),
            attach_target_role="core_bench_or_wall",
            reasons=("bench_spread_threat",),
        )

    if wall_this_turn and (snapshot.matchup.prefers_crustle_wall or snapshot.opponent_active_is_ex):
        return TurnPlan(
            objective="setup_crustle_wall",
            priority=84,
            active_goal="crustle",
            search_goal="crustle_piece",
            search_target_ids=(CardIds.CRUSTLE, CardIds.DWEBBLE, CardIds.GROW_GRASS_ENERGY, CardIds.BASIC_GRASS),
            poffin_basic_ids=(CardIds.DWEBBLE, CardIds.MEGA_KANGASKHAN_EX),
            hilda_pair_preferences=((CardIds.CRUSTLE, CardIds.GROW_GRASS_ENERGY), (CardIds.DWEBBLE, CardIds.GROW_GRASS_ENERGY), (CardIds.CRUSTLE, CardIds.BASIC_GRASS)),
            petrel_target_ids=(CardIds.HILDA, CardIds.BUDDY_BUDDY_POFFIN, CardIds.ULTRA_BALL, CardIds.SWITCH),
            attach_energy_preference=(CardIds.GROW_GRASS_ENERGY, CardIds.BASIC_GRASS),
            attach_target_role="crustle_line",
            switch_target_role="crustle",
            reasons=("wall_can_be_made",),
        )

    if snapshot.wall_online:
        return TurnPlan(
            objective="preserve_wall",
            priority=78,
            active_goal="crustle",
            search_goal="disruption_or_heal",
            search_target_ids=(CardIds.MIST_ENERGY, CardIds.SPIKY_ENERGY, CardIds.JUMBO_ICE_CREAM),
            hilda_pair_preferences=((CardIds.CRUSTLE, CardIds.MIST_ENERGY), (CardIds.CRUSTLE, CardIds.GROW_GRASS_ENERGY)),
            petrel_target_ids=(CardIds.ERI, CardIds.XEROSIC, CardIds.HAND_TRIMMER, CardIds.HANDHELD_FAN, CardIds.JUMBO_ICE_CREAM),
            attach_energy_preference=(CardIds.SPIKY_ENERGY, CardIds.MIST_ENERGY, CardIds.GROW_GRASS_ENERGY),
            attach_target_role="wall",
            reasons=("wall_online",),
        )

    if snapshot.crustle_in_play == 0 and (snapshot.matchup.prefers_crustle_wall or snapshot.opponent_active_is_ex):
        return TurnPlan(
            objective="setup_crustle_wall",
            priority=72,
            active_goal="crustle",
            search_goal="crustle_piece",
            search_target_ids=(CardIds.DWEBBLE, CardIds.CRUSTLE, CardIds.GROW_GRASS_ENERGY),
            poffin_basic_ids=(CardIds.DWEBBLE, CardIds.MEGA_KANGASKHAN_EX),
            hilda_pair_preferences=((CardIds.DWEBBLE, CardIds.GROW_GRASS_ENERGY), (CardIds.CRUSTLE, CardIds.GROW_GRASS_ENERGY)),
            petrel_target_ids=(CardIds.HILDA, CardIds.BUDDY_BUDDY_POFFIN, CardIds.ULTRA_BALL),
            attach_energy_preference=(CardIds.GROW_GRASS_ENERGY, CardIds.BASIC_GRASS),
            attach_target_role="crustle_line",
            reasons=("need_crustle_wall",),
        )

    if (snapshot.active_is_kang or snapshot.kang_in_play > 0) and kang_engine_allowed(snapshot, obligations):
        return TurnPlan(
            objective="kang_engine",
            priority=58,
            active_goal="kang",
            search_goal="resource",
            search_target_ids=(CardIds.MEGA_KANGASKHAN_EX, CardIds.SPIKY_ENERGY, CardIds.MIST_ENERGY),
            hilda_pair_preferences=((CardIds.MEGA_KANGASKHAN_EX, CardIds.SPIKY_ENERGY), (CardIds.MEGA_KANGASKHAN_EX, CardIds.MIST_ENERGY)),
            petrel_target_ids=(CardIds.LILLIE, CardIds.HILDA, CardIds.JUMBO_ICE_CREAM),
            attach_energy_preference=(CardIds.SPIKY_ENERGY, CardIds.MIST_ENERGY, CardIds.GROW_GRASS_ENERGY),
            attach_target_role="kang",
            reasons=("kang_engine_allowed",),
        )

    return TurnPlan(
        objective="stabilize",
        priority=40,
        active_goal="keep",
        search_goal="resource",
        search_target_ids=(CardIds.DWEBBLE, CardIds.CRUSTLE, CardIds.MEGA_KANGASKHAN_EX, CardIds.GROW_GRASS_ENERGY),
        poffin_basic_ids=(CardIds.DWEBBLE, CardIds.MEGA_KANGASKHAN_EX),
        hilda_pair_preferences=((CardIds.DWEBBLE, CardIds.GROW_GRASS_ENERGY), (CardIds.CRUSTLE, CardIds.GROW_GRASS_ENERGY), (CardIds.MEGA_KANGASKHAN_EX, CardIds.SPIKY_ENERGY)),
        petrel_target_ids=(CardIds.HILDA, CardIds.BUDDY_BUDDY_POFFIN, CardIds.ULTRA_BALL),
        reasons=("default_stabilize",),
    )


def build_turn_plan(obs_or_snapshot, obligations=None, deck_knowledge=None):
    if isinstance(obs_or_snapshot, BoardSnapshot):
        return build_plan_from_snapshot(obs_or_snapshot, obligations, deck_knowledge)
    snapshot = BoardSnapshot.from_obs(obs_or_snapshot, deck_knowledge)
    if obligations is None:
        from obligations import build_obligations
        obligations = build_obligations(snapshot, deck_knowledge)
    plan = build_plan_from_snapshot(snapshot, obligations, deck_knowledge)
    return snapshot, plan


def build_state_view(snapshot, plan, deck_knowledge=None):
    return SimpleNamespace(
        primary_plan=plan.objective,
        turn_plan=plan,
        matchup=snapshot.matchup,
        active_id=snapshot.active_id,
        active_energy=snapshot.active_energy,
        active_damage=snapshot.active_damage,
        active_remaining_hp=snapshot.active_hp,
        dwebble_in_play=snapshot.dwebble_in_play,
        crustle_in_play=snapshot.crustle_in_play,
        kangaskhan_in_play=snapshot.kang_in_play,
        bench_space=snapshot.bench_space,
        field_count=snapshot.field_count,
        must_bench_basic=plan.must_prevent_no_active,
        setup_missing_crustle=snapshot.crustle_in_play == 0,
        setup_missing_kangaskhan=snapshot.kang_in_play == 0,
        wall_online=snapshot.wall_online,
        wall_is_valid=snapshot.wall_valid,
        active_is_crustle=snapshot.active_is_crustle,
        active_is_kangaskhan=snapshot.active_is_kang,
        active_is_dwebble=snapshot.active_is_dwebble,
        active_under_ko_threat=snapshot.active_under_ko_threat,
        bench_risk=snapshot.core_bench_at_risk,
        my_prizes_left=snapshot.my_prizes_left,
        opponent_prizes_left=snapshot.opponent_prizes_left,
        can_attack_now=snapshot.can_attack_now,
        current_attack_damage=snapshot.current_attack_damage,
        close_game=plan.objective == "finish",
        direct_win_available=plan.can_win_now,
        can_make_crustle_wall_this_turn=plan.can_make_crustle_wall_this_turn,
        gust_for_win=plan.objective == "finish",
        gust_for_prize=False,
        gust_for_stall=False,
        jumbo_prevents_ko=plan.heal_card_id == CardIds.JUMBO_ICE_CREAM,
        bianca_prevents_ko=plan.heal_card_id == CardIds.BIANCA_DEVOTION,
        line_states=[],
        state_tags=[plan.objective, *plan.reasons, *snapshot.matchup.tags],
    )
