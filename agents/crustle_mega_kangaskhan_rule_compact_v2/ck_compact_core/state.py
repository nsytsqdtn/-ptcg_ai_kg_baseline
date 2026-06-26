from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from cg.api import OptionType

from .deck_knowledge import DeckKnowledgeTracker
from .runtime import (
    CardIds,
    CORE_POKEMON,
    count_ids,
    damage_taken,
    energy_count,
    get_card_name_en,
    get_card_name_zh,
    has_attached,
    hp_remaining,
    is_ex_card,
    max_hp,
    prize_count,
)


@dataclass(frozen=True)
class PokemonView:
    card: Any
    card_id: int | None
    name_en: str
    name_zh: str
    hp: int
    max_hp: int
    damage: int
    energy_count: int
    is_ex: bool
    prize_value: int
    is_active: bool
    bench_index: int | None = None

    @classmethod
    def from_card(cls, card: Any, is_active: bool = False, bench_index: int | None = None) -> "PokemonView":
        return cls(
            card=card,
            card_id=getattr(card, "id", None),
            name_en=get_card_name_en(card),
            name_zh=get_card_name_zh(card),
            hp=hp_remaining(card),
            max_hp=max_hp(card),
            damage=damage_taken(card),
            energy_count=energy_count(card),
            is_ex=is_ex_card(card),
            prize_value=prize_count(card),
            is_active=is_active,
            bench_index=bench_index,
        )


@dataclass(frozen=True)
class TargetView:
    pokemon: PokemonView
    slot: str              # active / bench
    is_basic: bool

    @property
    def card_id(self) -> int | None:
        return self.pokemon.card_id

    @property
    def name_en(self) -> str:
        return self.pokemon.name_en

    @property
    def name_zh(self) -> str:
        return self.pokemon.name_zh

    @property
    def hp(self) -> int:
        return self.pokemon.hp

    @property
    def prize_value(self) -> int:
        return self.pokemon.prize_value

    @property
    def is_ex(self) -> bool:
        return self.pokemon.is_ex


@dataclass
class CompactState:
    obs: Any
    deck_knowledge: DeckKnowledgeTracker | None
    current: Any
    my_index: int
    opp_index: int
    me: Any
    opp: Any

    turn: int
    phase: str
    context_name: str
    select_min: int
    select_max: int

    my_prizes_left: int
    opp_prizes_left: int
    my_deck_count: int
    opp_deck_count: int
    safe_draws: int
    deck_danger: bool
    supporter_available: bool

    active: Any | None
    active_view: PokemonView | None
    bench: list[Any]
    bench_views: list[PokemonView]
    field: list[Any]
    field_counts: Counter[int]
    hand: list[Any]
    hand_counts: Counter[int]
    discard: list[Any]
    discard_counts: Counter[int]
    bench_space: int
    field_count: int

    opponent_active: Any | None
    opponent_active_view: PokemonView | None
    opponent_bench: list[Any]
    opponent_bench_views: list[PokemonView]
    opponent_targets: list[TargetView]
    opponent_hand_count: int

    active_id: int | None
    dwebble_active: bool
    crustle_active: bool
    kang_active: bool
    has_dwebble: bool
    has_crustle: bool
    has_kang: bool
    dwebble_count: int
    crustle_count: int
    kang_count: int

    opponent_active_is_ex: bool
    wall_status: str
    wall_effective_now: bool
    wall_leak_reasons: list[str]
    has_low_hp_core_bench: bool
    has_damaged_core_bench: bool
    active_under_threat: bool
    active_threat_damage_estimate: int

    can_attack_now: bool
    active_attack_damage: int
    crustle_attack_ready: bool
    kang_attack_ready: bool
    opponent_active_energy_count: int

    # Lightweight debug material.
    reasons: list[str] = field(default_factory=list)

    @classmethod
    def from_obs(cls, obs: Any, deck_knowledge: DeckKnowledgeTracker | None = None) -> "CompactState":
        cur = obs.current
        yi = int(getattr(cur, "yourIndex", 0) or 0)
        oi = 1 - yi
        me = cur.players[yi]
        opp = cur.players[oi]

        active = (getattr(me, "active", []) or [None])[0]
        opp_active = (getattr(opp, "active", []) or [None])[0]
        bench = [c for c in (getattr(me, "bench", []) or []) if c is not None]
        opp_bench = [c for c in (getattr(opp, "bench", []) or []) if c is not None]
        field = [c for c in ([active] if active is not None else []) + bench if c is not None]
        hand = [c for c in (getattr(me, "hand", []) or []) if c is not None]
        discard = [c for c in (getattr(me, "discard", []) or []) if c is not None]

        active_view = PokemonView.from_card(active, is_active=True) if active is not None else None
        bench_views = [PokemonView.from_card(c, is_active=False, bench_index=i) for i, c in enumerate(bench)]
        opp_active_view = PokemonView.from_card(opp_active, is_active=True) if opp_active is not None else None
        opp_bench_views = [PokemonView.from_card(c, is_active=False, bench_index=i) for i, c in enumerate(opp_bench)]

        opponent_targets: list[TargetView] = []
        if opp_active_view is not None:
            opponent_targets.append(TargetView(opp_active_view, "active", is_basic_target(opp_active)))
        for pv in opp_bench_views:
            opponent_targets.append(TargetView(pv, "bench", is_basic_target(pv.card)))

        field_counts = count_ids(field)
        hand_counts = count_ids(hand)
        discard_counts = count_ids(discard)
        prize_me = len(getattr(me, "prize", []) or [])
        prize_opp = len(getattr(opp, "prize", []) or [])
        my_deck_count = int(getattr(me, "deckCount", 0) or 0)
        opp_deck_count = int(getattr(opp, "deckCount", 0) or 0)
        safe_draws = my_deck_count - prize_me - 1
        deck_danger = safe_draws <= 0
        select = getattr(obs, "select", None)
        options = list(getattr(select, "option", []) or [])
        can_attack = any(getattr(o, "type", None) == OptionType.ATTACK for o in options)

        active_id = getattr(active, "id", None)
        dwebble_active = active_id == CardIds.DWEBBLE
        crustle_active = active_id == CardIds.CRUSTLE
        kang_active = active_id == CardIds.MEGA_KANGASKHAN_EX
        opp_active_is_ex = is_ex_card(opp_active)
        wall_effective_now = crustle_active and opp_active_is_ex
        if not (field_counts[CardIds.DWEBBLE] or field_counts[CardIds.CRUSTLE]):
            wall_status = "absent"
        elif not crustle_active:
            wall_status = "building"
        elif wall_effective_now:
            wall_status = "online"
        else:
            wall_status = "leaky"

        has_low_hp_core_bench = any(
            getattr(c, "id", None) in CORE_POKEMON and hp_remaining(c) <= 80
            for c in bench
        )
        has_damaged_core_bench = any(
            getattr(c, "id", None) in CORE_POKEMON and damage_taken(c) > 0
            for c in bench
        )

        active_threat_damage_estimate = estimate_opponent_threat_damage(opp_active)
        active_under_threat = estimate_active_under_threat(
            active=active,
            opponent_active=opp_active,
            wall_effective_now=wall_effective_now,
            active_threat_damage_estimate=active_threat_damage_estimate,
        )
        wall_leak_reasons = build_wall_leak_reasons(
            wall_status=wall_status,
            wall_effective_now=wall_effective_now,
            active_under_threat=active_under_threat,
            has_low_hp_core_bench=has_low_hp_core_bench,
            has_damaged_core_bench=has_damaged_core_bench,
            deck_danger=deck_danger,
            opponent_active=opp_active,
        )

        active_damage = estimate_active_attack_damage(active, can_attack)
        crustle_ready = False
        kang_ready = False
        if crustle_active and can_attack:
            crustle_ready = True
        elif any(getattr(c, "id", None) == CardIds.CRUSTLE and energy_count(c) >= 3 for c in bench):
            crustle_ready = True
        if kang_active and can_attack:
            kang_ready = True
        elif any(getattr(c, "id", None) == CardIds.MEGA_KANGASKHAN_EX and energy_count(c) >= 3 for c in bench):
            kang_ready = True

        context_name = str(getattr(getattr(obs, "select", None), "context", "MAIN")).split(".")[-1]
        phase = "MAIN" if context_name == "MAIN" else "SELECT"
        n = len(options)
        select_min = max(0, min(int(getattr(select, "minCount", 1) or 0), n)) if select is not None else 0
        select_max = max(select_min, min(int(getattr(select, "maxCount", 1) or 1), n)) if select is not None else 0

        opp_hand_count = int(getattr(opp, "handCount", len(getattr(opp, "hand", []) or [])) or 0)

        return cls(
            obs=obs,
            deck_knowledge=deck_knowledge,
            current=cur,
            my_index=yi,
            opp_index=oi,
            me=me,
            opp=opp,
            turn=int(getattr(cur, "turn", 0) or 0),
            phase=phase,
            context_name=context_name,
            select_min=select_min,
            select_max=select_max,
            my_prizes_left=prize_me,
            opp_prizes_left=prize_opp,
            my_deck_count=my_deck_count,
            opp_deck_count=opp_deck_count,
            safe_draws=safe_draws,
            deck_danger=deck_danger,
            supporter_available=not bool(getattr(cur, "supporterPlayed", False)),
            active=active,
            active_view=active_view,
            bench=bench,
            bench_views=bench_views,
            field=field,
            field_counts=field_counts,
            hand=hand,
            hand_counts=hand_counts,
            discard=discard,
            discard_counts=discard_counts,
            bench_space=max(0, int(getattr(me, "benchMax", 5) or 5) - len(bench)),
            field_count=len(field),
            opponent_active=opp_active,
            opponent_active_view=opp_active_view,
            opponent_bench=opp_bench,
            opponent_bench_views=opp_bench_views,
            opponent_targets=opponent_targets,
            opponent_hand_count=opp_hand_count,
            active_id=active_id,
            dwebble_active=dwebble_active,
            crustle_active=crustle_active,
            kang_active=kang_active,
            has_dwebble=field_counts[CardIds.DWEBBLE] > 0,
            has_crustle=field_counts[CardIds.CRUSTLE] > 0,
            has_kang=field_counts[CardIds.MEGA_KANGASKHAN_EX] > 0,
            dwebble_count=field_counts[CardIds.DWEBBLE],
            crustle_count=field_counts[CardIds.CRUSTLE],
            kang_count=field_counts[CardIds.MEGA_KANGASKHAN_EX],
            opponent_active_is_ex=opp_active_is_ex,
            wall_status=wall_status,
            wall_effective_now=wall_effective_now,
            wall_leak_reasons=wall_leak_reasons,
            has_low_hp_core_bench=has_low_hp_core_bench,
            has_damaged_core_bench=has_damaged_core_bench,
            active_under_threat=active_under_threat,
            active_threat_damage_estimate=active_threat_damage_estimate,
            can_attack_now=can_attack,
            active_attack_damage=active_damage,
            crustle_attack_ready=crustle_ready,
            kang_attack_ready=kang_ready,
            opponent_active_energy_count=energy_count(opp_active),
        )

    def hand_has(self, card_id: int) -> bool:
        return self.hand_counts.get(card_id, 0) > 0

    def deck_has(self, card_id: int) -> bool | None:
        if self.deck_knowledge is None:
            return None
        try:
            return self.deck_knowledge.deck_has(card_id)
        except Exception:
            return None

    def card_status(self, card_id: int) -> str:
        value = self.deck_has(card_id)
        if value is True:
            return "confirmed"
        if value is False:
            return "dead"
        return "possible"

    def has_attached_to_core_bench(self, card_id: int) -> bool:
        return any(v.card_id in CORE_POKEMON and has_attached(v.card, card_id) for v in self.bench_views)


def is_basic_target(card: Any) -> bool:
    # Only exact card metadata is not consistently exposed. This heuristic is used
    # solely for Lisia's Appeal target preference and never for legality.
    if card is None:
        return False
    cid = getattr(card, "id", None)
    name = get_card_name_en(card).lower()
    if cid in {CardIds.DWEBBLE, CardIds.MEGA_KANGASKHAN_EX}:
        return True
    return not any(token in name for token in ["stage", "crustle", "lucario ex", "dragapult ex"])


def estimate_active_attack_damage(active: Any, can_attack: bool) -> int:
    if active is None or not can_attack:
        return 0
    cid = getattr(active, "id", None)
    if cid == CardIds.CRUSTLE:
        return 120
    if cid == CardIds.MEGA_KANGASKHAN_EX:
        return 200
    return 0



def estimate_opponent_threat_damage(opponent_active: Any) -> int:
    """Small, deliberately conservative threat estimate.

    This is not a damage calculator. It only feeds backup/heal urgency. Crustle's
    wall effect is handled separately by estimate_active_under_threat().
    """
    if opponent_active is None:
        return 0
    e = energy_count(opponent_active)
    is_ex = is_ex_card(opponent_active)
    if e >= 3:
        return 270 if is_ex else 210
    if e >= 2:
        return 240 if is_ex else 170
    if e >= 1:
        return 130 if is_ex else 90
    return 40 if is_ex else 20


def estimate_active_under_threat(active: Any, opponent_active: Any, wall_effective_now: bool, active_threat_damage_estimate: int) -> bool:
    if active is None or opponent_active is None:
        return False
    hp = hp_remaining(active)
    if hp <= 80:
        return True
    # If Crustle is actively walling an ex attacker, do not panic unless the wall
    # is already very damaged. This avoids returning to the old over-conservative
    # backup behavior.
    if wall_effective_now and hp > 120:
        return False
    if active_threat_damage_estimate >= hp:
        return True
    if is_ex_card(opponent_active) and energy_count(opponent_active) >= 2 and hp <= 260:
        return True
    if energy_count(opponent_active) >= 3 and hp <= 220:
        return True
    return False


def build_wall_leak_reasons(
    wall_status: str,
    wall_effective_now: bool,
    active_under_threat: bool,
    has_low_hp_core_bench: bool,
    has_damaged_core_bench: bool,
    deck_danger: bool,
    opponent_active: Any,
) -> list[str]:
    reasons: list[str] = []
    if wall_status == "leaky":
        reasons.append("opponent_active_not_ex")
    if wall_effective_now:
        reasons.append("opponent_active_ex_wallable")
    if active_under_threat and not wall_effective_now:
        reasons.append("active_under_threat")
    if has_low_hp_core_bench:
        reasons.append("low_hp_core_bench")
    elif has_damaged_core_bench:
        reasons.append("damaged_core_bench")
    if deck_danger:
        reasons.append("deck_danger")
    if opponent_active is not None and energy_count(opponent_active) >= 2:
        reasons.append("opponent_energy_ready")
    return reasons
