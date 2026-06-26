from __future__ import annotations

from collections import Counter
from typing import Any


class DeckKnowledgeTracker:
    """Confirmed deck/prize knowledge.

    The tracker deliberately does not infer prizes before a full search frame.
    When obs.select.deck is a complete current deck view, known_deck becomes exact.
    known_prized is built by subtracting all visible cards, the complete deck view,
    and the in-flight resolving effect card from the initial decklist. If the count
    does not exactly match remaining prizes, prize knowledge becomes unknown.
    """

    def __init__(self, decklist: list[int]):
        self.full_deck = Counter(decklist)
        self.known_deck: Counter[int] | None = None
        self.known_prized: Counter[int] | None = None
        self.last_prize_count: int | None = None
        self.last_hand_counts: Counter[int] = Counter()

    def reset(self) -> None:
        self.known_deck = None
        self.known_prized = None
        self.last_prize_count = None
        self.last_hand_counts = Counter()

    def _hand_counts(self, player) -> Counter[int]:
        return Counter(card.id for card in (getattr(player, "hand", []) or []) if card is not None)

    def _sub_pokemon_public(self, visible: Counter[int], pokemon: Any) -> None:
        if pokemon is None:
            return
        visible[pokemon.id] += 1
        for zone_name in ("preEvolution", "energyCards", "energies", "tools"):
            for card in getattr(pokemon, zone_name, None) or []:
                if card is None:
                    continue
                cid = getattr(card, "id", card if isinstance(card, int) else None)
                if cid is not None:
                    visible[cid] += 1

    def _infer_prized_from_full_search(self, obs, player, player_index: int) -> Counter[int] | None:
        visible: Counter[int] = Counter()
        for card in getattr(obs.select, "deck", None) or []:
            if card is not None:
                visible[card.id] += 1
        for card in getattr(player, "hand", []) or []:
            if card is not None:
                visible[card.id] += 1
        for pokemon in list(getattr(player, "active", []) or []) + list(getattr(player, "bench", []) or []):
            self._sub_pokemon_public(visible, pokemon)
        for card in getattr(player, "discard", []) or []:
            if card is not None:
                visible[card.id] += 1
        for card in getattr(obs.current, "stadium", []) or []:
            if card is not None and getattr(card, "playerIndex", player_index) == player_index:
                visible[card.id] += 1
        effect = getattr(obs.select, "effect", None)
        if effect is not None and getattr(effect, "playerIndex", player_index) == player_index:
            visible[getattr(effect, "id", -1)] += 1

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

    def _update_prize_taken(self, player) -> None:
        current_prize_count = len(getattr(player, "prize", []) or [])
        hand_counts = self._hand_counts(player)
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
        self._update_prize_taken(player)
        if getattr(obs, "select", None) is None or getattr(obs.select, "deck", None) is None:
            return
        if len(obs.select.deck) != getattr(player, "deckCount", -1):
            return
        self.known_deck = Counter(card.id for card in obs.select.deck if card is not None)
        self.known_prized = self._infer_prized_from_full_search(obs, player, yi)

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
