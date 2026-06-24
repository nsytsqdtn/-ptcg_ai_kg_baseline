from __future__ import annotations


EMERGENCY_TAGS = {
    "bench_basic",
    "play_dwebble",
    "play_kang",
    "play_poffin",
    "play_hilda",
    "play_ultra_ball",
    "play_petrel",
    "search_basic",
    "select_dwebble",
    "select_kang",
    "bench_dwebble",
    "bench_kang",
    "poffin_target_dwebble",
    "poffin_target_kang",
    "hilda_target_dwebble",
    "hilda_target_kang",
    "ultra_ball_target_dwebble",
    "ultra_ball_target_kang",
}


def filter_emergency_actions(obs, scored, snapshot, plan):
    if getattr(plan, "mode", None) != "survival_setup":
        return scored
    emergency = []
    for item in scored:
        tags = set(item.prior.get("reason_tags", []))
        if tags & EMERGENCY_TAGS:
            emergency.append(item)
    return emergency or scored
