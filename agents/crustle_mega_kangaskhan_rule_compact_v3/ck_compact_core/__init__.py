"""Compact v3 rule agent core.

The decision stack is ZoneTracker -> BattleState -> OpponentThreatPlan ->
SetupPlan / PrizePlan -> TempoPlan -> plan-scored action selection.
"""
