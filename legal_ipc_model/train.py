"""
train.py — Step 2: Fine-tune the LLM on the prepared dataset.

Usage (on Ubuntu server with GPU):
    python train.py
    python train.py --model meta-llama/Meta-Llama-3-8B-Instruct --epochs 5
    python train.py --data_dir data/processed --output_dir models/legal_model

Environment variables:
    WANDB_API_KEY=<your_key>   (optional, for W&B logging)
    HF_TOKEN=<your_key>        (required for gated models like Llama-3)
"""
import argparse
import json
import os
import sys
sys.path.insert(0, "src")

from utils.logger_setup import setup_logger
from model.trainer import LegalModelTrainer

logger = setup_logger()


def load_jsonl(path: str) -> list:
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def main():
    parser = argparse.ArgumentParser(description="Fine-tune legal IPC model")
    parser.add_argument("--model",
                        default="mistralai/Mistral-7B-Instruct-v0.2",
                        help="Base model HuggingFace ID")
    parser.add_argument("--data_dir",   default="data/processed")
    parser.add_argument("--output_dir", default="models/legal_model")
    parser.add_argument("--epochs",     type=int,   default=3)
    parser.add_argument("--batch_size", type=int,   default=2)
    parser.add_argument("--grad_accum", type=int,   default=8,
                        help="Gradient accumulation steps (effective batch = batch*accum)")
    parser.add_argument("--lr",         type=float, default=2e-4)
    parser.add_argument("--wandb",      action="store_true",
                        help="Enable Weights & Biases logging")
    args = parser.parse_args()

    # ── Load data ─────────────────────────────────────────────────────────────
    train_path = f"{args.data_dir}/train/dataset.jsonl"
    val_path   = f"{args.data_dir}/val/dataset.jsonl"

    if not os.path.exists(train_path):
        logger.error(f"Train data not found: {train_path}")
        logger.error("Run prepare_data.py first.")
        sys.exit(1)

    logger.info(f"Loading training data from {train_path}")
    train_records = load_jsonl(train_path)

    val_records = []
    if os.path.exists(val_path):
        val_records = load_jsonl(val_path)
        logger.info(f"Loaded {len(val_records)} validation records")

    logger.info(f"Train records: {len(train_records)}")

    # ── Init trainer ──────────────────────────────────────────────────────────
    logger.info("=== Initializing Trainer ===")
    trainer = LegalModelTrainer(
        base_model  = args.model,
        output_dir  = args.output_dir,
        use_wandb   = args.wandb,
    )
    trainer.load_model_and_tokenizer()

    # ── Train ─────────────────────────────────────────────────────────────────
    logger.info("=== Starting Training ===")
    logger.info(f"  Model      : {args.model}")
    logger.info(f"  Epochs     : {args.epochs}")
    logger.info(f"  Batch size : {args.batch_size}")
    logger.info(f"  Grad accum : {args.grad_accum}")
    logger.info(f"  LR         : {args.lr}")
    logger.info(f"  Output     : {args.output_dir}")

    trainer.train(
        train_records = train_records,
        val_records   = val_records,
        num_epochs    = args.epochs,
        batch_size    = args.batch_size,
        grad_accum    = args.grad_accum,
        lr            = args.lr,
    )

    logger.info("Training complete. Run evaluate.py to assess performance.")


if __name__ == "__main__":
    main()
