from __future__ import annotations


def choose_plan(state, setup, wall, prize) -> str:
    # Direct confirmed win always takes priority.
    if prize.wins_game and prize.confidence == "confirmed":
        return "prize"

    # Avoid no-active first. After that, confirmed direct prizes are allowed
    # even before the wall is fully built; this prevents the compact agent from
    # ignoring obvious low-risk KOs while in setup mode.
    if setup.need_backup:
        return "setup"
    if prize.available and prize.confidence == "confirmed" and prize.route == "direct" and not prize.breaks_wall:
        return "prize"
    if wall.status in {"absent", "building"}:
        return "setup"

    # Once the wall is online, take only confirmed, low-risk prizes that do not
    # break the wall. Otherwise keep the wall plan.
    if wall.status == "online":
        if prize.available and prize.confidence == "confirmed" and not prize.breaks_wall and prize.prize_gain >= 1:
            return "prize"
        return "wall"

    # If wall is leaky, confirmed prizes are allowed; otherwise try to repair or
    # slow the opponent rather than taking speculative lines.
    if wall.status in {"leaky", "broken"}:
        if prize.available and prize.confidence == "confirmed":
            return "prize"
        return "wall"

    if prize.available and prize.confidence == "confirmed":
        return "prize"
    return "setup"
