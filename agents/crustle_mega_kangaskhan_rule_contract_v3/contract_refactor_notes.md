# Crustle / Mega Kangaskhan contract_v3 fixed

This version keeps the original uploaded deck/cg/model files, but replaces the live agent implementation with the cleaned contract-first rule line.

Key changes:
- Helper modules are isolated under `ck_contract_core/` to prevent cross-agent bare-import cache pollution.
- `main.py` uses `BoardSnapshot -> Obligations -> TurnPlan -> ActionClassifier -> DecisionContract -> FinishSearch -> score allowed actions only -> ContextChooser`.
- Search routes use explicit `CONFIRMED / POSSIBLE / DEAD` states. Unknown is no longer treated as confirmed; setup may use possible routes, finish/prize routes require confirmed routes.
- Pokegear is supported as a possible supporter probe and is never used as a verified finish route.
- Old `close_pressure`, `primary_plan`, `wall_and_tax`, `setup_kangaskhan`, `disruption_loop`, and `tank_and_heal` live semantics are removed from the main path.
- The live scorer no longer calls the old `rule_prior.score_option`; scoring is objective/tag based.
- Midgame objectives include `wall_control`, `resource_lock`, and `pressure_prize` so Crustle wall turns can actively disrupt and pressure instead of only preserving the wall.
- `evaluate.py` defaults to the current folder name and supports `--agent`.
