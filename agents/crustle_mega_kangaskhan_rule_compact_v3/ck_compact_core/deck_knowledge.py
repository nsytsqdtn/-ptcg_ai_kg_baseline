from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ZoneSnapshot:
    hand: Counter[int] = field(default_factory=Counter)
    discard: Counter[int] = field(default_factory=Counter)
    active: Counter[int] = field(default_factory=Counter)
    bench: Counter[int] = field(default_factory=Counter)
    attached: Counter[int] = field(default_factory=Counter)
    stadium: Counter[int] = field(default_factory=Counter)
    visible: Counter[int] = field(default_factory=Counter)


class DeckKnowledgeTracker:
    """Zone-based own-card knowledge.

    The tracker keeps public zones from the current observation and combines them
    with exact deck views observed during full-search effects. It does not guess
    prizes before a complete deck view. When a complete deck view exists, prizes
    are inferred as:

        initial decklist - visible zones - known deck - resolving effect card.

    If the arithmetic does not exactly match the prize count, prize knowledge is
    invalidated instead of being guessed.
    """

    def __init__(self, decklist: list[int]):
        self.full_deck = Counter(decklist)
        self.known_deck: Counter[int] | None = None
        self.known_prized: Counter[int] | None = None
        self.zones = ZoneSnapshot()
        self.last_prize_count: int | None = None
        self.last_hand_counts: Counter[int] = Counter()
        self.last_visible: Counter[int] = Counter()

    def reset(self) -> None:
        self.known_deck = None
        self.known_prized = None
        self.zones = ZoneSnapshot()
        self.last_prize_count = None
        self.last_hand_counts = Counter()
        self.last_visible = Counter()

    @staticmethod
    def _card_id(card: Any) -> int | None:
        if card is None:
            return None
        cid = getattr(card, "id", card if isinstance(card, int) else None)
        return int(cid) if cid is not None else None

    def _add_card(self, counts: Counter[int], card: Any) -> None:
        cid = self._card_id(card)
        if cid is not None:
            counts[cid] += 1

    def _add_pokemon_public(self, zone_counts: Counter[int], attached_counts: Counter[int], pokemon: Any) -> None:
        if pokemon is None:
            return
        self._add_card(zone_counts, pokemon)
        for zone_name in ("preEvolution", "energyCards", "energies", "tools"):
            for c in getattr(pokemon, zone_name, None) or []:
                self._add_card(attached_counts, c)

    def _build_zone_snapshot(self, obs, player, player_index: int) -> ZoneSnapshot:
        z = ZoneSnapshot()
        for card in getattr(player, "hand", []) or []:
            self._add_card(z.hand, card)
        for card in getattr(player, "discard", []) or []:
            self._add_card(z.discard, card)
        for pokemon in getattr(player, "active", []) or []:
            self._add_pokemon_public(z.active, z.attached, pokemon)
        for pokemon in getattr(player, "bench", []) or []:
            self._add_pokemon_public(z.bench, z.attached, pokemon)
        for card in getattr(obs.current, "stadium", []) or []:
            if card is not None and getattr(card, "playerIndex", player_index) == player_index:
                self._add_card(z.stadium, card)
        z.visible = z.hand + z.discard + z.active + z.bench + z.attached + z.stadium
        return z

    def _infer_prized_from_full_search(self, obs, player, player_index: int, deck_counts: Counter[int]) -> Counter[int] | None:
        visible = self.zones.visible.copy()
        visible += deck_counts
        effect = getattr(obs.select, "effect", None)
        if effect is not None and getattr(effect, "playerIndex", player_index) == player_index:
            cid = self._card_id(effect)
            if cid is not None:
                visible[cid] += 1

        remaining = self.full_deck.copy()
        for card_id, count in visible.items():
            remaining[card_id] -= count
            if remaining[card_id] < 0:
                return None
        inferred = Counter({cid: n for cid, n in remaining.items() if n > 0})
        prize_total = len(getattr(player, "prize", []) or [])
        if sum(inferred.values()) != prize_total:
            return None
        return inferred

    def _sync_known_deck_after_visible_change(self) -> None:
        """Best-effort maintenance of a previously known deck.

        Visible zones are authoritative. If a card newly appears in visible zones
        and it was in known_deck, decrement it. If a visible card disappears, do
        not add it back to deck; it may have moved to an unknown zone by a shuffle
        effect. If arithmetic becomes impossible, invalidate known_deck.
        """
        if self.known_deck is None:
            return
        delta_visible = self.zones.visible - self.last_visible
        if not delta_visible:
            return
        for cid, count in delta_visible.items():
            if self.known_deck.get(cid, 0) >= count:
                self.known_deck[cid] -= count
                if self.known_deck[cid] <= 0:
                    self.known_deck.pop(cid, None)
            else:
                # A card appeared that cannot be explained from known deck; the
                # previous exact deck view is no longer reliable.
                self.known_deck = None
                self.known_prized = None
                return

    def _update_prize_taken(self, player) -> None:
        current_prize_count = len(getattr(player, "prize", []) or [])
        hand_counts = self.zones.hand.copy()
        if self.last_prize_count is None:
            self.last_prize_count = current_prize_count
            self.last_hand_counts = hand_counts
            return
        if current_prize_count < self.last_prize_count and self.known_prized is not None:
            taken = self.last_prize_count - current_prize_count
            gained = hand_counts - self.last_hand_counts
            gained_total = sum(gained.values())
            if gained_total == taken:
                for cid, count in gained.items():
                    if self.known_prized.get(cid, 0) < count:
                        self.known_prized = None
                        break
                    self.known_prized[cid] -= count
                    if self.known_prized[cid] <= 0:
                        self.known_prized.pop(cid, None)
            else:
                self.known_prized = None
        self.last_prize_count = current_prize_count
        self.last_hand_counts = hand_counts

    def update(self, obs, obs_dict=None):
        if getattr(obs, "current", None) is None:
            return
        yi = obs.current.yourIndex
        player = obs.current.players[yi]
        prev_visible = self.zones.visible.copy()
        self.zones = self._build_zone_snapshot(obs, player, yi)
        self.last_visible = prev_visible
        self._sync_known_deck_after_visible_change()
        self._update_prize_taken(player)

        if getattr(obs, "select", None) is None or getattr(obs.select, "deck", None) is None:
            self.last_visible = self.zones.visible.copy()
            return
        if len(obs.select.deck) != getattr(player, "deckCount", -1):
            self.last_visible = self.zones.visible.copy()
            return
        deck_counts = Counter(card.id for card in obs.select.deck if card is not None)
        self.known_deck = deck_counts
        self.known_prized = self._infer_prized_from_full_search(obs, player, yi, deck_counts)
        self.last_visible = self.zones.visible.copy()

    def deck_count(self, card_id: int) -> int | None:
        if self.known_deck is None:
            return None
        return self.known_deck.get(card_id, 0)

    def deck_has(self, card_id: int) -> bool | None:
        count = self.deck_count(card_id)
        if count is None:
            return None
        return count > 0

    def is_prized(self, card_id: int) -> bool | None:
        if self.known_prized is None:
            return None
        return self.known_prized.get(card_id, 0) > 0

    def prized_cards(self) -> Counter[int] | None:
        return None if self.known_prized is None else self.known_prized.copy()

    def zone_count(self, zone: str, card_id: int) -> int | None:
        counter = getattr(self.zones, zone, None)
        if counter is None:
            return None
        return counter.get(card_id, 0)

    def visible_count(self, card_id: int) -> int:
        return self.zones.visible.get(card_id, 0)

    def debug_snapshot(self) -> dict:
        return {
            "known_deck": self.known_deck is not None,
            "known_prized": self.known_prized is not None,
            "known_deck_size": sum(self.known_deck.values()) if self.known_deck is not None else None,
            "known_prized_size": sum(self.known_prized.values()) if self.known_prized is not None else None,
            "visible_size": sum(self.zones.visible.values()),
            "hand_size": sum(self.zones.hand.values()),
            "discard_size": sum(self.zones.discard.values()),
            "attached_size": sum(self.zones.attached.values()),
        }
