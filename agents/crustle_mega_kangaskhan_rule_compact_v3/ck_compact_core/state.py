from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from cg.api import OptionType

from .battle_model import AttackProfile, attacks_for, bench_counter_damage, best_usable_attack, energy_ids, grass_energy_count, retreat_cost, usable_attacks_for
from .deck_knowledge import DeckKnowledgeTracker
from .runtime import CardIds, CORE_POKEMON, count_ids, damage_taken, energy_count, get_card_name_en, get_card_name_zh, has_attached, hp_remaining, is_ex_card, max_hp, prize_count


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
    energy_ids: tuple[int, ...]
    grass_energy_count: int
    retreat_cost: int | None
    can_retreat_now: bool
    is_ex: bool
    prize_value: int
    is_active: bool
    bench_index: int | None = None
    attacks: tuple[AttackProfile, ...] = field(default_factory=tuple)
    usable_attacks: tuple[AttackProfile, ...] = field(default_factory=tuple)
    best_attack_damage: int = 0
    best_bench_damage: int = 0
    has_mist: bool = False

    @classmethod
    def from_card(cls, card: Any, is_active: bool = False, bench_index: int | None = None) -> "PokemonView":
        eid = tuple(energy_ids(card))
        attacks = tuple(attacks_for(card))
        usable = tuple(usable_attacks_for(card))
        best = best_usable_attack(card)
        rc = retreat_cost(card)
        return cls(
            card=card,
            card_id=getattr(card, "id", None),
            name_en=get_card_name_en(card),
            name_zh=get_card_name_zh(card),
            hp=hp_remaining(card),
            max_hp=max_hp(card),
            damage=damage_taken(card),
            energy_count=energy_count(card),
            energy_ids=eid,
            grass_energy_count=grass_energy_count(card),
            retreat_cost=rc,
            can_retreat_now=(rc is not None and energy_count(card) >= (rc or 0)),
            is_ex=is_ex_card(card),
            prize_value=prize_count(card),
            is_active=is_active,
            bench_index=bench_index,
            attacks=attacks,
            usable_attacks=usable,
            best_attack_damage=best.damage if best is not None else 0,
            best_bench_damage=bench_counter_damage(best) if best is not None else 0,
            has_mist=(CardIds.MIST_ENERGY in eid),
        )


@dataclass(frozen=True)
class TargetView:
    pokemon: PokemonView
    slot: str
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
    current_active_damage_blocked: bool
    has_low_hp_core_bench: bool
    has_damaged_core_bench: bool
    has_unprotected_damaged_core_bench: bool
    active_under_threat: bool
    active_threat_damage_estimate: int
    opponent_threat: Any

    can_attack_now: bool
    active_attack_damage: int
    crustle_attack_ready: bool
    kang_attack_ready: bool
    opponent_active_energy_count: int

    @classmethod
    def from_obs(cls, obs: Any, deck_knowledge: DeckKnowledgeTracker | None) -> "CompactState":
        cur = obs.current
        yi = cur.yourIndex
        oi = 1 - yi
        me = cur.players[yi]
        opp = cur.players[oi]

        active = (getattr(me, "active", []) or [None])[0]
        bench = list(getattr(me, "bench", []) or [])
        field = ([active] if active is not None else []) + bench
        hand = list(getattr(me, "hand", []) or [])
        discard = list(getattr(me, "discard", []) or [])
        opp_active = (getattr(opp, "active", []) or [None])[0]
        opp_bench = list(getattr(opp, "bench", []) or [])

        active_view = PokemonView.from_card(active, is_active=True) if active is not None else None
        bench_views = [PokemonView.from_card(c, is_active=False, bench_index=i) for i, c in enumerate(bench)]
        opponent_active_view = PokemonView.from_card(opp_active, is_active=True) if opp_active is not None else None
        opponent_bench_views = [PokemonView.from_card(c, is_active=False, bench_index=i) for i, c in enumerate(opp_bench)]
        opponent_targets: list[TargetView] = []
        if opponent_active_view is not None:
            opponent_targets.append(TargetView(opponent_active_view, "active", is_basic_target(opp_active)))
        for view in opponent_bench_views:
            opponent_targets.append(TargetView(view, "bench", is_basic_target(view.card)))

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
        context_name = str(getattr(select, "context", "MAIN")).split(".")[-1]
        phase = "MAIN" if context_name == "MAIN" else "SELECT"
        n = len(options)
        select_min = max(0, min(int(getattr(select, "minCount", 1) or 0), n)) if select is not None else 0
        select_max = max(select_min, min(int(getattr(select, "maxCount", 1) or 1), n)) if select is not None else 0

        active_id = getattr(active, "id", None)
        dwebble_active = active_id == CardIds.DWEBBLE
        crustle_active = active_id == CardIds.CRUSTLE
        kang_active = active_id == CardIds.MEGA_KANGASKHAN_EX
        opp_hand_count = int(getattr(opp, "handCount", len(getattr(opp, "hand", []) or [])) or 0)

        active_damage = active_view.best_attack_damage if active_view is not None and can_attack else 0
        crustle_ready = bool(crustle_active and can_attack) or any(v.card_id == CardIds.CRUSTLE and v.usable_attacks for v in bench_views)
        kang_ready = bool(kang_active and can_attack) or any(v.card_id == CardIds.MEGA_KANGASKHAN_EX and v.usable_attacks for v in bench_views)

        has_low_hp_core_bench = any(v.card_id in CORE_POKEMON and v.hp <= 80 for v in bench_views)
        has_damaged_core_bench = any(v.card_id in CORE_POKEMON and v.damage > 0 for v in bench_views)
        has_unprotected_damaged_core_bench = any(v.card_id in CORE_POKEMON and v.damage > 0 and not v.has_mist for v in bench_views)

        # Build a partial state first; threat_plan needs field and view data.
        partial = cls(
            obs=obs, deck_knowledge=deck_knowledge, current=cur, my_index=yi, opp_index=oi, me=me, opp=opp,
            turn=int(getattr(cur, "turn", 0) or 0), phase=phase, context_name=context_name, select_min=select_min, select_max=select_max,
            my_prizes_left=prize_me, opp_prizes_left=prize_opp, my_deck_count=my_deck_count, opp_deck_count=opp_deck_count,
            safe_draws=safe_draws, deck_danger=deck_danger, supporter_available=not bool(getattr(cur, "supporterPlayed", False)),
            active=active, active_view=active_view, bench=bench, bench_views=bench_views, field=field, field_counts=field_counts,
            hand=hand, hand_counts=hand_counts, discard=discard, discard_counts=discard_counts,
            bench_space=max(0, int(getattr(me, "benchMax", 5) or 5) - len(bench)), field_count=len(field),
            opponent_active=opp_active, opponent_active_view=opponent_active_view, opponent_bench=opp_bench, opponent_bench_views=opponent_bench_views,
            opponent_targets=opponent_targets, opponent_hand_count=opp_hand_count,
            active_id=active_id, dwebble_active=dwebble_active, crustle_active=crustle_active, kang_active=kang_active,
            has_dwebble=field_counts[CardIds.DWEBBLE] > 0, has_crustle=field_counts[CardIds.CRUSTLE] > 0,
            has_kang=field_counts[CardIds.MEGA_KANGASKHAN_EX] > 0,
            dwebble_count=field_counts[CardIds.DWEBBLE], crustle_count=field_counts[CardIds.CRUSTLE], kang_count=field_counts[CardIds.MEGA_KANGASKHAN_EX],
            opponent_active_is_ex=is_ex_card(opp_active), current_active_damage_blocked=False,
            has_low_hp_core_bench=has_low_hp_core_bench, has_damaged_core_bench=has_damaged_core_bench,
            has_unprotected_damaged_core_bench=has_unprotected_damaged_core_bench, active_under_threat=False,
            active_threat_damage_estimate=0, opponent_threat=None,
            can_attack_now=can_attack, active_attack_damage=active_damage, crustle_attack_ready=crustle_ready, kang_attack_ready=kang_ready,
            opponent_active_energy_count=energy_count(opp_active),
        )
        from .threat_plan import build_opponent_threat_plan
        threat = build_opponent_threat_plan(partial)
        partial.opponent_threat = threat
        partial.active_under_threat = bool(threat.can_ko_active)
        partial.active_threat_damage_estimate = int(threat.effective_damage_to_active)
        partial.current_active_damage_blocked = bool(threat.blocked_by_crustle)
        return partial

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
        return any(v.card_id in CORE_POKEMON and card_id in v.energy_ids for v in self.bench_views)


def is_basic_target(card: Any) -> bool:
    if card is None:
        return False
    cid = getattr(card, "id", None)
    name = get_card_name_en(card).lower()
    if cid in {CardIds.DWEBBLE, CardIds.MEGA_KANGASKHAN_EX}:
        return True
    return not any(token in name for token in ["stage", "crustle", "lucario ex", "dragapult ex", "drakloak", "hariyama", "alakazam"])
