"""
Training configuration for Gemma-2B QLoRA fine-tuning.

All hyperparameters are documented with their rationale.
Change ONLY the paths section if you move files around.
Everything else is tuned for: RTX 2050 (4GB VRAM) + 16GB RAM, 509 training pairs.
"""

from dataclasses import dataclass, field
from pathlib import Path


# ── Paths ──────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent.parent  # FineTune/

TRAIN_FILE   = BASE_DIR / "training_data" / "train.jsonl"
VAL_FILE     = BASE_DIR / "training_data" / "val.jsonl"
TEST_FILE    = BASE_DIR / "training_data" / "test.jsonl"

MODEL_OUTPUT_DIR   = BASE_DIR / "models" / "gemma2b-bail-lora"
MERGED_OUTPUT_DIR  = BASE_DIR / "models" / "gemma2b-bail-merged"
LOGS_DIR           = BASE_DIR / "logs"


# ── Model ──────────────────────────────────────────────────────────────────────
# Gemma-2B: smallest Gemma that has enough capacity for legal reasoning.
# Gemma-7B/9B require 8+ GB VRAM even with 4-bit — not viable on RTX 2050.
MODEL_ID = "google/gemma-2b-it"   # instruction-tuned base (better starting point than base)


# ── Quantization (BitsAndBytes 4-bit NF4) ─────────────────────────────────────
# NF4 (NormalFloat4) is the best 4-bit format for language models.
# load_in_4bit reduces VRAM from ~5GB (bf16) to ~1.5GB, leaving room for
# activations, LoRA adapters, and optimizer states.
@dataclass
class BnBConfig:
    load_in_4bit: bool = True
    bnb_4bit_quant_type: str = "nf4"          # NF4 > INT4 for LLMs
    bnb_4bit_use_double_quant: bool = True     # Double quantization: saves ~0.4 bits extra
    bnb_4bit_compute_dtype: str = "bfloat16"  # Compute in bf16 for numerical stability

BNB = BnBConfig()


# ── LoRA ───────────────────────────────────────────────────────────────────────
# QLoRA: train low-rank adapters on top of the frozen quantized model.
# Only ~0.5% of parameters are trained — this is why it fits in 4GB VRAM.
@dataclass
class LoRAConfig:
    r: int = 16
    # Rank = number of trainable dimensions per weight matrix.
    # r=16 is the sweet spot for a 509-example dataset:
    #   - r=8: too little capacity for legal vocabulary
    #   - r=32: overfits on 509 examples
    #   - r=16: good generalisation on narrow domain

    lora_alpha: int = 32
    # alpha controls the effective learning rate of the adapter.
    # Rule of thumb: alpha = 2*r. Higher alpha = stronger adaptation.
    # alpha=32 with r=16 means effective scaling = 32/16 = 2.0

    lora_dropout: float = 0.05
    # Small dropout prevents the adapter from memorising training examples.
    # 0.05 is standard for small datasets; increase to 0.1 if eval loss diverges.

    bias: str = "none"
    # Don't train bias terms — adds parameters without much benefit at this scale.

    task_type: str = "CAUSAL_LM"

    target_modules: list = field(default_factory=lambda: [
        "q_proj", "k_proj", "v_proj", "o_proj",   # attention projections
        "gate_proj", "up_proj", "down_proj",         # MLP projections
    ])
    # Apply LoRA to all projection layers (not just QV) for best accuracy.
    # On a 4GB card this still fits because the base model is frozen + quantized.

LORA = LoRAConfig()


# ── Sequence length ────────────────────────────────────────────────────────────
# p90 of training data is ~1100 tokens. Cap at 1024 to fit in VRAM.
# The ~10% of longer examples get truncated — acceptable tradeoff.
# Increasing to 2048 would require reducing batch size to 1 and may OOM.
MAX_SEQ_LENGTH = 768
# Reduced from 1024: RTX 2050 (4GB) OOMs at 1024 tokens even with batch=1.
# p75 of training data is ~680 tokens, so 768 covers the majority.
# ~15% of longer examples get truncated at 768 — acceptable for this dataset.


# ── Training hyperparameters ───────────────────────────────────────────────────
@dataclass
class TrainingConfig:
    # --- Batch and gradient accumulation ---
    per_device_train_batch_size: int = 1
    # Reduced from 2 to 1 — RTX 2050 (4GB) OOMs at batch=2 with 1024 token sequences.
    # Effective batch stays at 16 via gradient accumulation below.

    gradient_accumulation_steps: int = 16
    # Increased from 8 to 16 to maintain effective batch size of 16 (1 × 16 = 16).

    per_device_eval_batch_size: int = 1
    # Must be 1. Evaluation runs without gradient checkpointing, so full activations
    # are stored. On 4GB VRAM this OOMs at batch=2. Batch=1 is the safe maximum.

    # --- Learning rate schedule ---
    learning_rate: float = 2e-4

    lr_scheduler_type: str = "cosine"
    # Cosine decay: starts at learning_rate, decays smoothly to near-zero.
    # Better than linear for small datasets — prevents sharp loss spikes near end.

    warmup_ratio: float = 0.05
    # Warm up for 5% of steps before full learning rate.
    # Prevents early training instability on the legal vocabulary.

    # --- Epochs and evaluation ---
    num_train_epochs: int = 3
    # 3 epochs on 509 examples = ~96 gradient updates (with effective batch 16).
    # More epochs → overfitting. Fewer → underfitting.
    # Monitor val loss — stop early if it stops decreasing.

    eval_strategy: str = "steps"
    eval_steps: int = 25
    # Evaluate every 25 steps — gives ~4 eval checkpoints per epoch.
    # Frequent enough to catch overfitting early.

    save_strategy: str = "steps"
    save_steps: int = 25
    save_total_limit: int = 3
    # Keep only the 3 best checkpoints to save disk space.

    load_best_model_at_end: bool = True
    metric_for_best_model: str = "eval_loss"
    greater_is_better: bool = False

    # --- Optimiser ---
    optim: str = "paged_adamw_8bit"
    # paged_adamw_8bit: stores optimiser states in 8-bit + uses paging to CPU RAM.
    # This is the key technique that makes 4GB VRAM work — optimizer states are
    # the largest memory consumer during training, not the model weights.

    # --- Precision ---
    bf16: bool = True
    # bf16 (bfloat16) for computations — same range as fp32, less precision.
    # RTX 2050 supports bf16. If you see NaN loss, switch to fp16=True instead.
    fp16: bool = False

    # --- Logging ---
    logging_steps: int = 5
    report_to: str = "none"   # "wandb" if you want W&B tracking
    run_name: str = "gemma2b-bail-lora"

    # --- Misc ---
    dataloader_num_workers: int = 0
    # 0 on Windows — multi-process dataloading causes issues on Windows.

    remove_unused_columns: bool = False
    # Required when using custom dataset format.

    gradient_checkpointing: bool = True
    # Recompute activations during backward pass instead of storing them.
    # Saves ~40% VRAM at cost of ~20% slower training — essential for 4GB.

    max_grad_norm: float = 0.3
    # Gradient clipping: prevents exploding gradients on the legal text domain
    # which has long sequences and unusual vocabulary.

    seed: int = 42

TRAINING = TrainingConfig()


# ── Prompt template ────────────────────────────────────────────────────────────
# Gemma-2B-IT uses a specific chat template. Using it correctly is critical —
# the model was instruction-tuned with this exact format.
PROMPT_TEMPLATE = """<start_of_turn>user
{instruction}

Context:
{input}<end_of_turn>
<start_of_turn>model
{output}<end_of_turn>"""

PROMPT_TEMPLATE_INFERENCE = """<start_of_turn>user
{instruction}

Context:
{input}<end_of_turn>
<start_of_turn>model
"""
