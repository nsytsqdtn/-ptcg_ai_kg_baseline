from __future__ import annotations

import csv
import json
from dataclasses import fields, is_dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path

from replay_systems.notebook_visualizer import write_replay_html
from cg.api import AreaType, LogType, OptionType, all_attack, all_card_data


ROOT = Path(__file__).resolve().parents[1]
CARD_NAME_BY_ID = {card.cardId: card.name for card in all_card_data()}
ATTACK_NAME_BY_ID = {attack.attackId: attack.name for attack in all_attack()}
CARD_NAME_ZH_CSV_PATH = ROOT / "JP_Card_Data_全中文翻译.csv"
AREA_NAME_ZH = {
    "DECK": "牌库",
    "HAND": "手牌",
    "DISCARD": "弃牌区",
    "ACTIVE": "战斗位",
    "BENCH": "备战区",
    "PRIZE": "奖赏卡",
    "STADIUM": "场地",
    "LOOKING": "查看区",
    "ENERGY": "能量区",
    "TOOL": "道具区",
    "PRE_EVOLUTION": "退化来源区",
}


def load_card_name_zh_map() -> dict[int, str]:
    if not CARD_NAME_ZH_CSV_PATH.exists():
        return {}
    mapping: dict[int, str] = {}
    with CARD_NAME_ZH_CSV_PATH.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            try:
                card_id = int(row["卡牌ID"])
            except Exception:
                continue
            name_zh = (row.get("卡牌名（中文）") or "").strip()
            if name_zh:
                mapping[card_id] = name_zh
    return mapping


CARD_NAME_ZH_BY_ID = load_card_name_zh_map()


def normalize_for_json(value):
    if is_dataclass(value):
        return {field.name: normalize_for_json(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Enum):
        return value.name
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): normalize_for_json(val) for key, val in value.items()}
    if isinstance(value, (list, tuple)):
        return [normalize_for_json(item) for item in value]
    if hasattr(value, "__dict__"):
        return {key: normalize_for_json(val) for key, val in vars(value).items() if not key.startswith("_")}
    return value


def enum_name(enum_cls, value):
    if hasattr(value, "name"):
        return value.name
    try:
        return enum_cls(value).name
    except Exception:
        return str(value)


def card_name(card_id):
    if card_id is None:
        return None
    return CARD_NAME_ZH_BY_ID.get(card_id) or CARD_NAME_BY_ID.get(card_id, f"cardId={card_id}")


def attack_name(attack_id):
    if attack_id is None:
        return None
    return ATTACK_NAME_BY_ID.get(attack_id, f"attackId={attack_id}")


def area_name_zh(area_name: str | None) -> str:
    if not area_name:
        return "未知区域"
    if area_name in AREA_NAME_ZH:
        return AREA_NAME_ZH[area_name]
    if str(area_name).isdigit():
        return f"未知区域({area_name})"
    return str(area_name)


def summarize_logs(logs: list[dict]) -> str:
    if not logs:
        return "no logs"
    log_types = [str(log.get("type_name", log.get("type", "UNKNOWN"))) for log in logs]
    return ", ".join(log_types[:5]) + (" ..." if len(log_types) > 5 else "")


def summarize_selected_options(selected_options: list[dict]) -> str:
    if not selected_options:
        return "无"
    parts = []
    for option in selected_options:
        part = option.get("type_name", "UNKNOWN")
        if option.get("card_name"):
            part += f"({option['card_name']})"
        elif option.get("attack_name"):
            part += f"({option['attack_name']})"
        elif option.get("number") is not None:
            part += f"(number={option['number']})"
        elif option.get("area_name") is not None and option.get("index") is not None:
            part += f"({option['area_name']} #{option['index']})"
        parts.append(part)
    return ", ".join(parts)


def get_area_card_name(observation, area, index, player_index):
    if observation is None or observation.current is None:
        return None
    try:
        players = observation.current.players
        if area == AreaType.HAND:
            card = players[player_index].hand[index]
        elif area == AreaType.DISCARD:
            card = players[player_index].discard[index]
        elif area == AreaType.ACTIVE:
            card = players[player_index].active[index]
        elif area == AreaType.BENCH:
            card = players[player_index].bench[index]
        elif area == AreaType.PRIZE:
            card = players[player_index].prize[index]
        elif area == AreaType.STADIUM:
            card = observation.current.stadium[index]
        elif area == AreaType.LOOKING and observation.current.looking is not None:
            card = observation.current.looking[index]
        elif area == AreaType.DECK and observation.select is not None and observation.select.deck is not None:
            card = observation.select.deck[index]
        else:
            return None
        if card is None:
            return None
        return card_name(getattr(card, "id", None))
    except Exception:
        return None


def describe_option(option, observation=None, player_index=None) -> dict:
    data = normalize_for_json(option)
    option_type = getattr(option, "type", None)
    data["type_name"] = enum_name(OptionType, option_type)
    area = getattr(option, "area", None)
    data["area_name"] = enum_name(AreaType, area) if area is not None else None
    data["card_name"] = card_name(getattr(option, "cardId", None))
    data["attack_name"] = attack_name(getattr(option, "attackId", None))
    if observation is not None and player_index is not None:
        if area is not None and getattr(option, "index", None) is not None:
            data["resolved_card_name"] = get_area_card_name(
                observation,
                area,
                option.index,
                getattr(option, "playerIndex", player_index),
            )
        in_play_area = getattr(option, "inPlayArea", None)
        in_play_index = getattr(option, "inPlayIndex", None)
        if in_play_area is not None and in_play_index is not None:
            data["target_card_name"] = get_area_card_name(
                observation,
                in_play_area,
                in_play_index,
                getattr(option, "playerIndex", player_index),
            )
    return data


def describe_card_instance(card) -> dict:
    if card is None:
        return {}
    energies = [card_name(energy_id) for energy_id in getattr(card, "energies", [])]
    energy_cards = [card_name(getattr(energy_card, "id", None)) for energy_card in getattr(card, "energyCards", [])]
    tools = [card_name(getattr(tool, "id", None)) for tool in getattr(card, "tools", [])]
    pre_evolution = [card_name(getattr(prev, "id", None)) for prev in getattr(card, "preEvolution", [])]
    return {
        "name": card_name(getattr(card, "id", None)),
        "card_id": getattr(card, "id", None),
        "serial": getattr(card, "serial", None),
        "hp": getattr(card, "hp", None),
        "max_hp": getattr(card, "maxHp", None),
        "energies": [energy for energy in energies if energy],
        "energy_cards": [energy for energy in energy_cards if energy],
        "tools": [tool for tool in tools if tool],
        "pre_evolution": [prev for prev in pre_evolution if prev],
    }


def capture_board_snapshot(observation) -> dict:
    state = observation.current
    players = []
    for player in state.players:
        hand_cards = player.hand if player.hand is not None else []
        players.append(
            {
                "hand_count": getattr(player, "handCount", len(hand_cards)),
                "hand": [card_name(card.id) for card in hand_cards],
                "active": [describe_card_instance(card) for card in (player.active or [])],
                "bench": [describe_card_instance(card) for card in (player.bench or [])],
                "discard": [card_name(card.id) for card in (player.discard or [])],
                "discard_count": len(player.discard or []),
                "prize_count": len(player.prize or []),
                "deck_count": getattr(player, "deckCount", None),
            }
        )
    return {
        "turn": state.turn,
        "turn_action_count": state.turnActionCount,
        "current_player": state.yourIndex,
        "first_player": getattr(state, "firstPlayer", None),
        "stadium": [card_name(card.id) for card in (state.stadium or [])],
        "looking": [card_name(card.id) for card in (state.looking or [])] if state.looking is not None else [],
        "players": players,
    }


def describe_logs(logs) -> list[dict]:
    described = []
    for log in logs:
        data = normalize_for_json(log)
        data["type_name"] = enum_name(LogType, getattr(log, "type", None))
        from_area = getattr(log, "fromArea", None)
        to_area = getattr(log, "toArea", None)
        data["from_area_name"] = enum_name(AreaType, from_area) if from_area is not None else None
        data["to_area_name"] = enum_name(AreaType, to_area) if to_area is not None else None
        data["card_name"] = card_name(getattr(log, "cardId", None))
        data["card_name_active"] = card_name(getattr(log, "cardIdActive", None))
        data["card_name_bench"] = card_name(getattr(log, "cardIdBench", None))
        data["card_name_target"] = card_name(getattr(log, "cardIdTarget", None))
        data["attack_name"] = attack_name(getattr(log, "attackId", None))
        described.append(data)
    return described


def format_option_detail(option: dict) -> str:
    option_type = option.get("type_name", "UNKNOWN")
    card = option.get("resolved_card_name") or option.get("card_name")
    target = option.get("target_card_name")
    attack = option.get("attack_name")
    if option_type == "PLAY":
        return f"打出手牌 {card or '#'+str(option.get('index'))}"
    if option_type == "ATTACH":
        if card and target:
            return f"将 {card} 附加到 {target}"
        return "附加卡牌到目标宝可梦"
    if option_type == "ATTACK":
        return f"使用招式 {attack or option.get('attackId')}"
    if option_type == "RETREAT":
        return "撤退当前主动宝可梦"
    if option_type == "END":
        return "结束回合"
    if option_type == "ABILITY":
        return f"使用能力 {card or '#'+str(option.get('index'))}"
    if option_type == "EVOLVE":
        return f"让宝可梦进化为 {card or '#'+str(option.get('index'))}"
    if option_type == "CARD":
        area_name = area_name_zh(option.get("area_name"))
        idx = option.get("index")
        return f"选择 {area_name} 区的 {card or '#'+str(idx)}"
    if option_type == "YES":
        return "选择 YES"
    if option_type == "NO":
        return "选择 NO"
    if option_type == "NUMBER":
        return f"选择数字 {option.get('number')}"
    return option_type


def format_available_options(options: list[dict]) -> str:
    if not options:
        return "无"
    return "\n".join(f"    - [{idx}] {format_option_detail(option)}" for idx, option in enumerate(options))


def explain_log(log: dict) -> str:
    log_type = log.get("type_name", "UNKNOWN")
    if log_type == "DRAW":
        return f"玩家 {log.get('playerIndex')} 抽到了 {log.get('card_name') or log.get('cardId')}"
    if log_type == "DRAW_REVERSE":
        return f"玩家 {log.get('playerIndex')} 抽了 1 张未知牌"
    if log_type == "PLAY":
        return f"玩家 {log.get('playerIndex')} 打出了 {log.get('card_name') or log.get('cardId')}"
    if log_type == "ATTACH":
        return (
            f"玩家 {log.get('playerIndex')} 将 {log.get('card_name') or log.get('cardId')} "
            f"附加到 {log.get('card_name_target') or log.get('cardIdTarget')}"
        )
    if log_type == "ATTACK":
        return f"玩家 {log.get('playerIndex')} 使用了招式 {log.get('attack_name') or log.get('attackId')}"
    if log_type == "MOVE_CARD":
        return (
            f"玩家 {log.get('playerIndex')} 将 {log.get('card_name') or log.get('cardId')} "
            f"从 {area_name_zh(log.get('from_area_name'))} 移动到 {area_name_zh(log.get('to_area_name'))}"
        )
    return log_type


def explain_logs(logs: list[dict]) -> str:
    if not logs:
        return "无"
    return "\n".join(f"    - {explain_log(log)}" for log in logs[:8])


def format_step_log(step_record: dict) -> str:
    return (
        f"步骤 {step_record['step']}\n"
        f"  玩家: {step_record['player_index']} ({step_record['agent']})\n"
        f"  回合: {step_record['turn']}  动作序号: {step_record['turn_action_count']}\n"
        f"  动作选项: {step_record['context_name']} / {step_record['select_type_name']} / "
        f"共 {step_record['option_count']} 个 / 可选 {step_record['min_count']}..{step_record['max_count']}\n"
        f"  当前玩家手牌: {', '.join(step_record.get('hand_snapshot', [])) if step_record.get('hand_snapshot') else '未知'}\n"
        f"  动作选项详情:\n{format_available_options(step_record.get('available_options', []))}\n"
        f"  实际选择: {step_record.get('selected', [])}\n"
        f"  选择说明: {summarize_selected_options(step_record.get('selected_options', []))}\n"
        f"  本步事件: {summarize_logs(step_record.get('logs', []))}\n"
        f"  事件详情:\n{explain_logs(step_record.get('logs', []))}\n"
    )


def format_match_result(result: dict) -> str:
    termination = result.get("termination", {})
    lines = [
        "对战结果",
        f"  状态: {result.get('status')}",
        f"  Agent A: {result.get('agent_a')}",
        f"  Agent B: {result.get('agent_b')}",
        f"  winner: {result.get('winner')}",
        f"  终局原因: {termination.get('reason_key')}",
        f"  turn: {result.get('turn')}",
        f"  steps: {result.get('steps')}",
        "",
        "对战过程",
    ]
    for step in result.get("history", []):
        lines.append(format_step_log(step))
    if result.get("status") == "error":
        error = result.get("error", {})
        lines.extend(
            [
                "",
                "错误信息",
                f"  phase: {error.get('phase')}",
                f"  exception_type: {error.get('exception_type')}",
                f"  message: {error.get('message')}",
            ]
        )
    return "\n".join(lines).strip() + "\n"


def group_steps_by_turn(history: list[dict]) -> list[dict]:
    groups: list[dict] = []
    current_group = None
    for step in history:
        key = (step["turn"], step["player_index"])
        if current_group is None or current_group["key"] != key:
            current_group = {
                "key": key,
                "turn": step["turn"],
                "player_index": step["player_index"],
                "agent": step["agent"],
                "steps": [],
            }
            groups.append(current_group)
        current_group["steps"].append(step)
    return groups


def format_action_summary(step_record: dict) -> str:
    selected_options = step_record.get("selected_options", [])
    if not selected_options:
        return f"{step_record['context_name']}: 未记录具体选择"
    return "；".join(format_option_detail(option) for option in selected_options)


def summarize_turn_events(group: dict) -> list[str]:
    event_lines: list[str] = []
    seen: set[str] = set()
    for step in group["steps"]:
        for log in step.get("delta_logs", []):
            line = explain_log(log)
            if line in seen:
                continue
            seen.add(line)
            event_lines.append(line)
    return event_lines


def format_turn_group(group: dict) -> str:
    title = "准备阶段" if group["turn"] == 0 else f"第 {group['turn']} 回合"
    first_step = group["steps"][0]
    lines = [
        title,
        f"  玩家: {group['player_index']} ({group['agent']})",
        f"  起始手牌: {', '.join(first_step.get('hand_snapshot', [])) if first_step.get('hand_snapshot') else '未知'}",
        "  动作:",
    ]
    for step in group["steps"]:
        lines.append(f"    - 动作 {step['turn_action_count']}: {format_action_summary(step)}")
    lines.append("  结果:")
    event_lines = summarize_turn_events(group)
    if event_lines:
        for line in event_lines:
            lines.append(f"    - {line}")
    else:
        lines.append("    - 无可读事件")
    return "\n".join(lines)


def format_summary_result(result: dict) -> str:
    if "results" in result:
        lines = [
            "系列赛摘要",
            f"  对局数: {result.get('games')}",
            f"  交换先后手: {result.get('swap_sides')}",
            f"  胜场: {result.get('wins_by_agent')}",
            f"  平局: {result.get('draws')}",
            f"  平均回合: {result.get('average_turns'):.2f}",
            f"  平均步骤: {result.get('average_steps'):.2f}",
            "",
        ]
        for game in result.get("results", []):
            lines.append(
                f"第 {game['game_index']} 局: {game['agent_a']} vs {game['agent_b']} "
                f"winner={game['winner']} turn={game['turn']} steps={game['steps']}"
            )
        return "\n".join(lines).strip() + "\n"

    lines = [
        "对战摘要",
        f"  状态: {result.get('status')}",
        f"  Agent A: {result.get('agent_a')}",
        f"  Agent B: {result.get('agent_b')}",
        f"  winner: {result.get('winner')}",
        f"  终局原因: {result.get('termination', {}).get('reason_key')}",
        f"  turn: {result.get('turn')}",
        f"  steps: {result.get('steps')}",
        "",
        "回合摘要",
    ]
    for group in group_steps_by_turn(result.get("history", [])):
        lines.append(format_turn_group(group))
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def build_match_metrics(history: list[dict], winner, turn: int, steps: int, status: str) -> dict:
    action_counts_by_player: dict[str, int] = {}
    action_counts_by_select_type: dict[str, int] = {}
    for step_record in history:
        player_key = str(step_record.get("player_index"))
        action_counts_by_player[player_key] = action_counts_by_player.get(player_key, 0) + 1
        select_type = step_record.get("select_type_name", "UNKNOWN")
        action_counts_by_select_type[select_type] = action_counts_by_select_type.get(select_type, 0) + 1
    return {
        "winner": winner,
        "final_status": status,
        "total_turns": turn,
        "total_steps": steps,
        "steps_per_turn": (steps / turn) if turn else float(steps),
        "action_counts_by_player": action_counts_by_player,
        "action_counts_by_select_type": action_counts_by_select_type,
    }


def save_match_record(result: dict, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    record = dict(result)
    steps_payload = record.pop("steps_data", None)
    if steps_payload is not None:
        record["step_count"] = record.get("steps")
        record["steps"] = steps_payload
    output_path.write_text(json.dumps(normalize_for_json(record), indent=2), encoding="utf-8")


def save_human_log(result: dict, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(format_match_result(result), encoding="utf-8")


def save_summary_log(result: dict, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(format_summary_result(result), encoding="utf-8")


def save_replay_html(result: dict, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_replay_html(normalize_for_json(result), output_path)


def default_log_base_path(record_file: str, games: int) -> Path:
    if record_file:
        return Path(record_file).with_suffix("")
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    name = f"series-{timestamp}" if games > 1 else f"match-{timestamp}"
    return ROOT / "battle_records" / name


def build_log_paths(record_file: str, log_file: str, games: int) -> tuple[Path, Path]:
    if log_file:
        base = Path(log_file)
        if base.suffix:
            base = base.with_suffix("")
    else:
        base = default_log_base_path(record_file, games)
    return base.with_suffix(".summary.log"), base.with_suffix(".detail.log")


def build_replay_path(record_file: str, replay_file: str, log_file: str, games: int) -> Path:
    if replay_file:
        return Path(replay_file)
    if log_file:
        base = Path(log_file)
        if base.suffix:
            base = base.with_suffix("")
        return base.with_suffix(".replay.html")
    return default_log_base_path(record_file, games).with_suffix(".replay.html")
