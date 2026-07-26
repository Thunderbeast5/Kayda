# Legal IPC Model — CPU LoRA Fine-tuning Pipeline

Fine-tunes `Qwen/Qwen2-0.5B-Instruct` on Indian Supreme Court cases to predict
IPC/BNS sections. Fully CPU-compatible. Exports to GGUF for Ollama inference.

---

## Machine Requirements

| Component | Minimum | Your machine |
|-----------|---------|--------------|
| RAM | 8 GB | 16.8 GB ✓ |
| CPU | Any x86-64 | Intel i7-13th gen ✓ |
| Disk | 5 GB free | — |
| GPU | Not required | CPU only ✓ |

---

## Pipeline Overview

```
sample_dataset/ (3 files)  OR  data/raw/ (26k files)
          │
          ▼
01_validate_dataset.py     ← Check JSON quality, section counts
          │
          ▼
02_prepare_dataset.py      ← Build train/val/test JSONL splits
          │
          ▼
03_analyze_dataset.py      ← Inspect lengths, leakage, distribution
          │
          ▼
04_test_base_model.py      ← Baseline metrics (untuned model)
          │
          ▼
05_train_lora_cpu.py       ← LoRA fine-tuning on CPU
          │
          ▼
06_evaluate_lora.py        ← Compare fine-tuned vs baseline
          │
          ▼
07_merge_lora.py           ← Merge adapter into base model
          │
          ▼
08_convert_gguf.py         ← Convert to GGUF (needs llama.cpp)
          │
          ▼
09_test_gguf.py            ← Sanity check GGUF
          │
          ▼
10_build_ollama.py         ← Register trained model in Ollama
          │
          ▼
11_predict.py              ← Interactive / batch inference
```

---

## Quick Start — From Scratch

### Step 0: Setup (run once)

```cmd
cd d:\khete\mootcourt\legal_ipc_model

python -m venv venv_cpu
venv_cpu\Scripts\pip install -r requirements.txt
```

### Step 1: Validate data

```cmd
:: Sample (3 files — for testing)
venv_cpu\Scripts\python scripts\01_validate_dataset.py --data_dir sample_dataset

:: Full 26k files
venv_cpu\Scripts\python scripts\01_validate_dataset.py --data_dir data/raw
```

### Step 2: Prepare dataset

```cmd
venv_cpu\Scripts\python scripts\02_prepare_dataset.py --data_dir sample_dataset
```

### Step 3: Analyze dataset

```cmd
venv_cpu\Scripts\python scripts\03_analyze_dataset.py
```

### Step 4: Baseline (optional but recommended)

Downloads Qwen2-0.5B (~850 MB, first run only):
```cmd
venv_cpu\Scripts\python scripts\04_test_base_model.py
```

### Step 5: Smoke test training (verify pipeline — ~5 min)

```cmd
venv_cpu\Scripts\python scripts\05_train_lora_cpu.py --limit 1 --epochs 1
```

You should see:
```
Trainable params: 884,736 / 494,917,504 (0.18%)
Epoch 1  Step    1  loss=X.XXXX
Final adapter saved → models/adapters/legal-ipc-lora/final
```

### Step 6: Real training

After smoke test passes, train with more data:

```cmd
:: 100-example experiment (~10 min on CPU)
venv_cpu\Scripts\python scripts\05_train_lora_cpu.py --limit 100 --epochs 1

:: 1000-example experiment (~2 hours on CPU)
venv_cpu\Scripts\python scripts\05_train_lora_cpu.py --limit 1000 --epochs 2

:: Full dataset (run overnight)
venv_cpu\Scripts\python scripts\05_train_lora_cpu.py --epochs 3
```

### Step 7: Evaluate

```cmd
venv_cpu\Scripts\python scripts\06_evaluate_lora.py
```

### Step 8: Merge + Convert + Deploy to Ollama

```cmd
venv_cpu\Scripts\python scripts\07_merge_lora.py
venv_cpu\Scripts\python scripts\08_convert_gguf.py
venv_cpu\Scripts\python scripts\09_test_gguf.py
venv_cpu\Scripts\python scripts\10_build_ollama.py
```

### Step 9: Predict

```cmd
:: Interactive
venv_cpu\Scripts\python scripts\11_predict.py --interactive

:: Single query
venv_cpu\Scripts\python scripts\11_predict.py --text "A man raped a woman and threatened her."
```

---

## Resume After Interruption

Training saves checkpoints every 50 steps. To resume:

```cmd
venv_cpu\Scripts\python scripts\05_train_lora_cpu.py --resume models/adapters/legal-ipc-lora/checkpoints/step-000050
```

---

## Training Time Estimates (CPU, Intel i7-13th gen)

| Examples | Epochs | Est. Time |
|----------|--------|-----------|
| 1 (smoke test) | 1 | ~30 sec |
| 100 | 1 | ~10 min |
| 1,000 | 1 | ~2 hours |
| 5,000 | 2 | ~20 hours |
| 26,000 | 3 | ~4 days |

> Tip: Train overnight with 1,000–5,000 examples first. Evaluate. Only proceed to full training if results improve over baseline.

---

## Project Structure

```
legal_ipc_model/
├── README.md
├── requirements.txt            ← Install with: pip install -r requirements.txt
├── .gitignore
│
├── scripts/
│   ├── 01_validate_dataset.py
│   ├── 02_prepare_dataset.py
│   ├── 03_analyze_dataset.py
│   ├── 04_test_base_model.py
│   ├── 05_train_lora_cpu.py    ← Main training script
│   ├── 06_evaluate_lora.py
│   ├── 07_merge_lora.py
│   ├── 08_convert_gguf.py
│   ├── 09_test_gguf.py
│   ├── 10_build_ollama.py
│   └── 11_predict.py
│
├── sample_dataset/             ← 3 sample JSON files
├── data/
│   ├── raw/                    ← PUT 26,000 JSON FILES HERE
│   └── processed/
│       ├── train/dataset.jsonl
│       ├── val/dataset.jsonl
│       └── test/dataset.jsonl
│
├── models/
│   ├── adapters/legal-ipc-lora/  ← LoRA adapter (saved by script 05)
│   │   ├── best/
│   │   ├── final/
│   │   └── checkpoints/
│   ├── merged/legal-ipc/         ← Merged model (script 07)
│   └── gguf/                     ← GGUF files (script 08)
│
├── logs/
│   ├── validation_report.json
│   ├── baseline_results.json
│   ├── lora_eval_results.json
│   └── training_log.jsonl
│
└── venv_cpu/                   ← Virtual environment
```

---

## Troubleshooting

**"torch_dtype is deprecated"** — harmless warning, ignore it.

**symlinks warning on Windows** — harmless, models still download fine.

**"loss did not decrease" with --limit 1** — expected, smoke test only uses 1 example.

**Out of memory** — reduce `--limit` or set `MAX_SEQ_LEN=256` in `05_train_lora_cpu.py`.

**Training too slow** — reduce `--limit`. With 16 GB RAM, 1000 examples x 1 epoch is the sweet spot before touching the full dataset.
