# compact_v3 算法逐步说明

本文按代码实际调用顺序说明 `crustle_mega_kangaskhan_rule_compact_v3` 的每次决策过程。卡牌名称在说明中使用中文名；代码内部仍使用英文名和卡牌 ID。

---

## 0. 重要前提：agent 不是一次规划完整回合

模拟器在一个回合里会多次调用 `agent()`。例如：

```text
主阶段选择动作
→ 打出友好松饼
→ 模拟器进入选宝可梦阶段，再调用 agent
→ 选择石居蟹
→ 回到主阶段，再调用 agent
→ 打斗子
→ 进入选牌阶段，再调用 agent
→ 选择岩殿居蟹 + 能量
→ 回到主阶段，再调用 agent
→ 攻击或结束
```

所以每次 `agent()` 做的是“当前选择窗口的最优动作”，不是一次性输出整回合脚本。

---

## 1. 入口：`main.py::agent()`

每次环境调用：

```python
agent(obs_dict, configuration=None)
```

如果 `obs_dict["select"] is None`，表示环境正在询问 deck，agent 会：

```text
1. 重置 DeckKnowledgeTracker。
2. 返回 deck.csv 的 60 张卡牌 ID。
```

正常对局选择时，主流程是：

```text
1. to_observation_class(obs_dict)
2. deck_knowledge.update(obs)
3. state = CompactState.from_obs(obs, deck_knowledge)
4. actions = classify_actions(obs, state)
5. setup_plan = build_setup_plan(state)
6. prize_plan = build_prize_plan(state, actions)
7. tempo_plan = build_tempo_plan(state, setup_plan, prize_plan)
8. selected_plan = choose_plan(state, setup_plan, tempo_plan, prize_plan)
9. scored = score_actions(actions, state, selected_plan, setup_plan, tempo_plan, prize_plan)
10. 如果是 SELECT 阶段：choose_context_action(...)
11. 如果是 MAIN 阶段：choose_best(scored, state)
12. _normalize_selection(...)
13. write_debug(...)
14. 返回合法 option index
```

如果发生异常，且没有设置 `RULE_RAISE=1`，会 fallback 到安全动作。`fallback_count=0` 只说明没有异常，不代表策略正确。

---

## 2. 区域知识：`DeckKnowledgeTracker.update()`

模块：`ck_compact_core/deck_knowledge.py`

v3 维护区域知识，而不是只记一次牌库搜索结果。它记录：

```text
hand      手牌
 discard   弃牌区
 active    前排宝可梦
 bench     备战区宝可梦
 attached  进化前、能量、道具等附着牌
 stadium   我方场地
 visible   所有可见我方牌
 known_deck    完整检索后确认的牌库内容
 known_prized  如果可推出，则确认的奖赏卡内容
```

### 2.1 每次调用先重建可见区

`update()` 每次都从 observation 直接重建：

```text
手牌、弃牌区、前排、备战区、附着牌、场地
```

这些公开信息以当前 observation 为准，不靠记忆猜。

### 2.2 如果之前知道牌库，则用可见区变化同步

如果之前 `known_deck` 存在，而某张牌新出现在可见区，tracker 会尝试从 `known_deck` 扣掉这张牌。

如果出现无法解释的变化，比如某张新可见牌不在已知牌库中，则认为旧牌库知识失效：

```text
known_deck = None
known_prized = None
```

这是为了防止错误状态持续污染后续判断。

### 2.3 完整检索牌库时更新 `known_deck`

当当前选择窗口提供 `obs.select.deck`，且其长度等于当前牌库数量时，认为这是完整牌库视图。

此时：

```text
known_deck = 当前 obs.select.deck 的计数
```

然后尝试推断奖赏区：

```text
known_prized = 初始 60 张
               - visible 可见区
               - known_deck 已知牌库
               - 当前正在结算的效果牌
```

如果结果数量正好等于剩余奖赏卡数量，就接受；否则不猜，`known_prized = None`。

### 2.4 拿奖赏时更新

如果奖赏数量减少，tracker 用手牌差分尝试判断拿到什么。

```text
如果手牌新增数量 == 奖赏减少数量：
    从 known_prized 中扣除这些牌。
否则：
    known_prized 失效。
```

所以 v3 不是无条件声称“知道奖赏是什么”，而是在 observation 支持时更新，在不确定时失效。

---

## 3. 战斗视图：`CompactState.from_obs()`

模块：`ck_compact_core/state.py`

`CompactState` 把复杂 observation 压成一个统一局面对象。

### 3.1 我方局面

它读取：

```text
我方主动宝可梦
我方备战区
我方手牌
我方弃牌区
我方奖赏数量
我方牌库数量
```

并统计：

```text
field_count
bench_space
hand_counts
discard_counts
field_counts
safe_draws = my_deck_count - my_prizes_left - 1
deck_danger = safe_draws <= 0
```

### 3.2 核心宝可梦状态

核心宝可梦是：

```text
石居蟹
岩殿居蟹
超级袋兽ex
```

状态字段包括：

```text
has_dwebble / has_crustle / has_kang
dwebble_active / crustle_active / kang_active
```

### 3.3 `PokemonView`

每只公开宝可梦会变成 `PokemonView`：

```text
卡牌 ID
中文名
当前 HP / 最大 HP / 已受伤害
已有能量数量
已有能量 ID 列表
草能量数量
撤退费用
当前是否能撤退
是否 ex
被击倒给几张奖赏
攻击列表
当前可用攻击列表
当前最佳主动伤害
当前最佳备战区伤害
是否附有薄雾能量
```

这一步已经不再只看“能量数量”，而是结合 `battle_model.py` 的招式资料判断攻击是否可用。

---

## 4. 公开战斗模型：`battle_model.py`

这个模块保存公开卡面事实，不是 matchup 分支。它记录常见卡的：

```text
招式名称
伤害
费用
撤退费用
是否有备战区伤害指示物
是否是效果伤害
特殊说明
```

已建模的关键牌包括：

```text
我方：石居蟹、岩殿居蟹、超级袋兽ex
多龙系：多龙梅西亚、多龙奇、多龙巴鲁托ex
路卡利欧系：利欧路、超级路卡利欧ex、幕下力士、超力王
格斗组件：月石、太阳岩
胡地系：凯西、勇基拉、胡地
水系/乘算类估计：盖欧卡、雪笠怪、超级暴雪王ex
```

如果遇到没有 profile 的公开对手宝可梦，代码会使用 generic estimate。generic 只是保底，不是完整卡面理解。

---

## 5. 对手威胁计划：`OpponentThreatPlan`

模块：`ck_compact_core/threat_plan.py`

这是 v3 的核心变化。它不再只看对手主动位，而是同时看：

```text
对手主动宝可梦
对手备战区宝可梦
当前可用攻击
差一颗能量的攻击
备战攻击手的未来路线
备战区伤害
非 ex 破墙攻击手
老大的指令类隐藏抓人风险
```

### 5.1 为每个对手宝可梦生成 `ThreatCandidate`

每个候选记录：

```text
来源：active / bench:N
宝可梦中文名
攻击名
timing：now / next_turn / future
confidence：confirmed / likely / possible
打主动的原始伤害
打主动的实际伤害
备战区伤害
缺几颗能量
能否击倒主动
能否本回合击倒备战核心
能否两回合内击倒备战核心
是否被岩殿居蟹阻挡
绕墙原因
severity 威胁分
```

### 5.2 岩殿居蟹只阻挡“ex 对主动造成的攻击伤害”

如果对方主动是 ex，当前攻击要打主动岩殿居蟹，那么主动伤害会被视为 0。

但是以下情况不算被完全挡住：

```text
备战区放伤害指示物
非 ex 攻击手
攻击效果
抓备战区
备战区攻击手下回合上来
```

### 5.3 多龙巴鲁托ex的备战区伤害不再只看 immediate KO

旧逻辑只看 60 点备战区伤害是否立刻击倒核心。v3 还记录：

```text
两回合内是否会击倒备战核心
是否形成 bench_damage_pressure
two_turn_bench_pressure
```

所以“这回合没有马上 KO”不再等于“岩殿居蟹买到了安全回合”。

### 5.4 隐藏老大风险

对方手牌内容不可见，但如果：

```text
对手手牌 >= 4
我方备战区有高奖赏或低血核心
```

则记录：

```text
gust_prize_pressure = True
```

这是风险估计，不是确认对方手里有老大的指令。

### 5.5 输出总威胁计划

最终 `OpponentThreatPlan` 输出：

```text
main 最高威胁候选
immediate_prize_threat
next_turn_prize_threat
bench_damage_pressure
two_turn_bench_pressure
gust_prize_pressure
non_ex_wall_breaker_ready
active_damage_blocked_by_crustle
defense_buys_tempo
recommended_defense
reasons
summary
```

---

## 6. SetupPlan：建设与防 no-active

模块：`setup_plan.py`

`SetupPlan` 负责：

```text
补后备
找石居蟹
找岩殿居蟹
让岩殿居蟹站主动
准备岩殿居蟹能量
判断石居蟹升阶是否安全
```

核心逻辑：

```text
如果场上只有 1 只：need_backup
如果前 3 回合场上少于 2 只：need_backup
如果对手有立即击倒主动风险，场上不超过 2 只，且当前不是岩殿居蟹已经挡住该伤害：need_backup
```

石居蟹升阶只在以下条件允许：

```text
主动是石居蟹
场上至少 2 只宝可梦
牌库不危险
```

---

## 7. PrizePlan：确认拿奖与压力线

模块：`prize_plan.py`

`PrizePlan` 只负责同回合或当前合法动作链可确认的拿奖路线。

### 7.1 攻击手

候选攻击手：

```text
岩殿居蟹：稳定按 120
超级袋兽ex：稳定按 200，不计算硬币额外收益
```

主动位差一颗能量时，如果当前合法动作里能贴对应能量，则生成 confirmed attach -> attack 路线。

备战攻击手如果需要换位，必须当前合法动作里有换位/撤退，才是 confirmed；否则只是 possible。

### 7.2 目标

目标包括：

```text
对手主动位
老大的指令可拉的备战目标
露琪亚的魅力展示可拉的基础宝可梦
```

Boss/Lisia 必须在当前 legal_actions 中存在，才是 confirmed。

火箭队的兰斯达找老大/露琪亚只能作为 future possible，不能同回合 confirmed，因为它和老大/露琪亚同为支援者。

### 7.3 pressure hint

如果没有明确 KO，但攻击能造成较大比例伤害，则记录 `pressure_available`。这不会直接抢主计划，只能供 TempoPlan 在没有更高优先级时使用。

---

## 8. TempoPlan：防守拖延后换成什么收益

模块：`tempo_plan.py`

这是 v3 的第二个核心变化。它不再问“墙在线吗”，而是问：

```text
对手威胁是什么？
防守是否买到一回合 tempo？
如果买到 tempo，这回合应该把 tempo 换成什么收益？
```

### 8.1 emergency 情况

如果对手有立即 prize threat：

```text
需要补后备 -> payoff = setup
主动快死 -> payoff = heal
备战核心被威胁 -> payoff = protect_bench
否则 -> payoff = disrupt_energy
```

### 8.2 备战区压力

如果存在两回合备战区奖赏压力：

```text
payoff = protect_bench
```

优先牌：

```text
薄雾能量
特大冰淇淋
枇琶
手牌修剪器
```

### 8.3 抓人压力

如果对方有隐藏抓人风险：

```text
payoff = disrupt_hand
```

优先牌：

```text
枇琶
手牌修剪器
克希洛希奇的图谋
```

### 8.4 非 ex 破墙攻击手

如果对方有非 ex 攻击手可以破岩殿居蟹：

```text
有 confirmed prize -> payoff = prize
否则 -> payoff = disrupt_energy
```

### 8.5 岩殿居蟹真的买到 tempo

只有当：

```text
岩殿居蟹挡住对手主动 ex 的主动伤害
并且没有严重备战区两回合压力
并且没有立即 prize threat
并且没有非 ex 破墙攻击手 ready
```

才认为：

```text
defense_buys_tempo = True
```

这时 payoff 不是“继续 wall”，而是按优先级选择：

```text
confirmed prize -> prize
还没建好场 -> setup
超级袋兽ex没成型 -> build_attacker
有 pressure hint -> pressure
否则 -> disrupt_hand
```

---

## 9. 计划选择：`choose_plan()`

模块：`plan_select.py`

v3 不按 `wall_status` 选计划。顺序是：

```text
1. confirmed win -> win_prize
2. need_backup -> setup
3. emergency tempo -> tempo_xxx
4. confirmed prize 且不破坏防守 -> prize
5. setup 未完成 -> setup
6. tempo payoff -> tempo_xxx
7. confirmed prize -> prize
8. pressure hint -> pressure
9. stabilize
```

所以主计划是：

```text
win_prize
setup
prize
tempo_setup
tempo_protect_bench
tempo_disrupt_energy
tempo_disrupt_hand
tempo_heal
tempo_build_attacker
tempo_pressure
pressure
stabilize
```

---

## 10. 动作评分：`score_actions()`

模块：`score.py`

每个动作分数由：

```text
safety_score
+ selected plan score
+ secondary setup/prize/tempo score
+ small_general_score
```

### 10.1 safety_score

安全层会惩罚：

```text
牌库危险还抽牌
场上只有 1 只还攻击
场上只有 1 只还结束
对手有立即 prize threat 还空过
石居蟹无后备升阶
浪费已经挡住的岩殿居蟹主动位
低 safe_draws 抽牌
```

### 10.2 setup 分

高分动作包括：

```text
下石居蟹
友好松饼
高级球
斗子
火箭队的兰斯达
进化岩殿居蟹
安全的石居蟹升阶
给石居蟹/岩殿居蟹准备草能量或薄雾能量
```

### 10.3 prize 分

高分动作包括：

```text
攻击拿奖
贴能量完成攻击
老大的指令
露琪亚的魅力展示
换位到计划攻击手
```

### 10.4 tempo 分

按 `tempo.payoff` 不同：

```text
heal：特大冰淇淋 / 白露的真心 / 英雄斗篷
protect_bench：薄雾能量贴核心 / 特大冰淇淋 / 枇琶 / 手牌修剪器
disrupt_energy：克希洛希奇的图谋 / 手持循环扇 / 抓人拖能量目标
disrupt_hand：枇琶 / 手牌修剪器 / 克希洛希奇的图谋
build_attacker：给超级袋兽ex或岩殿居蟹贴能量 / 斗子
pressure：攻击或贴能量形成两回合 KO
stabilize：火箭队的兰斯达 / 宝可装置3.0 / 尖刺能量 / 安全抽牌
```

---

## 11. 选择阶段：`context.py`

选择阶段不直接用主阶段动作分，而是按当前效果牌和主计划选目标。

### 11.1 开局主动/备战

优先：

```text
石居蟹
超级袋兽ex
```

### 11.2 友好松饼

优先：

```text
石居蟹
如果需要补场，再选其他合法基础
```

### 11.3 斗子

优先：

```text
岩殿居蟹
成长【草】能量
基本【草】能量
薄雾能量
尖刺能量
```

如果 TempoPlan 是保护备战核心，薄雾能量优先级会明显提高。

### 11.4 火箭队的兰斯达

根据主计划选择：

```text
setup：友好松饼 / 斗子 / 高级球 / 宝可装置3.0
prize：老大的指令 / 露琪亚的魅力展示 / 宝可梦交替
heal：特大冰淇淋 / 白露的真心
protect_bench：特大冰淇淋 / 枇琶 / 手牌修剪器
disrupt_energy：克希洛希奇的图谋 / 手持循环扇 / 老大的指令
disrupt_hand：枇琶 / 手牌修剪器 / 克希洛希奇的图谋
```

### 11.5 高级球弃牌

保护：

```text
石居蟹
岩殿居蟹
超级袋兽ex
火箭队的兰斯达
斗子
老大的指令
露琪亚的魅力展示
薄雾能量
成长【草】能量
基本【草】能量
```

倾向弃：

```text
多余场地
牌库危险时的莉莉艾的决心
多余尖刺能量
```

### 11.6 老大/露琪亚目标

优先：

```text
PrizePlan 指定目标
当前攻击能击倒的最高奖赏目标
低 HP 目标
```

---

## 12. debug 输出

开启：

```bash
RULE_DEBUG=1 RULE_DEBUG_PATH=compact_v3_debug.jsonl
```

每次调用输出：

```text
当前阶段
当前主计划
我方场面
ZoneKnowledge 是否知道牌库/奖赏
OpponentThreatPlan 完整候选
SetupPlan
TempoPlan
PrizePlan
top actions
最终选择
```

这份 debug 的重点不是只看 selected action，而是看：

```text
对手威胁有没有识别对？
TempoPlan 的 payoff 是否合理？
PrizePlan 是否错过确认拿奖？
Context 是否选到了计划组件？
```

---

## 13. v3 与 v2 的本质区别

v2：

```text
岩殿居蟹状态 / WallPlan 仍然主导。
OpponentThreatPlan 主要看对手主动。
Tempo 字段更多用于 debug。
```

v3：

```text
没有 wall_plan.py。
没有 wall_status 主入口。
OpponentThreatPlan 同时看对手主动和备战区。
TempoPlan 是独立计划对象。
防守只负责买 tempo；买到的 tempo 必须转换成 setup / prize / protect / disrupt / heal / pressure。
```

---

## 14. 仍然明确的边界

v3 是规则 agent，不是完整游戏树搜索，也不是强化学习 agent。它不会完美预测隐藏手牌，也不会精确模拟所有未知对手牌文本。它的完整性目标是：

```text
不再套壳旧 WallPlan；
不再只看墙在线；
不再只看对手主动位；
把公开威胁、防守 tempo、收益计划、动作选择串成闭环。
```
