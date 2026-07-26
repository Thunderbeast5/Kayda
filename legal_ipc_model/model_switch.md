# Switching to Gemma-3-4B for Fine-tuning

## Important distinction

| Context | Model name |
|---------|-----------|
| Ollama (inference) | `gemma3:4b` |
| HuggingFace (fine-tuning) | `google/gemma-3-4b-it` |

You fine-tune using the HuggingFace weights.
After fine-tuning you convert to GGUF and load it in Ollama.

---

## Server requirements for Gemma-3-4B

| Resource | Required |
|----------|----------|
| RAM | 16 GB minimum (32 GB recommended) |
| VRAM | 10 GB (with QLoRA 4-bit) |
| Disk | 15 GB free |
| Python | 3.10+ |

---

## Step 1 — Accept Gemma license on HuggingFace

Gemma is a gated model. You must accept the license before downloading.

1. Go to: https://huggingface.co/google/gemma-3-4b-it
2. Click **"Access repository"** and accept the terms
3. Login from your server terminal:

```bash
huggingface-cli login
# Paste your HuggingFace token (from https://huggingface.co/settings/tokens)
```

---

## Step 2 — Change 4 files (exact lines)

### File 1: `scripts/05_train_lora_cpu.py`

```python
# LINE 18 — change BASE_MODEL:
# FROM:
BASE_MODEL = "Qwen/Qwen2-0.5B-Instruct"
# TO:
BASE_MODEL = "google/gemma-3-4b-it"

# LINE 24 — change TARGET_MODULES:
# FROM:
TARGET_MODULES = ["q_proj", "v_proj", "o_proj"]
# TO:
TARGET_MODULES = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]
```

### File 2: `scripts/04_test_base_model.py`

```python
# LINE 9 — change BASE_MODEL:
# FROM:
BASE_MODEL = "Qwen/Qwen2-0.5B-Instruct"
# TO:
BASE_MODEL = "google/gemma-3-4b-it"
```

### File 3: `scripts/06_evaluate_lora.py`

```python
# LINE 10 — change BASE_MODEL:
# FROM:
BASE_MODEL = "Qwen/Qwen2-0.5B-Instruct"
# TO:
BASE_MODEL = "google/gemma-3-4b-it"
```

### File 4: `scripts/07_merge_lora.py`

```python
# LINE 8 — change BASE_MODEL:
# FROM:
BASE_MODEL = "Qwen/Qwen2-0.5B-Instruct"
# TO:
BASE_MODEL = "google/gemma-3-4b-it"
```

---

## Step 3 — Change the prompt format

Gemma-3 uses a different chat template than Qwen2.

In `scripts/05_train_lora_cpu.py`, the `format_prompt` function already uses
`tokenizer.apply_chat_template()` — this auto-detects Gemma's format.
**No change needed here** — it works automatically.

But in `scripts/11_predict.py`, update the Ollama model name:

```python
# LINE 13 — change DEFAULT_MODEL:
# FROM:
DEFAULT_MODEL = "legal-ipc-trained"
# TO:
DEFAULT_MODEL = "gemma3-legal"   # or whatever name you use in step 10
```

---

## Step 4 — Add bitsandbytes for GPU training (server only)

On the Ubuntu server with GPU, install:

```bash
pip install bitsandbytes>=0.43.0
```

Then in `scripts/05_train_lora_cpu.py`, replace the model loading block
(around line 145) with QLoRA 4-bit for GPU:

```python
# REPLACE THIS (CPU version):
model = AutoModelForCausalLM.from_pretrained(
    args.model,
    torch_dtype    = torch.float32,
    trust_remote_code = True,
)

# WITH THIS (GPU + 4-bit QLoRA):
from transformers import BitsAndBytesConfig
bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_use_double_quant=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.bfloat16,
)
model = AutoModelForCausalLM.from_pretrained(
    args.model,
    quantization_config = bnb_config,
    device_map          = "auto",
    torch_dtype         = torch.bfloat16,
    trust_remote_code   = True,
    attn_implementation = "eager",
)
```

Also change the training arguments for GPU speed:

```python
# In the train() function, change:
optimizer = AdamW(...)

# To paged optimizer (better for GPU):
from transformers import Adafactor
optimizer = Adafactor(
    [p for p in model.parameters() if p.requires_grad],
    lr=LR, relative_step=False, scale_parameter=False
)
```

---

## Step 5 — Run pipeline on server

After making the changes above:

```bash
# On Ubuntu server
source venv_cpu/bin/activate

# Steps 1-3 don't change — data prep is model-independent
python scripts/01_validate_dataset.py --data_dir data/raw
python scripts/02_prepare_dataset.py  --data_dir data/raw
python scripts/03_analyze_dataset.py

# Step 4 baseline with Gemma-3-4B
python scripts/04_test_base_model.py --limit 100

# Step 5 train with Gemma-3-4B
# Start with 1000 examples (~1 hour with GPU, ~20 hours CPU)
python scripts/05_train_lora_cpu.py --limit 1000 --epochs 3

# Step 6 evaluate
python scripts/06_evaluate_lora.py

# Steps 7-8 merge and convert
python scripts/07_merge_lora.py
python scripts/08_convert_gguf.py --skip_clone

# Step 10 register in Ollama with a different name
python scripts/10_build_ollama.py --model_name gemma3-legal

# Step 11 predict
python scripts/11_predict.py --model gemma3-legal --interactive
```

---

## Step 6 — After GGUF, load in Ollama

The `10_build_ollama.py` script does this automatically.
But if you want to do it manually:

```bash
# Create Modelfile
cat > Modelfile << 'EOF'
FROM ./models/gguf/legal-ipc-Q4_K_M.gguf

SYSTEM """You are a legal classification model trained on Indian Supreme Court judgments.
When given case facts, identify the applicable IPC sections and BNS 2023 equivalents.
Always respond in this exact format:
IPC Sections: [comma-separated section numbers]
BNS Equivalents: [comma-separated BNS numbers]"""

PARAMETER temperature 0.1
PARAMETER num_ctx 2048
EOF

# Register
ollama create gemma3-legal -f Modelfile

# Test directly
ollama run gemma3-legal "A man broke into a house and committed rape."
```

---

## Summary of all changes for Gemma-3-4B

| File | Line | From | To |
|------|------|------|----|
| `scripts/05_train_lora_cpu.py` | 18 | `Qwen/Qwen2-0.5B-Instruct` | `google/gemma-3-4b-it` |
| `scripts/05_train_lora_cpu.py` | 24 | `["q_proj", "v_proj", "o_proj"]` | `["q_proj","k_proj","v_proj","o_proj","gate_proj","up_proj","down_proj"]` |
| `scripts/04_test_base_model.py` | 9 | `Qwen/Qwen2-0.5B-Instruct` | `google/gemma-3-4b-it` |
| `scripts/06_evaluate_lora.py` | 10 | `Qwen/Qwen2-0.5B-Instruct` | `google/gemma-3-4b-it` |
| `scripts/07_merge_lora.py` | 8 | `Qwen/Qwen2-0.5B-Instruct` | `google/gemma-3-4b-it` |
| `scripts/11_predict.py` | 13 | `legal-ipc-trained` | `gemma3-legal` |
| Model loading block | ~145 | float32 CPU | bfloat16 GPU + QLoRA (server only) |

**Total: 6 line changes + 1 block replacement for GPU.**

Data preparation scripts (01, 02, 03, 08, 09) need zero changes.
