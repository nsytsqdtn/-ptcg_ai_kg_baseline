from __future__ import annotations


def choose_plan(state, setup, tempo, prize) -> str:
    """Select exactly one top-level plan.

    v3 does not select by wall_status. It selects by a threat/tempo/payoff
    contract:
      1. confirmed win
      2. no-active prevention
      3. urgent defensive tempo
      4. confirmed prize
      5. board setup
      6. tempo payoff
      7. pressure/stabilize
    """
    if prize.available and prize.wins_game and prize.confidence == "confirmed":
        return "win_prize"

    if setup.need_backup:
        return "setup"

    if tempo.available and tempo.urgency == "emergency":
        return f"tempo_{tempo.payoff}"

    if prize.available and prize.confidence == "confirmed" and not prize.breaks_defense:
        return "prize"

    if setup.need_dwebble or setup.need_crustle or setup.need_crustle_active:
        return "setup"

    if tempo.available:
        return f"tempo_{tempo.payoff}"

    if prize.available and prize.confidence == "confirmed":
        return "prize"

    if prize.pressure_available:
        return "pressure"

    return "stabilize"
