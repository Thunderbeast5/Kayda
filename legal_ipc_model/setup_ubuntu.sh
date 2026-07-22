#!/bin/bash
# setup_ubuntu.sh — Run this ONCE on the Ubuntu server to set up the environment
# Usage: bash setup_ubuntu.sh

set -e
echo "========================================"
echo "  Legal IPC Model — Ubuntu Server Setup"
echo "========================================"

# 1. Check GPU
echo ""
echo "[1] Checking GPU..."
nvidia-smi || echo "WARNING: nvidia-smi not found. GPU may not be available."

# 2. Python version check
echo ""
echo "[2] Python version..."
python3 --version

# 3. Create virtual environment
echo ""
echo "[3] Creating virtual environment..."
python3 -m venv venv
source venv/bin/activate

# 4. Upgrade pip
pip install --upgrade pip setuptools wheel

# 5. Install PyTorch with CUDA (adjust cuda version to match your server)
echo ""
echo "[4] Installing PyTorch with CUDA 12.1..."
pip install torch==2.3.0 torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

# 6. Install remaining requirements
echo ""
echo "[5] Installing requirements..."
pip install -r requirements.txt

# 7. Verify
echo ""
echo "[6] Verifying installation..."
python3 -c "
import torch
print(f'PyTorch: {torch.__version__}')
print(f'CUDA available: {torch.cuda.is_available()}')
if torch.cuda.is_available():
    print(f'GPU: {torch.cuda.get_device_name(0)}')
    print(f'VRAM: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB')
import transformers, peft, trl, datasets
print(f'Transformers: {transformers.__version__}')
print(f'PEFT: {peft.__version__}')
print(f'TRL: {trl.__version__}')
print(f'Datasets: {datasets.__version__}')
print('All packages OK.')
"

# 8. Create data directories
echo ""
echo "[7] Creating data directories..."
mkdir -p data/raw data/processed/train data/processed/val data/processed/test
mkdir -p models logs

echo ""
echo "========================================"
echo "Setup complete."
echo ""
echo "NEXT STEPS:"
echo "1. Copy your 26,000 JSON files to:  data/raw/"
echo "   rsync -avz /path/to/json/files/ data/raw/"
echo ""
echo "2. Prepare training data:"
echo "   python prepare_data.py --data_dir data/raw"
echo ""
echo "3. Start training (use nohup for long runs):"
echo "   nohup python train.py > logs/train.log 2>&1 &"
echo "   tail -f logs/train.log"
echo ""
echo "4. Evaluate:"
echo "   python evaluate.py"
echo ""
echo "5. Predict:"
echo "   python predict.py --interactive"
echo "========================================"
