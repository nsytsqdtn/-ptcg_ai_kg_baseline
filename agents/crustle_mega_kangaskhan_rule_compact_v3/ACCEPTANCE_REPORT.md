# compact_v3 验收报告

## 结构验收

已完成：

```text
[通过] main.py 保留 battle_env agent(obs, configuration=None) 接口。
[通过] get_deck() 返回 60 张 deck.csv 卡牌。
[通过] 删除旧 wall_plan.py。
[通过] main.py 不再 import build_wall_plan。
[通过] plan_select.py 不再用 wall_status 选择主计划。
[通过] 新增 threat_plan.py，OpponentThreatPlan 同时评估对手主动和备战区。
[通过] 新增 tempo_plan.py，TempoPlan 独立决定 payoff。
[通过] score.py 改为按 setup / prize / tempo payoff 评分。
[通过] context.py 改为按 selected_plan + TempoPlan + PrizePlan 选择搜索目标。
[通过] debug.py 输出 ZoneKnowledge / OpponentThreatPlan / TempoPlan。
[通过] evaluate.py 默认支持 5 个对手。
```

## 代码验收

在当前容器内完成：

```text
python -m compileall -q .     通过
import main                   通过
len(main.get_deck()) == 60    通过
battle_model profiles loaded  通过
无 __pycache__ / .pyc 打包    通过
```

## 当前容器不能完成的验收

当前容器没有本地 `battle_env`，所以不能在这里跑 5 个对手各 50 局。需要你在本地仓库根目录执行：

```bash
python evaluate.py --agent crustle_mega_kangaskhan_rule_compact_v3 --games 50 --label compact_v3
```

如果要保存 debug：

```bash
RULE_DEBUG=1 RULE_DEBUG_PATH=compact_v3_debug.jsonl python evaluate.py --agent crustle_mega_kangaskhan_rule_compact_v3 --games 50 --label compact_v3_debug
```

## 不再保留的旧式降级逻辑

```text
没有 wall_plan.py。
没有 WallPlan 数据结构。
没有 build_wall_plan()。
没有 wall_status 主决策。
没有“岩殿居蟹在线 -> 进入 wall plan”的主路线。
```

## v3 的验收标准

本版本验收不是承诺固定胜率，而是验收算法是否形成完整闭环：

```text
区域知识 -> 战斗视图 -> 对手威胁 -> 我方 setup/prize -> tempo payoff -> 动作/目标选择
```

如果本地评测仍低，下一步应根据 debug 判断：

```text
是 threat profile 缺卡？
是 tempo payoff 选错？
是 PrizePlan 漏拿奖？
是 Context 选错搜索目标？
```

而不是再回到旧的 WallPlan/contract 套壳。
