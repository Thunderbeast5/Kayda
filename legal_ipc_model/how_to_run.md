# How to Run — Legal IPC Model (Complete Guide)

This guide takes you from zero to a working IPC section predictor,
step by step. No prior ML knowledge required.

---

## Table of Contents

1. [System Requirements](#1-system-requirements)
2. [Install Python](#2-install-python)
3. [Install Ollama](#3-install-ollama)
4. [Download the Project](#4-download-the-project)
5. [Create Virtual Environment](#5-create-virtual-environment)
6. [Install Dependencies](#6-install-dependencies)
7. [Set Up Your Dataset](#7-set-up-your-dataset)
8. [Change the Model](#8-change-the-model)
9. [Run the Pipeline — Step by Step](#9-run-the-pipeline--step-by-step)
10. [Give Queries / Predict](#10-give-queries--predict)
11. [Check Accuracy](#11-check-accuracy)
12. [Troubleshooting](#12-troubleshooting)

---

## 1. System Requirements

| Requirement | Minimum | Recommended |
|-------------|---------|-------------|
| OS | Windows 10 / Ubuntu 20.04 | Windows 11 / Ubuntu 22.04 |
| RAM | 8 GB | 16 GB |
| Disk space | 8 GB free | 15 GB free |
| Python | 3.10 | 3.12 |
| GPU | Not required | NVIDIA GPU (optional) |
| Internet | Required (first run) | — |

---

## 2. Install Python

**Check if Python is already installed:**
```cmd
python --version
```

If you see `Python 3.10.x` or higher, skip to step 3.

**If not installed — Windows:**
1. Go to https://python.org/downloads
2. Download Python 3.12 (Windows installer 64-bit)
3. Run the installer → **check "Add Python to PATH"** → Install
4. Restart your terminal and verify: `python --version`

**Ubuntu:**
```bash
sudo apt update
sudo apt install python3.12 python3.12-venv python3-pip
python3 --version
```

---

## 3. Install Ollama

Ollama is required to run the trained model for predictions.

**Windows:**
1. Go to https://ollama.ai
2. Click Download → Download for Windows
3. Run the installer
4. Open a new terminal and verify: `ollama --version`

**Ubuntu:**
```bash
curl -fsSL https://ollama.ai/install.sh | sh
ollama --version
```

**Pull the base model (llama3.1 — ~4.9 GB download, first time only):**
```cmd
ollama pull llama3.1:latest
```

**Start Ollama server (keep this running in a separate terminal window):**
```cmd
ollama serve
```

---

## 4. Download the Project

If you have the project folder already, navigate to it:
```cmd
cd d:\khete\mootcourt\legal_ipc_model
```

If cloning from git:
```cmd
git clone <your-repo-url>
cd legal_ipc_model
```

---

## 5. Create Virtual Environment

A virtual environment keeps project dependencies isolated from your system Python.

**Windows:**
```cmd
cd d:\khete\mootcourt\legal_ipc_model
python -m venv venv_cpu
```

**Ubuntu:**
```bash
cd /path/to/legal_ipc_model
python3 -m venv venv_cpu
```

**Activate the virtual environment:**

Windows:
```cmd
venv_cpu\Scripts\activate
```

Ubuntu:
```bash
source venv_cpu/bin/activate
```

You should see `(venv_cpu)` at the start of your terminal prompt.

> **Important:** Always activate the virtual environment before running any script.
> If you close the terminal, you must activate it again.

---

## 6. Install Dependencies

With the virtual environment activated:

```cmd
pip install -r requirements.txt
```

This installs: PyTorch, Transformers, PEFT, Datasets, Pandas, Requests, and other required packages.

**Verify installation:**
```cmd
python -c "import torch, transformers, peft; print('All OK')"
```

---

## 7. Set Up Your Dataset

### Option A — Using the 3 sample files (for testing)

The project already includes 3 sample JSON files in `sample_dataset/`.
No setup needed — use `--data_dir sample_dataset` in all commands.

### Option B — Using your 26,000 JSON files (for real training)

**Your JSON files must have this structure:**
```json
{
  "case_id": "2025_INSC_1061",
  "full_text": "...",
  "ipc_sections_referred": ["376", "302", "34"],
  "headnotes": "...",
  "issue_for_consideration": "...",
  "judgment_text": "..."
}
```

**Step 1: Copy all JSON files to `data/raw/`**

Windows — if files are in `D:\USERS\`:
```cmd
xcopy "D:\USERS\*_INSC_*.json" "data\raw\" /Y
```

Or copy manually in File Explorer to:
```
d:\khete\mootcourt\legal_ipc_model\data\raw\
```

**Step 2: Verify files are there:**
```cmd
dir data\raw\*.json | find /c ".json"
```
Should show 26000 (or however many you have).

### Changing the Dataset Path

Every script has a `--data_dir` argument. Replace `sample_dataset` with your folder:

```cmd
:: Instead of:
python scripts\01_validate_dataset.py --data_dir sample_dataset

:: Use:
python scripts\01_validate_dataset.py --data_dir data/raw

:: Or with a custom absolute path:
python scripts\01_validate_dataset.py --data_dir "C:\MyData\json_cases"
```

---

## 8. Change the Model

### Change the base model for fine-tuning

The default is `Qwen/Qwen2-0.5B-Instruct` (0.5B params, ~850 MB).

To use a different model, edit `scripts/05_train_lora_cpu.py`, line 18:

```python
# Default (0.5B — good for CPU, fast)
BASE_MODEL = "Qwen/Qwen2-0.5B-Instruct"

# Larger (1.5B — better accuracy, ~3x slower on CPU)
BASE_MODEL = "Qwen/Qwen2-1.5B-Instruct"

# Even larger (3B — much better, needs 8GB+ RAM)
BASE_MODEL = "Qwen/Qwen2-7B-Instruct"
```

Or pass via command line (currently not exposed — edit the file directly).

### Change the Ollama inference model

To use a different Ollama model for predictions:

```cmd
:: Pull a different model first
ollama pull llama3.2:latest

:: Re-build the Ollama model using the new base
python scripts\10_build_ollama.py --model_name my-legal-model

:: Predict with that model
python scripts\11_predict.py --model my-legal-model --interactive
```

---

## 9. Run the Pipeline — Step by Step

**Always activate venv first:**
```cmd
venv_cpu\Scripts\activate
```

### Step 1 — Validate Dataset
Checks all JSON files for errors, missing fields, section format issues.

```cmd
python scripts\01_validate_dataset.py --data_dir sample_dataset
```

With 26k files:
```cmd
python scripts\01_validate_dataset.py --data_dir data/raw
```

Expected output:
```
DATASET VALIDATION REPORT
Total files        : 7
Valid records      : 7
Invalid (errors)   : 0
3 valid records ready for training.
```

---

### Step 2 — Prepare Dataset
Reads JSON files → cleans text → removes label leakage → saves train/val/test JSONL splits.

```cmd
python scripts\02_prepare_dataset.py --data_dir sample_dataset
```

With 26k files:
```cmd
python scripts\02_prepare_dataset.py --data_dir data/raw --val_ratio 0.08 --test_ratio 0.07
```

Output files: `data/processed/train/dataset.jsonl`, `val/`, `test/`

---

### Step 3 — Analyze Dataset
Shows token lengths, section distribution, leakage check, sample record.

```cmd
python scripts\03_analyze_dataset.py
```

---

### Step 4 — Baseline (optional but recommended)
Runs the untuned base model on the test set. Save these numbers to compare later.

```cmd
python scripts\04_test_base_model.py
```

With many test cases, limit to 50 for speed:
```cmd
python scripts\04_test_base_model.py --limit 50
```

---

### Step 5 — Train the Model

**Smoke test first (verify pipeline works — ~1 min):**
```cmd
python scripts\05_train_lora_cpu.py --limit 1 --epochs 1
```

Look for: `✓ decreased` or `loss=X.XXXX` at each step.

**100-example experiment (~10 min on CPU):**
```cmd
python scripts\05_train_lora_cpu.py --limit 100 --epochs 1
```

**1000-example experiment (~2 hours on CPU):**
```cmd
python scripts\05_train_lora_cpu.py --limit 1000 --epochs 2
```

**Full training on all data (run overnight):**
```cmd
python scripts\05_train_lora_cpu.py --epochs 3
```

**Resume after interruption:**
```cmd
python scripts\05_train_lora_cpu.py --resume models/adapters/legal-ipc-lora/checkpoints/step-000050
```

---

### Step 6 — Evaluate Fine-tuned Model

```cmd
python scripts\06_evaluate_lora.py
```

Shows side-by-side comparison with baseline:
```
Metric               Baseline  Fine-tuned    Δ
Exact Match             12%       45%      +33%
Avg F1                  0.18      0.67     +0.49
```

---

### Step 7 — Merge LoRA Adapter

Combines trained LoRA weights with the base model into a single file.

```cmd
python scripts\07_merge_lora.py
```

Output: `models/merged/legal-ipc/` (~1.9 GB)

---

### Step 8 — Convert to GGUF

Converts the merged model to GGUF format for Ollama (downloads llama.cpp automatically).

```cmd
python scripts\08_convert_gguf.py
```

Output: `models/gguf/legal-ipc-f16.gguf` (~1 GB)

---

### Step 9 — Test GGUF (optional)

Quick sanity check before loading into Ollama.

```cmd
pip install llama-cpp-python
python scripts\09_test_gguf.py
```

---

### Step 10 — Register with Ollama

```cmd
python scripts\10_build_ollama.py --model_name legal-ipc-trained
```

Verify it's registered:
```cmd
ollama list
```

You should see `legal-ipc-trained` in the list.

---

### Step 11 — Predict

Interactive mode:
```cmd
python scripts\11_predict.py --interactive
```

Single query:
```cmd
python scripts\11_predict.py --text "A man raped a minor girl and threatened her family."
```

JSON output (for integration with other apps):
```cmd
python scripts\11_predict.py --text "..." --json_out
```

---

## 10. Give Queries / Predict

### Interactive Mode
```cmd
python scripts\11_predict.py --interactive
```

Then type your case facts at the prompt:
```
Facts > A man broke into a house at night and assaulted the residents.
Analyzing...

IPC     : 457, 323, 452
BNS     : BNS 337, BNS 115(2), BNS 332
```

Type `quit` to exit.

### Single Query
```cmd
python scripts\11_predict.py --text "The accused murdered his wife for dowry and tried to make it look like suicide."
```

### Process Multiple Cases from a File

Create a text file `my_cases.txt` with one case per line:
```
A man raped a minor and threatened her.
The accused committed murder during a robbery.
The accused cheated the victim of Rs 5 lakh using forged documents.
```

Run:
```cmd
python scripts\11_predict.py --file my_cases.txt
```

### Use a Different Model
```cmd
python scripts\11_predict.py --model legal-ipc-trained --text "..."
```

### Get Raw JSON Output
```cmd
python scripts\11_predict.py --text "..." --json_out
```
Output:
```json
{
  "ipc_sections": ["376", "452", "506"],
  "bns_sections": ["BNS 64", "BNS 332", "BNS 351"],
  "reasoning": "",
  "raw": "IPC Sections: 376 (rape)...",
  "error": ""
}
```

---

## 11. Check Accuracy

### View Evaluation Results
After running `06_evaluate_lora.py`, check the saved report:
```cmd
python -c "
import json
with open('logs/lora_eval_results.json') as f:
    d = json.load(f)
m = d['metrics']
print(f'Exact Match : {m[\"exact_match\"]:.1%}')
print(f'Precision   : {m[\"avg_precision\"]:.1%}')
print(f'Recall      : {m[\"avg_recall\"]:.1%}')
print(f'F1          : {m[\"avg_f1\"]:.1%}')
print()
print('Per-section F1:')
for sec, v in list(m['per_section'].items())[:10]:
    print(f'  IPC {sec:<10} F1={v[\"f1\"]:.2f}  support={v[\"support\"]}')
"
```

### Compare Baseline vs Fine-tuned
```cmd
python -c "
import json
b = json.load(open('logs/baseline_results.json'))['metrics'] if __import__('os').path.exists('logs/baseline_results.json') else None
f = json.load(open('logs/lora_eval_results.json'))['metrics']
print(f'{'Metric':<20} {'Baseline':>10} {'Fine-tuned':>12}')
print('-' * 45)
for k, label in [('exact_match','Exact Match'),('avg_f1','F1')]:
    bv = f'{b[k]:.1%}' if b else 'N/A'
    fv = f'{f[k]:.1%}'
    print(f'{label:<20} {bv:>10} {fv:>12}')
"
```

### What accuracy to expect

| Training data | Expected F1 |
|---------------|-------------|
| 7 examples | ~0% (hallucination) |
| 100 examples | ~15-25% |
| 1,000 examples | ~40-60% |
| 5,000 examples | ~60-75% |
| 26,000 examples | ~75-85% |

---

## 12. Troubleshooting

### "Ollama not found" or "Cannot connect to Ollama"
```cmd
:: Start Ollama in a separate terminal window
ollama serve
```

### "venv_cpu\Scripts\activate is not recognized"
You are not in the right directory. Navigate first:
```cmd
cd d:\khete\mootcourt\legal_ipc_model
venv_cpu\Scripts\activate
```

### "No module named torch" or "No module named transformers"
Virtual environment is not activated or dependencies not installed:
```cmd
venv_cpu\Scripts\activate
pip install -r requirements.txt
```

### "No valid records found" in step 01 or 02
Your JSON files don't have `ipc_sections_referred`. Check one file:
```cmd
python -c "import json; d=json.load(open('sample_dataset/2017_INSC_1205.json')); print(d.get('ipc_sections_referred'))"
```

### "Out of memory" during training
Reduce sequence length in `scripts/05_train_lora_cpu.py`:
```python
MAX_SEQ_LEN = 256    # change from 512 to 256
```

Or reduce training size:
```cmd
python scripts\05_train_lora_cpu.py --limit 50 --epochs 1
```

### "Loss did not decrease" warning
Normal with very few examples (< 10). Not a code error.
With 100+ examples the loss will consistently decrease.

### Slow training
CPU training is inherently slow. Expected times:
- 100 examples × 1 epoch = ~10 min
- 1000 examples × 1 epoch = ~2 hours
- Run overnight for larger datasets

### GGUF conversion error (tokenizer)
The fix is already in `08_convert_gguf.py` (Step 3a).
If the error persists, manually fix:
```cmd
python -c "
import json
path = 'models/merged/legal-ipc/tokenizer_config.json'
cfg = json.load(open(path))
if isinstance(cfg.get('extra_special_tokens'), list):
    cfg['extra_special_tokens'] = {}
    json.dump(cfg, open(path,'w'), indent=2)
    print('Fixed')
"
```

---

## Quick Reference — All Commands

```cmd
:: Setup (run once)
python -m venv venv_cpu
venv_cpu\Scripts\activate
pip install -r requirements.txt
ollama pull llama3.1:latest

:: Pipeline (run in order)
python scripts\01_validate_dataset.py --data_dir data/raw
python scripts\02_prepare_dataset.py  --data_dir data/raw
python scripts\03_analyze_dataset.py
python scripts\04_test_base_model.py
python scripts\05_train_lora_cpu.py   --limit 1000 --epochs 3
python scripts\06_evaluate_lora.py
python scripts\07_merge_lora.py
python scripts\08_convert_gguf.py
python scripts\10_build_ollama.py     --model_name legal-ipc-trained
python scripts\11_predict.py          --model legal-ipc-trained --interactive
```
