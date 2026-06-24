# PTCG 本地对战环境

这个项目现在的目标是提供一套稳定的本地对战基础环境，统一支持：

- agent 对战
- 系列赛评测
- 结构化记录
- HTML 回放
- 指标汇总
- 后续强化学习数据采样

## 目录约定

所有 agent 都放在 `agents/` 下，一个 agent 一个文件夹：

```text
agents/
  your_agent/
    agent.py
    deck.csv
    manifest.json
```

回放系统统一归档在 `replay_systems/`：

- `replay_systems/notebook_visualizer.py`：当前使用中的 notebook 回放系统
- `replay_systems/legacy_battle_viewer.py`：旧版本地自定义回放系统备份

## 入口

主入口在项目根目录：

```powershell
cd D:\workspace\ptcg
python local_battle.py --agent-a dragapult_rule_based --agent-b mega_lucario_beginner
```

兼容入口 `scripts\local_battle.py` 仍然保留，但只是薄包装。

## 最常用命令

跑 1 局：

```powershell
python local_battle.py --agent-a dragapult_rule_based --agent-b mega_lucario_beginner
```

跑 1 局，并保存完整记录 + 人类日志：

```powershell
python local_battle.py --agent-a dragapult_rule_based --agent-b mega_lucario_beginner --verbose --record-file battle_records\sample_match.json
```

只生成可视化回放页面：

```powershell
python local_battle.py --agent-a dragapult_rule_based --agent-b mega_lucario_beginner --replay-file battle_records\sample_match.replay.html
```

跑多局并交换先后手：

```powershell
python local_battle.py --agent-a dragapult_rule_based --agent-b mega_lucario_beginner --games 20 --swap-sides --record-file battle_records\series_match.json
```

## 日志文件怎么看

执行带 `--verbose` 的命令后，会同时生成两份文本日志：

- `*.summary.log`：给人看的，按回合汇总，先看这个
- `*.detail.log`：逐步骤详细日志，排查问题时再看这个
- `*.replay.html`：通过 notebook 抽出的 replay visualizer 生成的可视化回放页面，最适合人工复盘

如果命令里写了：

```powershell
--record-file battle_records\sample_match.json
```

那默认会得到：

```text
battle_records\sample_match.json
battle_records\sample_match.summary.log
battle_records\sample_match.detail.log
battle_records\sample_match.replay.html
```

程序结束后也会直接打印这些文件路径。

## 三种输出分别是什么

- `*.json`：完整结构化记录，主回放数据在顶层 `steps[]`，适合后续分析、统计、写脚本
- `*.summary.log`：回合摘要，适合看对战流程
- `*.detail.log`：每一步的选择和事件细节，适合调试 agent
- `*.replay.html`：notebook replay visualizer 输出，适合回看局面变化

## 怎么打开回放页面

生成 `*.replay.html` 后，直接双击打开即可。

如果你想在命令行里打开，也可以：

```powershell
start battle_records\sample_match.replay.html
```

## 建议使用顺序

新增 agent 之后，建议按这个顺序测：

1. 先跑 1 局确认能正常结束
2. 先看 `*.replay.html` 复盘局面和动作
3. 再看 `*.summary.log` 快速扫流程
4. 如果行为不对，再看 `*.detail.log`
5. 最后跑多局加 `--swap-sides` 看稳定性
