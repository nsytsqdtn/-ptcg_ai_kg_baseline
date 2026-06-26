# crustle_mega_kangaskhan_rule_compact_v3

这是一个重新整理后的规则 agent 分支。它保留本地 `battle_env` 接口，但不再沿用旧的 `WallPlan` 主导逻辑，也不再把“岩殿居蟹墙在线”当成胜利路线。

## 决策栈

```text
agent()
→ DeckKnowledgeTracker.update()        # 区域知识：手牌/弃牌/场上/附着/已知牌库/已知奖赏
→ CompactState.from_obs()              # 公开局面 + 我方战斗视图
→ classify_actions()                   # 轻标签动作分类
→ OpponentThreatPlan                   # 对手主动 + 备战区威胁，不只看主动位
→ SetupPlan                            # 保场 / 石居蟹 / 岩殿居蟹 / 能量准备
→ PrizePlan                            # 同回合确认拿奖 + 弱 pressure hint
→ TempoPlan                            # 防守买到的一回合应该换成什么收益
→ choose_plan()                        # 选择唯一主计划
→ score_actions() / choose_context()   # 按主计划选择动作或搜索目标
```

## 关键变化

1. 删除旧的 `wall_plan.py`，不再用 `wall_status` 作为主决策入口。
2. 新增 `threat_plan.py`，同时评估对手主动和备战区攻击手。
3. 新增 `tempo_plan.py`，把“岩殿居蟹挡住 ex 攻击”解释为一回合 tempo，而不是最终目标。
4. `battle_model.py` 增加我方和常见对手关键宝可梦的招式、费用、撤退信息。
5. `deck_knowledge.py` 维护区域知识和完整检索后的牌库/奖赏信息。
6. `ALGORITHM_STEP_BY_STEP.md` 写明每次 agent 调用的完整代码逻辑。
7. `ACCEPTANCE_REPORT.md` 写明本次验收项、通过项和不能在当前容器完成的本地 battle_env 评测项。

## 本地评测

```bash
python evaluate.py --agent crustle_mega_kangaskhan_rule_compact_v3 --games 50 --label compact_v3
```

默认评测 5 个对手：

```text
mega_lucario_beginner
 dragapult_rule_based
 alakazam_rule_based
 crustle_aware_fighting_agent
 multiply_agent_best_940
```

指定对手：

```bash
python evaluate.py --agent crustle_mega_kangaskhan_rule_compact_v3 --games 50 --opponents mega_lucario_beginner,dragapult_rule_based
```

开启 debug：

```bash
RULE_DEBUG=1 RULE_DEBUG_PATH=compact_v3_debug.jsonl python evaluate.py --agent crustle_mega_kangaskhan_rule_compact_v3 --games 50 --label compact_v3_debug
```
