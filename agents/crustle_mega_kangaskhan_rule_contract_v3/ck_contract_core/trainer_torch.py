from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

import torch
import torch.nn.functional as F


class ActionConditionedActorCritic(torch.nn.Module):
    def __init__(self, obs_dim: int, action_dim: int, hidden_dim: int = 64):
        super().__init__()
        self.obs_net = torch.nn.Sequential(
            torch.nn.Linear(obs_dim, hidden_dim),
            torch.nn.ReLU(),
        )
        self.policy_hidden = torch.nn.Sequential(
            torch.nn.Linear(hidden_dim + action_dim + 1, hidden_dim),
            torch.nn.ReLU(),
        )
        self.policy_out = torch.nn.Linear(hidden_dim, 1)
        self.value_hidden = torch.nn.Sequential(
            torch.nn.Linear(hidden_dim, hidden_dim),
            torch.nn.ReLU(),
        )
        self.value_out = torch.nn.Linear(hidden_dim, 1)

    def obs_embed(self, obs: torch.Tensor) -> torch.Tensor:
        return self.obs_net(obs)

    def value(self, obs_embed: torch.Tensor) -> torch.Tensor:
        return self.value_out(self.value_hidden(obs_embed)).squeeze(-1)

    def policy_logits(self, obs_embed: torch.Tensor, actions: torch.Tensor, rule_logits: torch.Tensor) -> torch.Tensor:
        batch, action_count, _ = actions.shape
        repeated = obs_embed.unsqueeze(1).expand(batch, action_count, obs_embed.shape[-1])
        inputs = torch.cat([repeated, actions, rule_logits.unsqueeze(-1)], dim=-1)
        hidden = self.policy_hidden(inputs)
        return self.policy_out(hidden).squeeze(-1)


def parse_args():
    parser = argparse.ArgumentParser(description="Train distillation or PPO policy/value network.")
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--metrics-output", type=Path, required=True)
    parser.add_argument("--mode", choices=["distill", "ppo"], required=True)
    parser.add_argument("--epochs", type=int, default=8)
    parser.add_argument("--beta", type=float, default=0.2)
    parser.add_argument("--learning-rate", type=float, default=3e-4)
    parser.add_argument("--clip-range", type=float, default=0.2)
    parser.add_argument("--value-coef", type=float, default=0.5)
    parser.add_argument("--entropy-coef", type=float, default=0.01)
    parser.add_argument("--kl-rule-coef", type=float, default=0.02)
    parser.add_argument("--kl-rule-final-coef", type=float)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--init-model", type=Path)
    return parser.parse_args()


def build_model(samples: list[dict], device: torch.device) -> ActionConditionedActorCritic:
    obs_dim = len(samples[0]["observation_features"])
    action_dim = len(samples[0]["action_features"][0])
    return ActionConditionedActorCritic(obs_dim, action_dim).to(device)


def export_model(model: ActionConditionedActorCritic, output: Path, beta: float):
    export = {
        "obs_hidden_weights": model.obs_net[0].weight.detach().cpu().tolist(),
        "obs_hidden_bias": model.obs_net[0].bias.detach().cpu().tolist(),
        "policy_hidden_weights": model.policy_hidden[0].weight.detach().cpu().tolist(),
        "policy_hidden_bias": model.policy_hidden[0].bias.detach().cpu().tolist(),
        "output_weights": model.policy_out.weight.detach().cpu().tolist(),
        "output_bias": model.policy_out.bias.detach().cpu().tolist(),
        "value_hidden_weights": model.value_hidden[0].weight.detach().cpu().tolist(),
        "value_hidden_bias": model.value_hidden[0].bias.detach().cpu().tolist(),
        "value_output_weights": model.value_out.weight.detach().cpu().tolist(),
        "value_output_bias": model.value_out.bias.detach().cpu().tolist(),
        "beta": beta,
    }
    output.write_text(json.dumps(export), encoding="utf-8")


def _load_export(path: Path) -> dict | None:
    if path is None or not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _copy_linear_weights(module: torch.nn.Linear, weights: list[list[float]], bias: list[float]):
    if tuple(module.weight.shape) != (len(weights), len(weights[0])):
        raise ValueError("checkpoint shape mismatch")
    if tuple(module.bias.shape) != (len(bias),):
        raise ValueError("checkpoint bias shape mismatch")
    module.weight.data.copy_(torch.tensor(weights, dtype=module.weight.dtype, device=module.weight.device))
    module.bias.data.copy_(torch.tensor(bias, dtype=module.bias.dtype, device=module.bias.device))


def maybe_load_model(model: ActionConditionedActorCritic, init_model: Path | None):
    payload = _load_export(init_model) if init_model is not None else None
    if payload is None:
        return
    _copy_linear_weights(model.obs_net[0], payload["obs_hidden_weights"], payload["obs_hidden_bias"])
    _copy_linear_weights(model.policy_hidden[0], payload["policy_hidden_weights"], payload["policy_hidden_bias"])
    _copy_linear_weights(model.policy_out, payload["output_weights"], payload["output_bias"])
    _copy_linear_weights(model.value_hidden[0], payload["value_hidden_weights"], payload["value_hidden_bias"])
    _copy_linear_weights(model.value_out, payload["value_output_weights"], payload["value_output_bias"])


def _iter_minibatches(samples: list[dict], batch_size: int):
    shuffled = list(samples)
    random.shuffle(shuffled)
    size = max(1, batch_size)
    for start in range(0, len(shuffled), size):
        yield shuffled[start : start + size]


def _tensor(values, device: torch.device):
    return torch.tensor(values, dtype=torch.float32, device=device)


def _forward_sample(model, sample: dict, beta: float, device: torch.device):
    obs = _tensor(sample["observation_features"], device).unsqueeze(0)
    actions = _tensor(sample["action_features"], device).unsqueeze(0)
    rule_logits = _tensor(sample["rule_logits"], device).unsqueeze(0)
    obs_embed = model.obs_embed(obs)
    residual = model.policy_logits(obs_embed, actions, rule_logits)
    final_logits = rule_logits + beta * residual
    return obs_embed, rule_logits, final_logits


def distill_epoch(
    model,
    samples: list[dict],
    optimizer,
    beta: float,
    kl_rule_coef: float,
    batch_size: int,
    device: torch.device,
) -> dict:
    loss_total = 0.0
    policy_total = 0.0
    value_total = 0.0
    kl_total = 0.0
    sample_count = 0
    for batch in _iter_minibatches(samples, batch_size):
        optimizer.zero_grad()
        batch_loss = torch.tensor(0.0, device=device)
        for sample in batch:
            obs_embed, rule_logits, final_logits = _forward_sample(model, sample, beta=beta, device=device)
            target_logits = _tensor(sample["final_logits"], device).unsqueeze(0)
            target_probs = torch.softmax(target_logits, dim=-1)
            pred_log_probs = torch.log_softmax(final_logits, dim=-1)
            kl = F.kl_div(pred_log_probs, target_probs, reduction="batchmean", log_target=False)
            target_return = _tensor([sample.get("return", 0.0)], device)
            value_loss = F.smooth_l1_loss(model.value(obs_embed), target_return)
            loss = kl + value_loss * 0.2 + kl_rule_coef * kl
            batch_loss = batch_loss + loss
            batch_item_count = 1
            sample_count += batch_item_count
            loss_total += float(loss.detach().cpu().item())
            policy_total += float(kl.detach().cpu().item())
            value_total += float(value_loss.detach().cpu().item())
            kl_total += float(kl.detach().cpu().item())
        batch_loss = batch_loss / max(1, len(batch))
        batch_loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
        optimizer.step()
    count = max(1, sample_count)
    return {
        "loss_total": loss_total / count,
        "policy_loss": policy_total / count,
        "value_loss": value_total / count,
        "entropy": 0.0,
        "kl_to_rule": kl_total / count,
    }


def ppo_epoch(
    model,
    samples: list[dict],
    optimizer,
    beta: float,
    clip_range: float,
    value_coef: float,
    entropy_coef: float,
    kl_rule_coef: float,
    batch_size: int,
    device: torch.device,
) -> dict:
    advantages = [float(sample["advantage"]) for sample in samples]
    advantage_mean = sum(advantages) / max(1, len(advantages))
    advantage_var = sum((value - advantage_mean) ** 2 for value in advantages) / max(1, len(advantages))
    advantage_std = max(advantage_var**0.5, 1e-6)

    loss_total = 0.0
    policy_total = 0.0
    value_total = 0.0
    entropy_total = 0.0
    kl_total = 0.0
    sample_count = 0
    for batch in _iter_minibatches(samples, batch_size):
        optimizer.zero_grad()
        batch_loss = torch.tensor(0.0, device=device)
        for sample in batch:
            _, rule_logits, final_logits = _forward_sample(model, sample, beta=beta, device=device)
            selected_rank = int(sample["selected_rank"])
            old_logprob = _tensor(sample["logprob"], device)
            advantage_value = (float(sample["advantage"]) - advantage_mean) / advantage_std
            advantage = _tensor(advantage_value, device)
            ret = _tensor(sample["return"], device)

            log_probs = torch.log_softmax(final_logits, dim=-1)
            probs = torch.softmax(final_logits, dim=-1)
            new_logprob = log_probs[0, selected_rank]
            ratio = torch.exp(new_logprob - old_logprob)
            unclipped = ratio * advantage
            clipped = torch.clamp(ratio, 1.0 - clip_range, 1.0 + clip_range) * advantage
            policy_loss = -torch.min(unclipped, clipped)

            obs = _tensor(sample["observation_features"], device).unsqueeze(0)
            value_pred = model.value(model.obs_embed(obs)).squeeze(0)
            value_loss = F.smooth_l1_loss(value_pred, ret)
            entropy = -(probs * log_probs).sum(dim=-1).mean()
            rule_probs = torch.softmax(rule_logits, dim=-1)
            kl = torch.sum(probs * (torch.log(probs + 1e-8) - torch.log(rule_probs + 1e-8)), dim=-1).mean()
            loss = policy_loss + value_coef * value_loss - entropy_coef * entropy + kl_rule_coef * kl
            batch_loss = batch_loss + loss
            sample_count += 1
            loss_total += float(loss.detach().cpu().item())
            policy_total += float(policy_loss.detach().cpu().item())
            value_total += float(value_loss.detach().cpu().item())
            entropy_total += float(entropy.detach().cpu().item())
            kl_total += float(kl.detach().cpu().item())
        batch_loss = batch_loss / max(1, len(batch))
        batch_loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
        optimizer.step()
    count = max(1, sample_count)
    return {
        "loss_total": loss_total / count,
        "policy_loss": policy_total / count,
        "value_loss": value_total / count,
        "entropy": entropy_total / count,
        "kl_to_rule": kl_total / count,
    }


def main():
    args = parse_args()
    payload = json.loads(args.dataset.read_text(encoding="utf-8"))
    samples = payload["samples"]
    if not samples:
        raise RuntimeError("Dataset is empty.")
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = build_model(samples, device)
    maybe_load_model(model, args.init_model)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.learning_rate)
    history: list[dict] = []
    kl_rule_final = args.kl_rule_final_coef
    if kl_rule_final is None:
        kl_rule_final = args.kl_rule_coef if args.mode == "distill" else max(0.005, args.kl_rule_coef * 0.25)

    for epoch in range(args.epochs):
        if args.epochs <= 1:
            kl_rule_coef = args.kl_rule_coef
        else:
            alpha = epoch / float(args.epochs - 1)
            kl_rule_coef = args.kl_rule_coef + (kl_rule_final - args.kl_rule_coef) * alpha
        if args.mode == "distill":
            metrics = distill_epoch(
                model,
                samples,
                optimizer,
                beta=args.beta,
                kl_rule_coef=kl_rule_coef,
                batch_size=args.batch_size,
                device=device,
            )
        else:
            metrics = ppo_epoch(
                model,
                samples,
                optimizer,
                beta=args.beta,
                clip_range=args.clip_range,
                value_coef=args.value_coef,
                entropy_coef=args.entropy_coef,
                kl_rule_coef=kl_rule_coef,
                batch_size=args.batch_size,
                device=device,
            )
        metrics["epoch"] = epoch + 1
        metrics["samples"] = len(samples)
        metrics["kl_rule_coef"] = kl_rule_coef
        history.append(metrics)
        print(
            f"mode={args.mode} epoch={metrics['epoch']} samples={metrics['samples']} "
            f"loss={metrics['loss_total']:.4f} policy={metrics['policy_loss']:.4f} "
            f"value={metrics['value_loss']:.4f} entropy={metrics['entropy']:.4f} "
            f"kl={metrics['kl_to_rule']:.6f}",
            flush=True,
        )

    export_model(model, args.output, beta=args.beta)
    args.metrics_output.write_text(
        json.dumps(
            {
                "device": str(device),
                "mode": args.mode,
                "epochs": args.epochs,
                "learning_rate": args.learning_rate,
                "beta": args.beta,
                "clip_range": args.clip_range,
                "value_coef": args.value_coef,
                "entropy_coef": args.entropy_coef,
                "kl_rule_coef": args.kl_rule_coef,
                "kl_rule_final_coef": kl_rule_final,
                "batch_size": args.batch_size,
                "init_model": None if args.init_model is None else str(args.init_model),
                "dataset_samples": len(samples),
                "history": history,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
