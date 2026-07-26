"""
05_train_lora_cpu.py
====================
CPU LoRA fine-tuning of Qwen2-0.5B-Instruct on the prepared legal dataset.

Key design decisions for CPU:
  - Float32 (no bfloat16/float16 on CPU)
  - No bitsandbytes quantization (CUDA only)
  - LoRA rank 8 — minimal trainable params
  - max_seq_length 512 — keeps memory under 8 GB
  - gradient_accumulation=8 — effective batch=8 with batch_size=1
  - Checkpointing every N steps — resumable on Windows restart
  - Logging loss every step so you can see it decreasing

Smoke test (verify the pipeline works — ~5-10 min on CPU):
    python scripts/05_train_lora_cpu.py --limit 100 --epochs 1

Larger experiment:
    python scripts/05_train_lora_cpu.py --limit 1000 --epochs 1

Full training (use only if smoke test succeeds):
    python scripts/05_train_lora_cpu.py --epochs 3

Resume after interruption:
    python scripts/05_train_lora_cpu.py --resume models/adapters/legal-ipc-lora

Usage:
    python scripts/05_train_lora_cpu.py [options]
"""

import json
import os
import re
import argparse
import time
import math
from pathlib import Path


# ── Config ────────────────────────────────────────────────────────────────────
BASE_MODEL    = "Qwen/Qwen2-0.5B-Instruct"
ADAPTER_DIR   = "models/adapters/legal-ipc-lora"
CHECKPOINT_DIR= "models/adapters/legal-ipc-lora/checkpoints"
LOG_FILE      = "logs/training_log.jsonl"

LORA_R        = 8
LORA_ALPHA    = 16
LORA_DROPOUT  = 0.05
TARGET_MODULES= ["q_proj", "v_proj", "o_proj"]   # safe for Qwen2

BATCH_SIZE    = 1
GRAD_ACCUM    = 8
MAX_SEQ_LEN   = 512
LR            = 2e-4
WARMUP_STEPS  = 10
SAVE_STEPS    = 50


def load_jsonl(path: Path) -> list:
    if not path.exists():
        return []
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def format_prompt(record: dict, tokenizer) -> str:
    """Format a record as a chat prompt + answer for SFT."""
    instruction = record.get("instruction", "")
    input_text  = record.get("input", "")
    output      = record.get("output", "")

    messages = [
        {"role": "system", "content": instruction},
        {"role": "user",   "content": input_text},
    ]
    try:
        prompt_only = tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
    except Exception:
        prompt_only = f"System: {instruction}\nUser: {input_text}\nAssistant:"

    return prompt_only + output + tokenizer.eos_token


def make_dataset(records: list, tokenizer, max_len: int):
    """Tokenize records and return a list of input_ids tensors."""
    import torch

    tokenized = []
    for rec in records:
        text = format_prompt(rec, tokenizer)
        enc  = tokenizer(
            text,
            truncation=True,
            max_length=max_len,
            padding=False,
            return_tensors="pt",
        )
        ids = enc["input_ids"][0]
        if len(ids) < 5:
            continue
        tokenized.append(ids)

    return tokenized


def save_experiment_log(exp_info: dict):
    Path(LOG_FILE).parent.mkdir(exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(exp_info, ensure_ascii=False) + "\n")


def train(records: list, val_records: list, tokenizer, model,
          epochs: int, save_steps: int, adapter_dir: str) -> dict:
    import torch
    from torch.optim import AdamW
    from torch.optim.lr_scheduler import LinearLR

    device     = "cpu"
    model      = model.to(device)
    model.train()

    # Tokenize
    print("Tokenizing training data...")
    train_ids = make_dataset(records, tokenizer, MAX_SEQ_LEN)
    val_ids   = make_dataset(val_records, tokenizer, MAX_SEQ_LEN) if val_records else []
    print(f"Train tokens: {len(train_ids)} sequences")

    optimizer  = AdamW(
        [p for p in model.parameters() if p.requires_grad],
        lr=LR, weight_decay=0.01
    )
    total_steps = math.ceil(len(train_ids) * epochs / GRAD_ACCUM)
    warmup      = min(WARMUP_STEPS, total_steps // 4)
    scheduler   = LinearLR(optimizer, start_factor=0.1, end_factor=1.0,
                            total_iters=warmup)

    global_step  = 0
    best_val_loss= float("inf")
    train_log    = []

    Path(adapter_dir).mkdir(parents=True, exist_ok=True)

    for epoch in range(1, epochs + 1):
        epoch_loss = 0.0
        n_batches  = 0
        optimizer.zero_grad()

        for step, ids in enumerate(train_ids):
            # ── Forward ───────────────────────────────────────────────────
            ids_t  = ids.unsqueeze(0).to(device)   # [1, seq_len]
            labels = ids_t.clone()
            labels[labels == tokenizer.pad_token_id] = -100

            outputs = model(input_ids=ids_t, labels=labels)
            loss    = outputs.loss / GRAD_ACCUM

            # ── Backward ──────────────────────────────────────────────────
            loss.backward()
            epoch_loss += loss.item() * GRAD_ACCUM
            n_batches  += 1

            # ── Optimizer step every GRAD_ACCUM samples ───────────────────
            if (step + 1) % GRAD_ACCUM == 0 or (step + 1) == len(train_ids):
                torch.nn.utils.clip_grad_norm_(
                    [p for p in model.parameters() if p.requires_grad], 1.0
                )
                optimizer.step()
                scheduler.step()
                optimizer.zero_grad()
                global_step += 1

                avg_loss = epoch_loss / n_batches
                print(f"  Epoch {epoch}  Step {global_step:>4}  "
                      f"loss={avg_loss:.4f}  lr={scheduler.get_last_lr()[0]:.2e}")

                train_log.append({
                    "epoch": epoch,
                    "step":  global_step,
                    "loss":  round(avg_loss, 4),
                })

                # ── Checkpoint ────────────────────────────────────────────
                if global_step % save_steps == 0:
                    ckpt_path = Path(CHECKPOINT_DIR) / f"step-{global_step:06d}"
                    model.save_pretrained(str(ckpt_path))
                    tokenizer.save_pretrained(str(ckpt_path))
                    print(f"  Checkpoint saved → {ckpt_path}")

        # ── Validation loss ───────────────────────────────────────────────
        if val_ids:
            model.eval()
            val_loss_sum = 0.0
            with torch.no_grad():
                for ids in val_ids:
                    ids_t  = ids.unsqueeze(0).to(device)
                    labels = ids_t.clone()
                    labels[labels == tokenizer.pad_token_id] = -100
                    out    = model(input_ids=ids_t, labels=labels)
                    val_loss_sum += out.loss.item()
            val_loss = val_loss_sum / len(val_ids)
            model.train()
            print(f"\n  Epoch {epoch} complete — "
                  f"train_loss={epoch_loss/n_batches:.4f}  "
                  f"val_loss={val_loss:.4f}\n")
            if val_loss < best_val_loss:
                best_val_loss = val_loss
                model.save_pretrained(f"{adapter_dir}/best")
                tokenizer.save_pretrained(f"{adapter_dir}/best")
                print(f"  ✓ New best val_loss={val_loss:.4f} saved to {adapter_dir}/best")
        else:
            print(f"\n  Epoch {epoch} complete — "
                  f"train_loss={epoch_loss/n_batches:.4f}\n")

    # Final save
    model.save_pretrained(f"{adapter_dir}/final")
    tokenizer.save_pretrained(f"{adapter_dir}/final")
    print(f"\n  Final adapter saved → {adapter_dir}/final")

    return {"train_log": train_log, "best_val_loss": best_val_loss}


def main():
    parser = argparse.ArgumentParser(description="CPU LoRA fine-tuning")
    parser.add_argument("--model",       default=BASE_MODEL)
    parser.add_argument("--data_dir",    default="data/processed")
    parser.add_argument("--adapter_dir", default=ADAPTER_DIR)
    parser.add_argument("--epochs",      type=int,   default=1)
    parser.add_argument("--limit",       type=int,   default=0,
                        help="Max training examples (0=all). Use 100 for smoke test.")
    parser.add_argument("--save_steps",  type=int,   default=SAVE_STEPS)
    parser.add_argument("--resume",      default="",
                        help="Path to checkpoint dir to resume from")
    args = parser.parse_args()

    # ── Load data ─────────────────────────────────────────────────────────────
    train_records = load_jsonl(Path(args.data_dir) / "train" / "dataset.jsonl")
    val_records   = load_jsonl(Path(args.data_dir) / "val"   / "dataset.jsonl")

    if not train_records:
        print("ERROR: No training data. Run 02_prepare_dataset.py first.")
        raise SystemExit(1)

    if args.limit > 0:
        train_records = train_records[:args.limit]
        print(f"Using {len(train_records)} training records (--limit {args.limit})")
    else:
        print(f"Using all {len(train_records)} training records")

    # ── Load model + apply LoRA ───────────────────────────────────────────────
    print(f"\nLoading base model: {args.model}")
    from transformers import AutoTokenizer, AutoModelForCausalLM
    from peft import LoraConfig, TaskType, get_peft_model, PeftModel
    import torch

    tokenizer = AutoTokenizer.from_pretrained(
        args.model, trust_remote_code=True, padding_side="right"
    )
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    if args.resume and Path(args.resume).exists():
        print(f"Resuming from checkpoint: {args.resume}")
        base_model = AutoModelForCausalLM.from_pretrained(
            args.model, torch_dtype=torch.float32, trust_remote_code=True
        )
        model = PeftModel.from_pretrained(base_model, args.resume, is_trainable=True)
    else:
        base_model = AutoModelForCausalLM.from_pretrained(
            args.model, torch_dtype=torch.float32, trust_remote_code=True
        )
        lora_cfg = LoraConfig(
            r             = LORA_R,
            lora_alpha    = LORA_ALPHA,
            lora_dropout  = LORA_DROPOUT,
            bias          = "none",
            task_type     = TaskType.CAUSAL_LM,
            target_modules= TARGET_MODULES,
        )
        model = get_peft_model(base_model, lora_cfg)

    # Print trainable parameter count
    trainable  = sum(p.numel() for p in model.parameters() if p.requires_grad)
    total      = sum(p.numel() for p in model.parameters())
    print(f"Trainable params: {trainable:,} / {total:,} "
          f"({100*trainable/total:.2f}%)")

    # ── Train ─────────────────────────────────────────────────────────────────
    print(f"\nStarting training:")
    print(f"  Epochs          : {args.epochs}")
    print(f"  Train records   : {len(train_records)}")
    print(f"  Batch size      : {BATCH_SIZE}")
    print(f"  Grad accumulation: {GRAD_ACCUM}  (effective batch={BATCH_SIZE*GRAD_ACCUM})")
    print(f"  Max seq length  : {MAX_SEQ_LEN}")
    print(f"  LoRA rank       : {LORA_R}")
    print(f"  Learning rate   : {LR}")
    print(f"  Adapter dir     : {args.adapter_dir}\n")

    t_start = time.time()
    result  = train(train_records, val_records, tokenizer, model,
                    args.epochs, args.save_steps, args.adapter_dir)
    elapsed = time.time() - t_start

    print(f"\nTraining complete in {elapsed/60:.1f} minutes")
    if result["train_log"]:
        first_loss = result["train_log"][0]["loss"]
        last_loss  = result["train_log"][-1]["loss"]
        improved   = last_loss < first_loss
        print(f"Loss: {first_loss:.4f} → {last_loss:.4f}  "
              f"{'✓ decreased' if improved else '⚠ did not decrease — check data'}")

    # ── Save experiment log ───────────────────────────────────────────────────
    save_experiment_log({
        "phase":         "lora_training",
        "model":         args.model,
        "train_records": len(train_records),
        "epochs":        args.epochs,
        "lora_r":        LORA_R,
        "lora_alpha":    LORA_ALPHA,
        "max_seq_len":   MAX_SEQ_LEN,
        "lr":            LR,
        "elapsed_min":   round(elapsed/60, 1),
        "final_loss":    result["train_log"][-1]["loss"] if result["train_log"] else None,
        "best_val_loss": result["best_val_loss"] if result["best_val_loss"] < 1e9 else None,
        "adapter_dir":   args.adapter_dir,
    })

    print(f"\n  Next: python scripts/06_evaluate_lora.py")


if __name__ == "__main__":
    main()
