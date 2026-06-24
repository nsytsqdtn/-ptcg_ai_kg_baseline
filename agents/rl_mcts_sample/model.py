from __future__ import annotations

import importlib.util
import math
import random
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BATTLE_ENV_ROOT = ROOT / "battle_env"
battle_env_root_str = str(BATTLE_ENV_ROOT)
if battle_env_root_str not in sys.path:
    sys.path.insert(0, battle_env_root_str)
import torch
import torch.nn
import torch.nn.functional

from cg.api import (  # noqa: E402
    AreaType,
    Card,
    Observation,
    OptionType,
    PlayerState,
    Pokemon,
    SearchState,
    SelectContext,
    all_attack,
    all_card_data,
    search_begin,
    search_end,
    search_step,
    to_observation_class,
)
from cg.game import battle_finish, battle_select, battle_start  # noqa: E402


all_card = all_card_data()
card_table = {c.cardId: c for c in all_card}
card_count = max(all_card, key=lambda c: c.cardId).cardId + 1
attack_count = max(all_attack(), key=lambda a: a.attackId).attackId + 1

NUM_WORDS_ENCODER = 24
ENCODER_SIZE = 22000
DECODER_MAIN_FEATURE = 8
DECODER_ATTACK_OFFSET = 14
DECODER_CARD_OFFSET = DECODER_ATTACK_OFFSET + attack_count
DECODER_SIZE = (
    DECODER_CARD_OFFSET
    + (1 + DECODER_MAIN_FEATURE + SelectContext.RECOVER_SPECIAL_CONDITION) * card_count
)

DEFAULT_SEARCH_COUNT = 10


def load_deck_from_csv(path: Path) -> list[int]:
    return [int(line.strip()) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


class DecoderLayer(torch.nn.Module):
    def __init__(self, d_model: int, num_heads: int, d_feedforward: int):
        super().__init__()
        self.attention = torch.nn.MultiheadAttention(d_model, num_heads)
        self.fc1 = torch.nn.Linear(d_model, d_feedforward)
        self.fc2 = torch.nn.Linear(d_feedforward, d_model)
        self.norm1 = torch.nn.LayerNorm(d_model)
        self.norm2 = torch.nn.LayerNorm(d_model)

    def forward(self, x: torch.Tensor, encoder_out: torch.Tensor) -> torch.Tensor:
        y, _ = self.attention(x, encoder_out, encoder_out, need_weights=False)
        residual = self.norm1(x + y)
        y = self.fc2(torch.nn.functional.relu(self.fc1(residual)))
        return self.norm2(residual + y)


class MyModel(torch.nn.Module):
    def __init__(
        self,
        d_model: int = 128,
        num_heads: int = 2,
        d_feedforward: int = 256,
        num_layers_encoder: int = 1,
        num_layers_decoder: int = 1,
    ):
        super().__init__()
        self.d_model = d_model
        self.encoder_bag = torch.nn.EmbeddingBag(ENCODER_SIZE, d_model, mode="sum")
        encoder_layer = torch.nn.TransformerEncoderLayer(d_model, num_heads, d_feedforward, 0)
        self.encoder = torch.nn.TransformerEncoder(encoder_layer, num_layers_encoder, enable_nested_tensor=False)
        self.encoder_fc = torch.nn.Linear(d_model, 1)
        self.decoder_bag = torch.nn.EmbeddingBag(DECODER_SIZE, d_model, mode="sum")
        self.decoder = torch.nn.ModuleList(
            [DecoderLayer(d_model, num_heads, d_feedforward) for _ in range(num_layers_decoder)]
        )
        self.decoder_fc = torch.nn.Linear(d_model, 1)

    def forward(
        self,
        index_encoder: torch.Tensor,
        value_encoder: torch.Tensor,
        offset_encoder: torch.Tensor,
        index_decoder: torch.Tensor,
        value_decoder: torch.Tensor,
        offset_decoder: torch.Tensor,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        value_state = self.encoder_bag(index_encoder, offset_encoder, value_encoder)
        value_state = value_state.reshape(-1, NUM_WORDS_ENCODER, self.d_model).transpose(0, 1)
        batch_size = value_state.size(1)
        encoder_out = self.encoder(value_state)
        value_out = torch.tanh(self.encoder_fc(encoder_out).mean(0))

        policy_state = self.decoder_bag(index_decoder, offset_decoder, value_decoder)
        policy_state = policy_state.reshape(batch_size, -1, self.d_model).transpose(0, 1)
        for layer in self.decoder:
            policy_state = layer(policy_state, encoder_out)
        policy_out = self.decoder_fc(policy_state).transpose(0, 1).view(batch_size, -1)
        return value_out, torch.tanh(policy_out)


class SparseVector:
    index: list[int]
    value: list[float]
    offset: list[int]
    pos: int

    def __init__(self):
        self.index = []
        self.value = []
        self.offset = []
        self.pos = 0

    def add(self, index: int, value: float | int | bool):
        numeric = float(value)
        if numeric != 0.0:
            self.index.append(self.pos + index)
            self.value.append(numeric)

    def add_pos(self, pos: int):
        self.pos += pos

    def add_single(self, value: float | int | bool):
        numeric = float(value)
        if numeric != 0.0:
            self.index.append(self.pos)
            self.value.append(numeric)
        self.pos += 1

    def word_start(self):
        self.offset.append(len(self.index))


def add_card(sv: SparseVector, card: Card | Pokemon | None):
    if card is not None:
        sv.add(card.id, 1)
    sv.add_pos(card_count)


def add_cards(sv: SparseVector, cards: list[Card] | None, value: float):
    if cards is not None:
        for card in cards:
            sv.add(card.id, value)
    sv.add_pos(card_count)


def add_pokemon(sv: SparseVector, poke: Pokemon | None):
    if poke is None:
        sv.add_single(1)
        sv.add_pos(1 + 3 * card_count)
        return
    sv.add_single(0)
    sv.add_single(poke.hp / 400)
    add_card(sv, poke)
    add_cards(sv, poke.tools, 1.0)
    add_cards(sv, poke.energyCards, 0.5)


def add_player(sv: SparseVector, player_state: PlayerState):
    sv.add_single(player_state.deckCount / 60)
    sv.add_single(len(player_state.discard) / 60)
    sv.add_single(player_state.handCount / 8)
    sv.add_single(len(player_state.bench) / 5)
    sv.add(len(player_state.prize), 1)
    sv.add_pos(7)
    sv.add_single(player_state.poisoned)
    sv.add_single(player_state.burned)
    sv.add_single(player_state.asleep)
    sv.add_single(player_state.paralyzed)
    sv.add_single(player_state.confused)
    add_cards(sv, player_state.discard, 0.25)


def get_encoder_input(obs: Observation, your_deck: list[int]) -> SparseVector:
    your_index = obs.current.yourIndex
    state = obs.current
    sv = SparseVector()
    for i in range(2):
        player_state = state.players[i ^ your_index]
        for j in range(8):
            sv.word_start()
            saved_pos = sv.pos
            add_pokemon(sv, player_state.bench[j] if j < len(player_state.bench) else None)
            if j != 7:
                sv.pos = saved_pos
    for i in range(2):
        player_state = state.players[i ^ your_index]
        sv.word_start()
        add_pokemon(sv, player_state.active[0] if player_state.active else None)
    for i in range(2):
        sv.word_start()
        add_player(sv, state.players[i ^ your_index])
    sv.word_start()
    add_cards(sv, state.players[your_index].hand, 0.25)
    sv.word_start()
    for card_id in your_deck:
        sv.add(card_id, 0.25)
    sv.add_pos(card_count)
    sv.word_start()
    add_cards(sv, state.stadium, 1.0)
    sv.word_start()
    sv.add_single(1)
    sv.add_single(state.turn / 10)
    sv.add_single(state.firstPlayer == your_index)
    return sv


def get_card(obs: Observation, area: AreaType, index: int, player_index: int) -> Pokemon | Card | None:
    player_state = obs.current.players[player_index]
    match area:
        case AreaType.DECK:
            return obs.select.deck[index]
        case AreaType.HAND:
            return player_state.hand[index]
        case AreaType.DISCARD:
            return player_state.discard[index]
        case AreaType.ACTIVE:
            return player_state.active[index]
        case AreaType.BENCH:
            return player_state.bench[index]
        case AreaType.PRIZE:
            return player_state.prize[index]
        case AreaType.STADIUM:
            return obs.current.stadium[index]
        case AreaType.LOOKING:
            return obs.current.looking[index]
        case _:
            return None


def decoder_main(sv: SparseVector, feature_index: int, card: Card | Pokemon | None):
    if card is not None:
        sv.add(DECODER_CARD_OFFSET + feature_index * card_count + card.id, 1)


def decoder_card_id(sv: SparseVector, context: SelectContext, card_id: int):
    sv.add(DECODER_CARD_OFFSET + (DECODER_MAIN_FEATURE + context) * card_count + card_id, 1)


def decoder_card(sv: SparseVector, context: SelectContext, card: Card | Pokemon | None):
    if card is not None:
        decoder_card_id(sv, context, card.id)


def get_decoder_input(obs: Observation, actions: list[list[int]]) -> SparseVector:
    sv = SparseVector()
    your_index = obs.current.yourIndex
    player_state = obs.current.players[your_index]
    context = obs.select.context
    for action in actions:
        sv.word_start()
        if not action:
            sv.add(0, 1)
            continue
        for index in action:
            option = obs.select.option[index]
            match option.type:
                case OptionType.END:
                    sv.add(1, 1)
                case OptionType.YES:
                    sv.add(2, 1)
                case OptionType.NO:
                    sv.add(3, 1)
                case OptionType.SPECIAL_CONDITION:
                    sv.add(4 + option.specialConditionType, 1)
                case OptionType.NUMBER:
                    sv.add(9 + min(option.number, 4), 1)
                case OptionType.ATTACK:
                    sv.add(DECODER_ATTACK_OFFSET + option.attackId, 1)
                case OptionType.PLAY:
                    decoder_main(sv, 0, player_state.hand[option.index])
                case OptionType.ATTACH:
                    decoder_main(sv, 1, get_card(obs, option.area, option.index, your_index))
                    decoder_main(sv, 2, get_card(obs, option.inPlayArea, option.inPlayIndex, your_index))
                case OptionType.EVOLVE:
                    decoder_main(sv, 3, get_card(obs, option.area, option.index, your_index))
                    decoder_main(sv, 4, get_card(obs, option.inPlayArea, option.inPlayIndex, your_index))
                case OptionType.ABILITY:
                    decoder_main(sv, 5, get_card(obs, option.area, option.index, your_index))
                case OptionType.DISCARD:
                    decoder_main(sv, 6, get_card(obs, option.area, option.index, your_index))
                case OptionType.RETREAT:
                    decoder_main(sv, 7, player_state.active[0])
                case OptionType.CARD:
                    decoder_card(sv, context, get_card(obs, option.area, option.index, option.playerIndex))
                case OptionType.TOOL_CARD:
                    card = get_card(obs, option.area, option.index, option.playerIndex)
                    decoder_card(sv, context, card.tools[option.toolIndex])
                case OptionType.ENERGY_CARD | OptionType.ENERGY:
                    card = get_card(obs, option.area, option.index, option.playerIndex)
                    decoder_card(sv, context, card.energyCards[option.energyIndex])
                case OptionType.SKILL:
                    decoder_card_id(sv, context, option.cardId)
    return sv


def eval_nn(sv_enc: SparseVector, sv_dec: SparseVector, model: MyModel) -> tuple[float, list[float]]:
    device = next(model.parameters()).device
    value, policy = model(
        torch.tensor(sv_enc.index, dtype=torch.int32, device=device),
        torch.tensor(sv_enc.value, dtype=torch.float32, device=device),
        torch.tensor(sv_enc.offset, dtype=torch.int32, device=device),
        torch.tensor(sv_dec.index, dtype=torch.int32, device=device),
        torch.tensor(sv_dec.value, dtype=torch.float32, device=device),
        torch.tensor(sv_dec.offset, dtype=torch.int32, device=device),
    )
    return value.tolist()[0][0], policy.tolist()[0]


class LearnSample:
    def __init__(self, value: float, policy: list[float], sv_enc: SparseVector, sv_dec: SparseVector):
        self.value = value
        self.policy = policy
        self.sv_enc = sv_enc
        self.sv_dec = sv_dec


class Child:
    def __init__(self, select: list[int], prob: float):
        self.node: Node | None = None
        self.select = select
        self.prob = prob


class Node:
    def __init__(self, parent: Node | None, state: SearchState):
        self.value = -2.0
        self.total = 0.0
        self.visit = 0
        self.parent = parent
        self.children: list[Child] = []
        self.state = state

    def backprop(self, value: float):
        self.total += value
        self.visit += 1
        if self.parent is not None:
            self.parent.backprop(value)


def enumerate_actions(obs: Observation, limit: int = 64) -> list[list[int]]:
    actions: list[list[int]] = []
    indices = list(range(obs.select.maxCount))
    for _ in range(limit):
        actions.append(indices.copy())
        for i in range(len(indices)):
            index = len(indices) - i - 1
            if indices[index] < len(obs.select.option) - i - 1:
                indices[index] += 1
                for j in range(index + 1, len(indices)):
                    indices[j] = indices[j - 1] + 1
                break
        else:
            break
    return actions


def create_node(
    parent: Node | None,
    search_state: SearchState,
    your_index: int,
    your_deck: list[int],
    model: MyModel,
) -> tuple[Node, LearnSample | None]:
    node = Node(parent, search_state)
    obs = search_state.observation
    state = obs.current
    if state.result >= 0:
        if state.result == 2:
            node.value = 0
        elif state.result == your_index:
            node.value = 1
        else:
            node.value = -1
        node.backprop(node.value)
        return node, None

    actions = enumerate_actions(obs)
    sv_enc = get_encoder_input(obs, your_deck)
    sv_dec = get_decoder_input(obs, actions)
    value, policy = eval_nn(sv_enc, sv_dec, model)
    node_value = value if state.yourIndex == your_index else -value
    node.value = node_value
    node.backprop(node_value)

    total = 0.0
    for index, action in enumerate(actions):
        prob = math.exp(policy[index] * 10.0)
        node.children.append(Child(action, prob))
        total += prob
    for child in node.children:
        child.prob /= total
    return node, LearnSample(value, policy, sv_enc, sv_dec)


def mcts_agent(
    obs_dict: dict,
    your_deck: list[int],
    model: MyModel,
    *,
    search_count: int = DEFAULT_SEARCH_COUNT,
) -> tuple[list[int], LearnSample]:
    obs = to_observation_class(obs_dict)
    your_index = obs.current.yourIndex
    state = obs.current
    active = state.players[1 - your_index].active
    search_state = search_begin(
        obs,
        your_deck=random.sample(your_deck, state.players[your_index].deckCount),
        your_prize=random.sample(your_deck, len(state.players[your_index].prize)),
        opponent_deck=[1072] * state.players[1 - your_index].deckCount,
        opponent_prize=[1] * len(state.players[1 - your_index].prize),
        opponent_hand=[1] * state.players[1 - your_index].handCount,
        opponent_active=[1072] if len(active) > 0 and active[0] is None else [],
    )
    root, sample = create_node(None, search_state, your_index, your_deck, model)
    for _ in range(search_count):
        current = root
        while True:
            best_value = -1e9
            exploration = 0.4 * math.sqrt(current.visit)
            next_child = None
            for child in current.children:
                visit = 0
                if child.node is None:
                    value = current.total / current.visit
                else:
                    value = child.node.total / child.node.visit
                    visit = child.node.visit
                if current.state.observation.current.yourIndex != your_index:
                    value = -value
                value += exploration * child.prob / (1 + visit)
                if value > best_value:
                    best_value = value
                    next_child = child
            if next_child is None:
                raise RuntimeError("MCTS failed to select a child node.")
            if next_child.node is None:
                next_state = search_step(current.state.searchId, next_child.select)
                next_child.node, _ = create_node(current, next_state, your_index, your_deck, model)
                break
            current = next_child.node
            if current.state.observation.current.result >= 0:
                current.backprop(current.value)
                break

    max_child = None
    max_visit = -1
    min_value = 10.0
    for child in root.children:
        if child.node is not None:
            if child.node.visit > max_visit:
                max_child = child
                max_visit = child.node.visit
            child_value = child.node.total / child.node.visit
            if child_value < min_value:
                min_value = child_value
    if max_child is None or sample is None:
        raise RuntimeError("MCTS did not produce a selectable action.")

    sample.value = root.total / root.visit
    for index, child in enumerate(root.children):
        child_value = sample.value
        if child.node is None:
            child_value = min_value - child_value - 0.03
        else:
            child_value = child.node.total / child.node.visit - child_value
        sample.policy[index] = max(-1.0, min(1.0, child_value))
    search_end()
    return max_child.select, sample


class LearnInput:
    def __init__(self):
        self.index: list[int] = []
        self.value: list[float] = []
        self.offset: list[int] = []

    def add(self, sv: SparseVector):
        count = len(self.index)
        self.index.extend(sv.index)
        self.value.extend(sv.value)
        for offset in sv.offset:
            self.offset.append(offset + count)


def random_agent(obs_dict: dict) -> list[int]:
    obs = to_observation_class(obs_dict)
    return random.sample(list(range(len(obs.select.option))), obs.select.maxCount)


def load_external_agent_module(agent_path: Path):
    module_name = f"train_agent_{agent_path.parent.name}"
    spec = importlib.util.spec_from_file_location(module_name, agent_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def resolve_named_agent_path(agent_name: str) -> Path:
    agent_dir = ROOT / "agents" / agent_name
    for filename in ("main.py", "agent.py"):
        candidate = agent_dir / filename
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"Unknown training opponent: {agent_name}")


def load_named_opponent(agent_name: str):
    return load_external_agent_module(resolve_named_agent_path(agent_name))


def progress(count: int, text: str):
    current = 0
    while True:
        percent = 100 * current // count
        sys.stderr.write(f"\r{text} {percent}%   ")
        sys.stderr.flush()
        if current >= count:
            sys.stderr.write("\n")
            sys.stderr.flush()
            break
        yield current
        current += 1


@dataclass
class TrainConfig:
    iterations: int = 5
    evaluation_games: int = 50
    self_play_games: int = 100
    batch_size: int = 128
    learning_rate: float = 3e-4
    lambda_value: float = 0.9
    search_count: int = DEFAULT_SEARCH_COUNT
    opponents: tuple[str, ...] = ("dragapult_rule_based", "mega_lucario_beginner")


def create_model(device: torch.device | None = None) -> MyModel:
    model = MyModel()
    if device is not None:
        model = model.to(device)
    return model


def validate_start_data(start_data):
    if start_data.errorPlayer < 0:
        return
    error = "Deck error."
    if start_data.errorType == 1:
        error = "The deck contains invalid card ID."
    elif start_data.errorType == 2:
        error = "You can include up to four cards with the same name in the deck, excluding basic Energy cards."
    elif start_data.errorType == 3:
        error = "There are no Basic Pokémon in the deck."
    elif start_data.errorType == 4:
        error = "You can include only one Ace Spec card in the deck."
    raise ValueError(error)


def play_named_opponent_game(
    model: MyModel,
    deck: list[int],
    opponent_module,
    *,
    search_count: int,
    collect_samples: bool,
    lambda_value: float = 0.9,
):
    your_index = random.randint(0, 1)
    decks = [list(deck), list(opponent_module.my_deck)]
    if your_index == 1:
        decks = [decks[1], decks[0]]
    obs, start_data = battle_start(decks[0], decks[1])
    validate_start_data(start_data)
    samples: list[LearnSample] = []
    while True:
        if obs["current"]["result"] >= 0:
            break
        current_index = obs["current"]["yourIndex"]
        if current_index == your_index:
            selected, sample = mcts_agent(obs, deck, model, search_count=search_count)
            if collect_samples:
                samples.append(sample)
        else:
            selected = opponent_module.agent(obs)
        obs = battle_select(selected)
    battle_finish()
    if collect_samples:
        value = 1.0 if your_index == obs["current"]["result"] else -1.0
        for sample in reversed(samples):
            label = (value + sample.value) * 0.5
            value = value * lambda_value + sample.value * (1.0 - lambda_value)
            sample.value = label
    return obs, your_index, samples


def evaluate_model(model: MyModel, deck: list[int], games: int, search_count: int, opponent_module) -> dict[str, int]:
    results = {"win": 0, "lose": 0, "draw": 0}
    model.eval()
    with torch.inference_mode():
        for _ in progress(games, "Evaluating..."):
            obs, your_index, _ = play_named_opponent_game(
                model,
                deck,
                opponent_module,
                search_count=search_count,
                collect_samples=False,
            )
            if obs["current"]["result"] == 2:
                results["draw"] += 1
            elif obs["current"]["result"] == your_index:
                results["win"] += 1
            else:
                results["lose"] += 1
    return results


def collect_opponent_samples(
    model: MyModel,
    deck: list[int],
    games: int,
    search_count: int,
    lambda_value: float,
    opponent_modules: list,
):
    sample_list: list[LearnSample] = []
    model.eval()
    with torch.inference_mode():
        for _ in progress(games, "Training Data Collecting..."):
            opponent_module = random.choice(opponent_modules)
            _, _, samples = play_named_opponent_game(
                model,
                deck,
                opponent_module,
                search_count=search_count,
                collect_samples=True,
                lambda_value=lambda_value,
            )
            sample_list.extend(samples)
    return sample_list


def train_epoch(
    model: MyModel,
    optimizer: torch.optim.Optimizer,
    sample_list: list[LearnSample],
    batch_size: int,
):
    loss_fn_enc = torch.nn.HuberLoss(delta=0.2)
    loss_fn_dec = torch.nn.HuberLoss(reduction="none", delta=0.1)
    device = next(model.parameters()).device
    model.train()
    random.shuffle(sample_list)
    batch_count = len(sample_list) // batch_size
    for batch_index in range(batch_count):
        input_enc = LearnInput()
        input_dec = LearnInput()
        mask: list[float] = []
        label_enc: list[float] = []
        label_dec: list[float] = []
        start = batch_size * batch_index
        for sample_index in range(start, start + batch_size):
            sample = sample_list[sample_index]
            input_enc.add(sample.sv_enc)
            input_dec.add(sample.sv_dec)
            label_enc.append(sample.value)
            label_dec.extend(sample.policy)
            for _ in range(len(sample.policy)):
                mask.append(1.0)
            for _ in range(64 - len(sample.policy)):
                mask.append(0.0)
                label_dec.append(0.0)
                input_dec.offset.append(len(input_dec.index))

        mask_tensor = torch.tensor(mask, dtype=torch.float32, device=device).view(batch_size, -1)
        label_tensor_enc = torch.tensor(label_enc, dtype=torch.float32, device=device).view(batch_size, -1)
        label_tensor_dec = torch.tensor(label_dec, dtype=torch.float32, device=device).view(batch_size, -1)

        optimizer.zero_grad()
        out_enc, out_dec = model(
            torch.tensor(input_enc.index, dtype=torch.int32, device=device),
            torch.tensor(input_enc.value, dtype=torch.float32, device=device),
            torch.tensor(input_enc.offset, dtype=torch.int32, device=device),
            torch.tensor(input_dec.index, dtype=torch.int32, device=device),
            torch.tensor(input_dec.value, dtype=torch.float32, device=device),
            torch.tensor(input_dec.offset, dtype=torch.int32, device=device),
        )
        loss_enc = loss_fn_enc(out_enc, label_tensor_enc)
        loss_dec = loss_fn_dec(out_dec, label_tensor_dec)
        loss = loss_enc + (loss_dec * mask_tensor).sum() / float(batch_size)
        loss.backward()
        optimizer.step()


def save_checkpoint(model: MyModel, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(model.state_dict(), path)
