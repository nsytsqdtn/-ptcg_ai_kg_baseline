# Crustle / Mega Kangaskhan ex Compact Rule v1

This agent is a clean compact branch. It does not reuse the old contract/turn-plan/scorer stack.

Core decision flow:

1. Build `CompactState`.
2. Build `SetupPlan`, `WallPlan`, and `PrizePlan`.
3. Choose exactly one selected plan.
4. Score legal actions only against that selected plan plus a small safety layer.
5. Resolve selection contexts with compact target selectors.

Code uses English card names and English plan logic. Chinese names are provided only in debug output for visualization.

Debug:

```bash
RULE_DEBUG=1 RULE_DEBUG_PATH=compact_debug.jsonl python evaluate.py --agent crustle_mega_kangaskhan_rule_compact_v1 --games 50 --label compact_v1
```

## compact_v1_1 update

This package keeps the compact three-plan structure and does not restore the old contract/turn-plan stack.

Changes from compact_v1:

- Added `get_deck()` and `agent(observation, configuration=None)` compatibility.
- Added lightweight `active_under_threat` and `active_threat_damage_estimate` to `CompactState`.
- `SetupPlan` now asks for backup when the Active is likely to be KO'd and the field has only two Pokémon, without returning to the old T1-T5 over-protection rule.
- `WallPlan` now reports `leak_reasons` and a conservative `broken` status for leaky/threatened wall states.
- `PrizePlan` now handles active attackers that are one legal attachment away from a KO.
- Petrel-to-Boss/Lisia is no longer treated as a confirmed same-turn prize route because Petrel is a Supporter.
- Wall scoring can use non-KO pressure hints when otherwise waiting, but pressure hints cannot hijack setup or a stable wall.
