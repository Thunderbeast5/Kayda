"""
trainer.py
Fine-tunes Mistral-7B-Instruct-v0.2 on the legal dataset using QLoRA + SFTTrainer.
Designed for Ubuntu server with NVIDIA GPU.
"""
import os
import json
import torch
from pathlib import Path
from typing import List, Dict
from loguru import logger

from transformers import (
    AutoTokenizer,
    AutoModelForCausalLM,
    BitsAndBytesConfig,
    TrainingArguments,
)
from peft import LoraConfig, TaskType, get_peft_model, prepare_model_for_kbit_training
from trl import SFTTrainer, DataCollatorForCompletionOnlyLM
from datasets import Dataset


# ── Config ────────────────────────────────────────────────────────────────────
BASE_MODEL   = "mistralai/Mistral-7B-Instruct-v0.2"   # change to llama3 if preferred
MAX_SEQ_LEN  = 2048
OUTPUT_DIR   = "models/legal_model"
LORA_RANK    = 32
LORA_ALPHA   = 64
LORA_DROPOUT = 0.1

# Mistral chat template tokens
RESPONSE_TEMPLATE = "[/INST]"
INSTRUCTION_TEMPLATE = "[INST]"


def format_prompt(example: Dict) -> str:
    """Convert instruction/input/output to Mistral instruct format."""
    instruction = example.get("instruction", "")
    input_text  = example.get("input", "")
    output      = example.get("output", "")

    if input_text:
        user_msg = f"{instruction}\n\n{input_text}"
    else:
        user_msg = instruction

    return (
        f"<s>[INST] {user_msg} [/INST] "
        f"{output} </s>"
    )


class LegalModelTrainer:
    def __init__(self,
                 base_model: str   = BASE_MODEL,
                 output_dir: str   = OUTPUT_DIR,
                 use_wandb: bool   = False):
        self.base_model  = base_model
        self.output_dir  = Path(output_dir)
        self.use_wandb   = use_wandb
        self.device      = "cuda" if torch.cuda.is_available() else "cpu"

        logger.info(f"Device: {self.device}")
        logger.info(f"Base model: {self.base_model}")
        logger.info(f"Output dir: {self.output_dir}")

        if self.device == "cpu":
            logger.warning(
                "No GPU detected. Training on CPU will be extremely slow. "
                "Run this on the Ubuntu server with GPU."
            )

    # ── Load model ────────────────────────────────────────────────────────────

    def load_model_and_tokenizer(self):
        logger.info("Loading tokenizer...")
        self.tokenizer = AutoTokenizer.from_pretrained(
            self.base_model,
            trust_remote_code=True,
            padding_side="right",
        )
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token

        logger.info("Loading model with 4-bit quantization (QLoRA)...")
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_use_double_quant=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16,
        )

        self.model = AutoModelForCausalLM.from_pretrained(
            self.base_model,
            quantization_config=bnb_config,
            device_map="auto",
            trust_remote_code=True,
            torch_dtype=torch.bfloat16,
        )

        self.model = prepare_model_for_kbit_training(self.model)

        # Apply LoRA
        lora_cfg = LoraConfig(
            r=LORA_RANK,
            lora_alpha=LORA_ALPHA,
            lora_dropout=LORA_DROPOUT,
            bias="none",
            task_type=TaskType.CAUSAL_LM,
            target_modules=[
                "q_proj", "k_proj", "v_proj", "o_proj",
                "gate_proj", "up_proj", "down_proj",
            ],
        )
        self.model = get_peft_model(self.model, lora_cfg)
        self.model.print_trainable_parameters()

        return self.model, self.tokenizer

    # ── Prepare data ──────────────────────────────────────────────────────────

    def prepare_dataset(self, records: List[Dict]) -> Dataset:
        """Format records and convert to HuggingFace Dataset."""
        texts = [format_prompt(r) for r in records]
        return Dataset.from_dict({"text": texts})

    # ── Train ─────────────────────────────────────────────────────────────────

    def train(self,
              train_records: List[Dict],
              val_records:   List[Dict],
              num_epochs:    int   = 3,
              batch_size:    int   = 2,
              grad_accum:    int   = 8,
              lr:            float = 2e-4):

        self.output_dir.mkdir(parents=True, exist_ok=True)

        train_ds = self.prepare_dataset(train_records)
        val_ds   = self.prepare_dataset(val_records) if val_records else None

        report_to = ["wandb"] if self.use_wandb else ["tensorboard"]

        args = TrainingArguments(
            output_dir               = str(self.output_dir),
            num_train_epochs         = num_epochs,
            per_device_train_batch_size  = batch_size,
            per_device_eval_batch_size   = batch_size,
            gradient_accumulation_steps  = grad_accum,
            learning_rate            = lr,
            warmup_ratio             = 0.03,
            lr_scheduler_type        = "cosine",
            weight_decay             = 0.01,
            max_grad_norm            = 1.0,
            fp16                     = False,
            bf16                     = True,            # bfloat16 for A100/H100
            gradient_checkpointing   = True,
            optim                    = "paged_adamw_8bit",
            evaluation_strategy      = "steps" if val_ds else "no",
            eval_steps               = 200,
            save_strategy            = "steps",
            save_steps               = 200,
            save_total_limit         = 3,
            load_best_model_at_end   = bool(val_ds),
            logging_steps            = 20,
            report_to                = report_to,
            run_name                 = "legal_ipc_model",
            dataloader_num_workers   = 4,
            remove_unused_columns    = False,
        )

        trainer = SFTTrainer(
            model           = self.model,
            tokenizer       = self.tokenizer,
            args            = args,
            train_dataset   = train_ds,
            eval_dataset    = val_ds,
            max_seq_length  = MAX_SEQ_LEN,
            dataset_text_field = "text",
            packing         = True,   # efficient packing of short sequences
        )

        logger.info("Starting training...")
        trainer.train()

        # Save final adapter
        final_path = self.output_dir / "final"
        trainer.save_model(str(final_path))
        self.tokenizer.save_pretrained(str(final_path))
        logger.info(f"Model saved to {final_path}")

        return trainer
