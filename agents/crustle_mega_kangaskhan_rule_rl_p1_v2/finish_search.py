from __future__ import annotations

from cg.api import OptionType

from runtime import CardIds, get_selected_card, prize_count


def _can_direct_attack_finish(snapshot) -> bool:
    target = getattr(snapshot, "opponent_active", None)
    if target is None:
        return False
    return (
        getattr(snapshot, "can_attack_now", False)
        and getattr(snapshot, "current_attack_damage", 0) >= getattr(target, "hp", 999) > 0
        and prize_count(target) >= getattr(snapshot, "my_prizes_left", 99)
    )


def _estimate_attack_damage(card) -> int:
    if card is None:
        return 0
    cid = getattr(card, "id", None)
    attached = len(getattr(card, "energies", []) or [])
    if cid == CardIds.CRUSTLE:
        return 120 if attached >= 1 else 0
    if cid == CardIds.MEGA_KANGASKHAN_EX:
        return 200 if attached >= 3 else 0
    return 0


def _bench_finish_needs_switch(snapshot, deck_knowledge=None) -> bool:
    hand_ids = {
        getattr(card, "id", None)
        for card in getattr(snapshot, "hand", []) or []
        if card is not None
    }
    gust_live = bool(hand_ids & {CardIds.BOSS_ORDERS, CardIds.LISIA})
    if not gust_live and CardIds.PETREL in hand_ids and deck_knowledge is not None:
        gust_live = (
            deck_knowledge.deck_has(CardIds.BOSS_ORDERS) is True
            or deck_knowledge.deck_has(CardIds.LISIA) is True
        )
    for attacker in getattr(snapshot, "bench", []) or []:
        damage = _estimate_attack_damage(attacker)
        if damage <= 0:
            continue
        active = getattr(snapshot, "opponent_active", None)
        if active is not None and damage >= getattr(active, "hp", 999) > 0 and prize_count(active) >= getattr(snapshot, "my_prizes_left", 99):
            return True
        if not gust_live:
            continue
        for card in getattr(snapshot, "opponent_bench", []) or []:
            if damage >= getattr(card, "hp", 999) > 0 and prize_count(card) >= getattr(snapshot, "my_prizes_left", 99):
                return True
    return False


def try_finish_search(obs, snapshot, plan, deck_knowledge=None):
    if getattr(plan, "mode", None) != "finish":
        return None
    if _can_direct_attack_finish(snapshot):
        for index, option in enumerate(getattr(obs.select, "option", []) or []):
            if option.type == OptionType.ATTACK:
                return [index]
    if _bench_finish_needs_switch(snapshot, deck_knowledge=deck_knowledge):
        for index, option in enumerate(getattr(obs.select, "option", []) or []):
            if option.type == OptionType.PLAY:
                card = get_selected_card(obs, option)
                if getattr(card, "id", None) == CardIds.SWITCH:
                    return [index]
        for index, option in enumerate(getattr(obs.select, "option", []) or []):
            if option.type == OptionType.RETREAT:
                return [index]
    hand_ids = {
        getattr(card, "id", None)
        for card in getattr(snapshot, "hand", []) or []
        if card is not None
    }
    if hand_ids & {CardIds.BOSS_ORDERS, CardIds.LISIA}:
        for index, option in enumerate(getattr(obs.select, "option", []) or []):
            if option.type == OptionType.PLAY:
                card = get_selected_card(obs, option)
                if getattr(card, "id", None) in {CardIds.BOSS_ORDERS, CardIds.LISIA}:
                    return [index]
    if CardIds.PETREL in hand_ids and deck_knowledge is not None:
        can_find_gust = (
            deck_knowledge.deck_has(CardIds.BOSS_ORDERS) is True
            or deck_knowledge.deck_has(CardIds.LISIA) is True
        )
        if can_find_gust:
            for index, option in enumerate(getattr(obs.select, "option", []) or []):
                if option.type == OptionType.PLAY:
                    card = get_selected_card(obs, option)
                    if getattr(card, "id", None) == CardIds.PETREL:
                        return [index]
    return None
