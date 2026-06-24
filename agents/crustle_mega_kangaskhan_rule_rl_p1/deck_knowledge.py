from __future__ import annotations

from collections import Counter


class DeckKnowledgeTracker:
    def __init__(self, decklist: list[int]):
        self.full_deck = Counter(decklist)
        self.known_deck: Counter[int] | None = None
        self.known_prized: Counter[int] | None = None
        self.last_prize_count: int | None = None
        self.last_hand_by_serial: dict[tuple[int, str], int] = {}

    def _hand_by_serial(self, player) -> dict[tuple[int, str], int]:
        hand = {}
        for index, card in enumerate(getattr(player, "hand", []) or []):
            if card is None:
                continue
            hand[(getattr(card, "id", -1), getattr(card, "name", ""))] = index
        return hand

    def _infer_prized_from_full_search(self, obs, player, player_index: int) -> Counter[int] | None:
        visible = Counter()
        for zone_card in list(getattr(player, "hand", []) or []):
            if zone_card is not None:
                visible[zone_card.id] += 1
        for zone_card in list(getattr(player, "active", []) or []) + list(getattr(player, "bench", []) or []) + list(getattr(player, "discard", []) or []):
            if zone_card is not None:
                visible[zone_card.id] += 1
        for zone_card in list(getattr(obs.select, "deck", []) or []):
            if zone_card is not None:
                visible[zone_card.id] += 1
        effect = getattr(obs.select, "effect", None)
        if effect is not None:
            visible[getattr(effect, "id", -1)] += 1

        remaining = self.full_deck.copy()
        for card_id, count in visible.items():
            remaining[card_id] -= count
            if remaining[card_id] <= 0:
                remaining.pop(card_id, None)
        prize_total = len(getattr(player, "prize", []) or [])
        if sum(remaining.values()) != prize_total:
            return None
        return remaining

    def update(self, obs, obs_dict=None):
        yi = obs.current.yourIndex
        player = obs.current.players[yi]
        self.last_prize_count = len(getattr(player, "prize", []) or [])
        self.last_hand_by_serial = self._hand_by_serial(player)

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
