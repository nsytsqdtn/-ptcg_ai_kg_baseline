from __future__ import annotations

from cg.api import OptionType

from runtime import CardIds, get_selected_card


def _required_basic_ids(plan) -> set[int]:
    ids = set(getattr(plan, "required_basic_ids", set()) or set())
    if ids:
        return ids
    if getattr(plan, "mode", None) == "survival_setup":
        return {CardIds.DWEBBLE, CardIds.MEGA_KANGASKHAN_EX}
    return set()


def _poffin_targets(plan) -> list[int]:
    ids = list(getattr(plan, "poffin_basic_ids", []) or [])
    return ids or [CardIds.DWEBBLE, CardIds.MEGA_KANGASKHAN_EX]


def _search_targets(plan) -> list[int]:
    ids = list(getattr(plan, "search_target_ids", []) or [])
    return ids or [CardIds.DWEBBLE, CardIds.MEGA_KANGASKHAN_EX, CardIds.CRUSTLE]


def _petrel_targets(plan) -> list[int]:
    ids = list(getattr(plan, "petrel_target_ids", []) or [])
    return ids or [CardIds.BUDDY_BUDDY_POFFIN, CardIds.HILDA, CardIds.ULTRA_BALL, CardIds.SWITCH]


def _deck_has_live(deck_knowledge, card_id: int) -> bool:
    if deck_knowledge is None:
        return True
    return deck_knowledge.deck_has(card_id) is not False


def _safe_discard_available(obs) -> bool:
    hand = getattr(obs.current.players[obs.current.yourIndex], "hand", []) or []
    return len(hand) >= 3


def is_emergency_action(obs, item, snapshot, plan, deck_knowledge=None) -> bool:
    option = obs.select.option[item.index]
    if option.type == OptionType.PLAY:
        card = get_selected_card(obs, option)
        if card is None:
            return False
        if getattr(card, "id", None) in _required_basic_ids(plan):
            return True
        if getattr(card, "id", None) == CardIds.BUDDY_BUDDY_POFFIN:
            return any(_deck_has_live(deck_knowledge, cid) for cid in _poffin_targets(plan))
        if getattr(card, "id", None) == CardIds.HILDA:
            return (
                not getattr(obs.current, "supporterPlayed", False)
                and any(_deck_has_live(deck_knowledge, cid) for cid in _search_targets(plan))
            )
        if getattr(card, "id", None) == CardIds.ULTRA_BALL:
            return _safe_discard_available(obs) and any(
                _deck_has_live(deck_knowledge, cid) for cid in _search_targets(plan)
            )
        if getattr(card, "id", None) == CardIds.PETREL:
            return (
                not getattr(obs.current, "supporterPlayed", False)
                and any(_deck_has_live(deck_knowledge, cid) for cid in _petrel_targets(plan))
            )
    if option.type == OptionType.CARD:
        card = get_selected_card(obs, option)
        return card is not None and getattr(card, "id", None) in _required_basic_ids(plan)
    return False


def filter_emergency_actions(obs, scored, snapshot, plan, deck_knowledge=None):
    if getattr(plan, "mode", None) != "survival_setup":
        return scored
    emergency = [item for item in scored if is_emergency_action(obs, item, snapshot, plan, deck_knowledge=deck_knowledge)]
    return emergency or scored
