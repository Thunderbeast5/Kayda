# Legal IPC Model — LLM Fine-tuning Pipeline

Fine-tunes Mistral-7B (or Llama-3-8B) on 26,000 Indian Supreme Court cases to predict IPC/BNS sections from case descriptions.

## Project Structure

```
legal_ipc_model/
├── prepare_data.py        # Step 1: validate + build datasets
├── train.py               # Step 2: fine-tune the model
├── evaluate.py            # Step 3: evaluate on test set
├── predict.py             # Step 4: run inference
├── setup_ubuntu.sh        # Server setup script
├── requirements.txt
├── src/
│   ├── data_preparation/
│   │   ├── data_validator.py   # Loads + validates 26k JSON files
│   │   └── dataset_builder.py  # Builds instruction-tuning dataset
│   ├── model/
│   │   ├── trainer.py          # QLoRA fine-tuning
│   │   └── evaluator.py        # Metrics: exact match, F1
│   └── utils/
│       └── logger_setup.py
├── data/
│   ├── raw/              ← put your 26k JSON files here
│   └── processed/
│       ├── train/
│       ├── val/
│       └── test/
├── models/
│   └── legal_model/
│       └── final/        ← trained model saved here
└── logs/
```

## Quick Start (Ubuntu Server)

```bash
# 1. Setup environment (run once)
bash setup_ubuntu.sh

# 2. Copy JSON files to data/raw/
rsync -avz /path/to/json/files/ data/raw/

# 3. Prepare data (~5 min for 26k files)
source venv/bin/activate
python prepare_data.py --data_dir data/raw

# 4. Train (8-16 hours on A100 / 24-48h on T4)
nohup python train.py > logs/train.log 2>&1 &
tail -f logs/train.log

# 5. Evaluate
python evaluate.py

# 6. Predict
python predict.py --interactive
```

## Training Configuration

| Parameter | Default | Notes |
|-----------|---------|-------|
| Base model | Mistral-7B-Instruct-v0.2 | Change with `--model` |
| Quantization | 4-bit (QLoRA) | Needs ~12GB VRAM |
| LoRA rank | 32 | Increase for more capacity |
| Epochs | 3 | 3-5 recommended |
| Batch size | 2 | Increase if VRAM allows |
| Grad accumulation | 8 | Effective batch = 16 |
| Learning rate | 2e-4 | |
| Max seq length | 2048 | |

## Using Llama-3 Instead

```bash
# Login to HuggingFace first
huggingface-cli login

python train.py --model meta-llama/Meta-Llama-3-8B-Instruct
```

## Expected Performance

After 3 epochs on ~20k training cases:
- Exact match: ~45-55%
- Section-level F1: ~70-80%
- Common sections (376, 302, 498A): F1 > 85%

## JSON Schema Expected

Each JSON file must have:
- `case_id` — unique identifier
- `full_text` — complete judgment text
- `ipc_sections_referred` — list of IPC sections

Optional (improves quality):
- `headnotes`, `issue_for_consideration`, `judgment_text`
- `list_of_keywords`, `list_of_acts`, `bns_sections_referred`
