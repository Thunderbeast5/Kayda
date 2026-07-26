# Legal IPC Model — Run From Scratch

Predicts IPC/BNS sections from Indian Supreme Court case descriptions using Ollama + llama3.1. Works on CPU, no GPU required.

---

## Prerequisites

Before starting, make sure you have:

1. **Python 3.10+** — check with `python --version`
2. **Ollama installed** — download from https://ollama.ai
3. **llama3.1 model pulled** — run `ollama pull llama3.1:latest`
4. **Ollama server running** — run `ollama serve` in a separate terminal

---

## Step 0 — One-Time Setup

Open a terminal in this folder:

```cmd
cd d:\khete\mootcourt\legal_ipc_model
```

Create a virtual environment and install dependencies:

```cmd
python -m venv venv_cpu
venv_cpu\Scripts\pip install -r requirements_cpu.txt
```

Verify Ollama is running and llama3.1 is available:

```cmd
ollama list
```

You should see `llama3.1:latest` in the list. If not:

```cmd
ollama pull llama3.1:latest
```

---

## Step 1 — Prepare Training Data

This reads your JSON case files and builds a clean JSONL dataset.

**With the 3 sample files (for testing):**
```cmd
venv_cpu\Scripts\python step1_prepare_data.py --data_dir sample_dataset
```

**With your full 26,000 JSON files:**
```cmd
venv_cpu\Scripts\python step1_prepare_data.py --data_dir data/raw
```

**With a custom folder path:**
```cmd
venv_cpu\Scripts\python step1_prepare_data.py --data_dir C:\path\to\your\json\files
```

Expected output:
```
Found 3 JSON files in sample_dataset
Valid records: 3  |  Skipped (no IPC sections): 0

Top 10 IPC sections in dataset:
  Section 376: 3 cases
  ...

Split → train:1  val:1  test:1
Data preparation complete.
```

Output files are saved to `data/processed/train/`, `data/processed/val/`, `data/processed/test/`.

---

## Step 2 — Build and Register the Model

This takes your training examples, injects them into a system prompt, and registers a new model with Ollama called `legal_ipc`.

```cmd
venv_cpu\Scripts\python step2_build_ollama_model.py
```

**With more examples (better accuracy with 26k files):**
```cmd
venv_cpu\Scripts\python step2_build_ollama_model.py --examples 25
```

**With a different base model:**
```cmd
venv_cpu\Scripts\python step2_build_ollama_model.py --base_model llama3.1:latest --examples 20
```

Expected output:
```
Loaded 2 training records
Selected 2 diverse examples
Sections covered: 323, 354, 375, 376, 506
Building system prompt with examples...
Modelfile saved: models/legal_ipc/Modelfile
Registering 'legal_ipc' with Ollama...
✅ Model 'legal_ipc' registered successfully!
```

---

## Step 3 — Predict IPC Sections

**Interactive mode (type cases one by one):**
```cmd
venv_cpu\Scripts\python step3_predict.py --interactive
```

**Single query:**
```cmd
venv_cpu\Scripts\python step3_predict.py --text "A man entered a woman's house at night and committed rape. He threatened to kill her if she reported it."
```

**Process a text file (one case per line):**
```cmd
venv_cpu\Scripts\python step3_predict.py --file my_cases.txt
```

**Get JSON output (for integration):**
```cmd
venv_cpu\Scripts\python step3_predict.py --text "..." --json_out
```

Example output:
```
=================================================================
LEGAL IPC SECTION PREDICTOR
=================================================================
INPUT: A man entered a woman's house at night and committed rape...
-----------------------------------------------------------------
IPC Sections : 376, 452, 506
BNS (2023)   : 64, 332, 351
Reasoning    : The facts establish offences involving rape,
               house-trespass, and criminal intimidation.
-----------------------------------------------------------------
```

---

## When You Add More Data (26,000 files)

Copy your JSON files to `data/raw/` then rerun steps 1 and 2:

```cmd
:: 1. Prepare data from full dataset
venv_cpu\Scripts\python step1_prepare_data.py --data_dir data/raw

:: 2. Rebuild model with 25 diverse examples
venv_cpu\Scripts\python step2_build_ollama_model.py --examples 25

:: 3. Predict
venv_cpu\Scripts\python step3_predict.py --interactive
```

---

## Full Command Reference

### step1_prepare_data.py
| Flag | Default | Description |
|------|---------|-------------|
| `--data_dir` | `sample_dataset` | Folder containing JSON case files |
| `--output_dir` | `data/processed` | Where to save JSONL splits |
| `--val_ratio` | `0.1` | Fraction for validation set |
| `--test_ratio` | `0.1` | Fraction for test set |

### step2_build_ollama_model.py
| Flag | Default | Description |
|------|---------|-------------|
| `--base_model` | `llama3.1:latest` | Ollama base model to use |
| `--model_name` | `legal_ipc` | Name for the new model |
| `--examples` | `15` | Number of training examples to inject (5–25) |
| `--data_dir` | `data/processed` | Where to read JSONL splits from |
| `--no_register` | off | Build Modelfile without registering |

### step3_predict.py
| Flag | Default | Description |
|------|---------|-------------|
| `--model` | `legal_ipc` | Ollama model name |
| `--text` | — | Single case description |
| `--file` | — | Text file with one case per line |
| `--interactive` | off | Interactive mode |
| `--json_out` | off | Output as JSON |
| `--url` | `http://127.0.0.1:11434` | Ollama server URL |

---

## Project Structure

```
legal_ipc_model/
├── README.md                        ← You are here
├── requirements_cpu.txt             ← CPU-only dependencies
│
├── step1_prepare_data.py            ← Build training dataset from JSONs
├── step2_build_ollama_model.py      ← Create and register Ollama model
├── step3_predict.py                 ← Predict IPC sections
│
├── sample_dataset/                  ← 3 sample JSON files for testing
│   ├── 2017_INSC_1030.json
│   ├── 2017_INSC_1201.json
│   └── 2017_INSC_1205.json
│
├── data/
│   ├── raw/                         ← PUT YOUR 26,000 JSON FILES HERE
│   └── processed/                   ← Auto-generated by step1
│       ├── train/dataset.jsonl
│       ├── val/dataset.jsonl
│       └── test/dataset.jsonl
│
├── models/
│   └── legal_ipc/
│       └── Modelfile                ← Auto-generated by step2
│
└── venv_cpu/                        ← Auto-generated virtual environment
```

---

## Troubleshooting

**"Cannot connect to Ollama"**
```cmd
:: Start Ollama server in a separate terminal window
ollama serve
```

**"Model 'legal_ipc' not found"**
```cmd
:: Rerun step 2
venv_cpu\Scripts\python step2_build_ollama_model.py
```

**"No valid records found" in step 1**
```cmd
:: Check your JSON files have 'ipc_sections_referred' field
python -c "import json; d=json.load(open('sample_dataset/2017_INSC_1205.json')); print(d.get('ipc_sections_referred'))"
```

**Model gives wrong or incomplete answers**
```cmd
:: Add more examples from your 26k dataset
venv_cpu\Scripts\python step2_build_ollama_model.py --examples 25 --data_dir data/processed
```

**Slow prediction on CPU**
- llama3.1:latest on CPU takes 30–90 seconds per query — this is normal
- For faster inference use `--base_model llama3.2:latest` (3B params, half the size)
  ```cmd
  ollama pull llama3.2:latest
  venv_cpu\Scripts\python step2_build_ollama_model.py --base_model llama3.2:latest
  ```
