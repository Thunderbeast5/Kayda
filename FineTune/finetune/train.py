"""
Phase 4 — QLoRA fine-tuning of Gemma-2B on anticipatory bail dataset.

Run:
    python finetune/train.py                    # full training run
    python finetune/train.py --dry-run          # verify setup without training
    python finetune/train.py --resume           # resume from last checkpoint

Requirements (install first):
    pip install -r requirements_training.txt

Memory budget on RTX 2050 (4GB VRAM):
    Model (4-bit quantized):  ~1.5 GB
    LoRA adapters:            ~0.1 GB
    Activations (grad_ckpt):  ~0.8 GB
    Optimizer (paged 8-bit):  ~0.5 GB (spills to RAM)
    Total:                    ~3.0 GB  (0.9 GB headroom)
"""

import argparse
import gc
import logging
import os
import sys
from pathlib import Path

# ── Redirect HuggingFace cache to D: drive before any HF import ───────────────
_hf_cache = Path("D:/hf_cache")
_hf_cache.mkdir(parents=True, exist_ok=True)
os.environ["HF_HOME"] = str(_hf_cache)
# ──────────────────────────────────────────────────────────────────────────────

# Add parent to path so finetune/ imports work
sys.path.insert(0, str(Path(__file__).parent.parent))

logger = logging.getLogger(__name__)


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
    )


def check_imports() -> bool:
    """Verify all required packages are installed before attempting to load model."""
    missing = []
    for pkg in ["torch", "transformers", "peft", "trl", "bitsandbytes", "accelerate"]:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)

    if missing:
        logger.error(
            f"Missing packages: {missing}\n"
            f"Run: pip install -r requirements_training.txt"
        )
        return False
    return True


def check_gpu() -> dict:
    """Report GPU status and return memory info."""
    import torch
    info = {
        "cuda_available": torch.cuda.is_available(),
        "device_name": None,
        "vram_total_gb": 0,
        "vram_free_gb": 0,
    }
    if torch.cuda.is_available():
        info["device_name"] = torch.cuda.get_device_name(0)
        total = torch.cuda.get_device_properties(0).total_memory
        free  = torch.cuda.memory_reserved(0)
        info["vram_total_gb"] = round(total / 1e9, 2)
        info["vram_free_gb"]  = round((total - free) / 1e9, 2)
        logger.info(
            f"GPU: {info['device_name']} | "
            f"VRAM: {info['vram_total_gb']} GB total, "
            f"{info['vram_free_gb']} GB free"
        )
    else:
        logger.warning(
            "CUDA not available — training will run on CPU. "
            "This will be extremely slow (~50x slower than GPU). "
            "On CPU, 4-bit quantization is not supported; "
            "the model will load in float32."
        )
    return info


def load_model_and_tokenizer(model_id: str, bnb_config_args: dict, device_map: str = "auto"):
    """
    Load Gemma-2B with 4-bit NF4 quantization.
    Falls back to CPU float32 if CUDA is not available (for testing only).
    """
    import torch
    from transformers import (
        AutoModelForCausalLM,
        AutoTokenizer,
        BitsAndBytesConfig,
    )

    logger.info(f"Loading tokenizer: {model_id}")
    tokenizer = AutoTokenizer.from_pretrained(
        model_id,
        trust_remote_code=True,
        padding_side="right",   # Right padding for causal LM
    )
    # Gemma tokenizer doesn't always have a pad token — set it
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
        logger.info("Set pad_token = eos_token")

    if torch.cuda.is_available():
        logger.info("Loading model with 4-bit NF4 quantization...")
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=bnb_config_args["load_in_4bit"],
            bnb_4bit_quant_type=bnb_config_args["bnb_4bit_quant_type"],
            bnb_4bit_use_double_quant=bnb_config_args["bnb_4bit_use_double_quant"],
            bnb_4bit_compute_dtype=getattr(torch, bnb_config_args["bnb_4bit_compute_dtype"]),
        )
        model = AutoModelForCausalLM.from_pretrained(
            model_id,
            quantization_config=bnb_config,
            device_map=device_map,
            trust_remote_code=True,
            attn_implementation="eager",   # Gemma-2B doesn't support flash_attention_2
        )
    else:
        logger.warning("Loading model in float32 (CPU mode — training not recommended)")
        model = AutoModelForCausalLM.from_pretrained(
            model_id,
            torch_dtype=torch.float32,
            device_map="cpu",
            trust_remote_code=True,
        )

    model.config.use_cache = False
    # Disable KV cache during training — incompatible with gradient checkpointing
    model.config.pretraining_tp = 1
    # Required for Gemma compatibility with PEFT

    logger.info(
        f"Model loaded | "
        f"Params: {sum(p.numel() for p in model.parameters()) / 1e6:.0f}M"
    )
    return model, tokenizer


def apply_lora(model, lora_config_args: dict):
    """Wrap the quantized model with LoRA adapters using PEFT."""
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training

    logger.info("Preparing model for k-bit training...")
    # prepare_model_for_kbit_training:
    # 1. Casts LayerNorm layers to float32 (stability with 4-bit base)
    # 2. Enables gradient checkpointing
    # 3. Ensures input embeddings require gradients
    model = prepare_model_for_kbit_training(
        model,
        use_gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
        # use_reentrant=False: newer, more memory-efficient implementation
    )

    lora_config = LoraConfig(
        r=lora_config_args["r"],
        lora_alpha=lora_config_args["lora_alpha"],
        lora_dropout=lora_config_args["lora_dropout"],
        bias=lora_config_args["bias"],
        task_type=lora_config_args["task_type"],
        target_modules=lora_config_args["target_modules"],
    )

    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()
    # Expected output: ~1.5% trainable params (LoRA adapters only)

    return model


def build_trainer(model, tokenizer, train_ds, val_ds, training_config, output_dir: Path):
    """Build the SFTTrainer (Supervised Fine-Tuning Trainer from TRL)."""
    from trl import SFTConfig, SFTTrainer, DataCollatorForCompletionOnlyLM

    # DataCollatorForCompletionOnlyLM masks instruction/input tokens in the loss.
    # Only the model's *response* tokens contribute to training loss.
    # Gemma-2B token IDs for "<start_of_turn>model\n":
    #   106 = <start_of_turn>
    #   1516 = "model"
    #   108 = "\n"
    # Using token IDs directly avoids string-matching issues with special tokens.
    response_template_ids = tokenizer.encode(
        "<start_of_turn>model\n",
        add_special_tokens=False,
    )
    logger.info(f"Response template token IDs: {response_template_ids}")
    collator = DataCollatorForCompletionOnlyLM(
        response_template=response_template_ids,
        tokenizer=tokenizer,
        mlm=False,
    )

    # trl 0.10+ uses SFTConfig which inherits from TrainingArguments
    sft_config = SFTConfig(
        output_dir=str(output_dir),
        per_device_train_batch_size=training_config.per_device_train_batch_size,
        gradient_accumulation_steps=training_config.gradient_accumulation_steps,
        learning_rate=training_config.learning_rate,
        lr_scheduler_type=training_config.lr_scheduler_type,
        warmup_ratio=training_config.warmup_ratio,
        num_train_epochs=training_config.num_train_epochs,
        eval_strategy=training_config.eval_strategy,
        eval_steps=training_config.eval_steps,
        save_strategy=training_config.save_strategy,
        save_steps=training_config.save_steps,
        save_total_limit=training_config.save_total_limit,
        load_best_model_at_end=training_config.load_best_model_at_end,
        metric_for_best_model=training_config.metric_for_best_model,
        greater_is_better=training_config.greater_is_better,
        optim=training_config.optim,
        bf16=training_config.bf16,
        fp16=training_config.fp16,
        logging_steps=training_config.logging_steps,
        report_to=training_config.report_to,
        run_name=training_config.run_name,
        dataloader_num_workers=training_config.dataloader_num_workers,
        remove_unused_columns=training_config.remove_unused_columns,
        gradient_checkpointing=training_config.gradient_checkpointing,
        gradient_checkpointing_kwargs={"use_reentrant": False},
        max_grad_norm=training_config.max_grad_norm,
        seed=training_config.seed,
        group_by_length=True,
        # SFT-specific: tell SFTTrainer the data is already tokenized
        dataset_kwargs={"skip_prepare_dataset": True},
        max_seq_length=768,
    )

    trainer = SFTTrainer(
        model=model,
        args=sft_config,
        train_dataset=train_ds,
        eval_dataset=val_ds,
        data_collator=collator,
        tokenizer=tokenizer,
    )

    return trainer


def save_lora_adapter(trainer, output_dir: Path) -> None:
    """Save only the LoRA adapter weights (not the full model)."""
    output_dir.mkdir(parents=True, exist_ok=True)
    trainer.model.save_pretrained(str(output_dir))
    trainer.tokenizer.save_pretrained(str(output_dir))  # type: ignore[attr-defined]
    logger.info(f"LoRA adapter saved → {output_dir}")
    logger.info(
        "To use for inference, merge the adapter with the base model "
        "using: python finetune/merge_and_export.py"
    )


def dry_run_check(model_id: str, train_path: Path, val_path: Path, max_seq: int) -> None:
    """Quick sanity check: load tokenizer, tokenize first 5 examples, report stats."""
    from transformers import AutoTokenizer

    logger.info("=== DRY RUN — checking setup without loading full model ===")
    tokenizer = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    from finetune.config import PROMPT_TEMPLATE
    from finetune.dataset import format_prompt

    import json
    pairs = []
    with open(train_path, encoding="utf-8") as f:
        for i, line in enumerate(f):
            if i >= 20:
                break
            pairs.append(json.loads(line.strip()))

    lengths = []
    for p in pairs:
        prompt = format_prompt(p["instruction"], p.get("input", ""), p["output"], PROMPT_TEMPLATE)
        toks = tokenizer(prompt, return_tensors=None)
        lengths.append(len(toks["input_ids"]))

    logger.info(f"Tokenizer: {tokenizer.__class__.__name__}, vocab={tokenizer.vocab_size}")
    logger.info(f"First 20 examples: min={min(lengths)} max={max(lengths)} avg={sum(lengths)//len(lengths)} tokens")
    logger.info(f"Max sequence length set to: {max_seq}")
    over = sum(1 for l in lengths if l > max_seq)
    logger.info(f"Examples over max_seq in sample: {over}/20")

    # Check output files will exist
    for path in [train_path, val_path]:
        count = sum(1 for _ in open(path, encoding="utf-8"))
        logger.info(f"  {path.name}: {count} lines")

    logger.info("Dry run complete — no model loaded, no training done.")
    logger.info(
        "Next step: run without --dry-run. "
        "First run will download Gemma-2B (~5GB) from HuggingFace."
    )


def main() -> None:
    setup_logging()

    parser = argparse.ArgumentParser(description="QLoRA fine-tune Gemma-2B on bail dataset")
    parser.add_argument("--dry-run", action="store_true",
                        help="Check setup without downloading model or training")
    parser.add_argument("--resume", action="store_true",
                        help="Resume from last checkpoint in output directory")
    parser.add_argument("--epochs", type=int, default=None,
                        help="Override number of epochs from config")
    args = parser.parse_args()

    from finetune.config import (
        MODEL_ID, BNB, LORA, TRAINING, MAX_SEQ_LENGTH,
        MODEL_OUTPUT_DIR, LOGS_DIR,
        TRAIN_FILE, VAL_FILE,
        PROMPT_TEMPLATE,
    )

    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    MODEL_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.epochs:
        TRAINING.num_train_epochs = args.epochs

    # ── Dry run ────────────────────────────────────────────────────────────
    if args.dry_run:
        dry_run_check(MODEL_ID, TRAIN_FILE, VAL_FILE, MAX_SEQ_LENGTH)
        return

    # ── Import checks ──────────────────────────────────────────────────────
    if not check_imports():
        sys.exit(1)

    gpu_info = check_gpu()

    # ── Load model ─────────────────────────────────────────────────────────
    bnb_config_args = {
        "load_in_4bit": BNB.load_in_4bit,
        "bnb_4bit_quant_type": BNB.bnb_4bit_quant_type,
        "bnb_4bit_use_double_quant": BNB.bnb_4bit_use_double_quant,
        "bnb_4bit_compute_dtype": BNB.bnb_4bit_compute_dtype,
    }

    model, tokenizer = load_model_and_tokenizer(MODEL_ID, bnb_config_args)

    # ── Apply LoRA ─────────────────────────────────────────────────────────
    lora_config_args = {
        "r": LORA.r,
        "lora_alpha": LORA.lora_alpha,
        "lora_dropout": LORA.lora_dropout,
        "bias": LORA.bias,
        "task_type": LORA.task_type,
        "target_modules": LORA.target_modules,
    }
    model = apply_lora(model, lora_config_args)

    # ── Build datasets ─────────────────────────────────────────────────────
    from finetune.dataset import build_datasets
    train_ds, val_ds = build_datasets(
        tokenizer, PROMPT_TEMPLATE, TRAIN_FILE, VAL_FILE, MAX_SEQ_LENGTH
    )

    logger.info(
        f"Training: {len(train_ds)} examples | "
        f"Validation: {len(val_ds)} examples"
    )

    # ── Build trainer ──────────────────────────────────────────────────────
    trainer = build_trainer(model, tokenizer, train_ds, val_ds, TRAINING, MODEL_OUTPUT_DIR)

    # ── Train ──────────────────────────────────────────────────────────────
    logger.info("Starting training...")
    logger.info(
        f"  Model:        {MODEL_ID}\n"
        f"  LoRA rank:    {LORA.r}\n"
        f"  Seq length:   {MAX_SEQ_LENGTH}\n"
        f"  Epochs:       {TRAINING.num_train_epochs}\n"
        f"  Batch size:   {TRAINING.per_device_train_batch_size} "
        f"× grad_accum {TRAINING.gradient_accumulation_steps} "
        f"= effective {TRAINING.per_device_train_batch_size * TRAINING.gradient_accumulation_steps}\n"
        f"  LR:           {TRAINING.learning_rate}\n"
        f"  Output:       {MODEL_OUTPUT_DIR}"
    )

    resume_from = str(MODEL_OUTPUT_DIR) if args.resume else None
    train_result = trainer.train(resume_from_checkpoint=resume_from)

    # ── Save ───────────────────────────────────────────────────────────────
    save_lora_adapter(trainer, MODEL_OUTPUT_DIR / "final_adapter")

    # Log training summary
    metrics = train_result.metrics
    trainer.log_metrics("train", metrics)
    trainer.save_metrics("train", metrics)

    logger.info("Training complete.")
    logger.info(f"Best checkpoint: {MODEL_OUTPUT_DIR}")

    # Free memory
    del model, trainer
    gc.collect()
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass


if __name__ == "__main__":
    main()
