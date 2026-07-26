"""
10_build_ollama.py
==================
Creates and registers the fine-tuned model with Ollama using a Modelfile
that points to the GGUF file.

This is the FINAL step before prediction. The model in Ollama at this
point is backed by TRAINED parameters, not just a system prompt.

Usage:
    python scripts/10_build_ollama.py
    python scripts/10_build_ollama.py --gguf models/gguf/legal-ipc-Q4_K_M.gguf
    python scripts/10_build_ollama.py --model_name legal-ipc-trained
"""

import argparse
import subprocess
import os
from pathlib import Path


GGUF_PATH   = "models/gguf/legal-ipc-Q4_K_M.gguf"
MODEL_NAME  = "legal-ipc-trained"
MODELFILE   = "models/gguf/Modelfile"

SYSTEM_PROMPT = (
    "You are a legal classification model trained on Indian Supreme Court judgments. "
    "When given case facts, identify the applicable IPC sections and their "
    "BNS 2023 equivalents. Always respond in this exact format:\n"
    "IPC Sections: [comma-separated section numbers]\n"
    "BNS Equivalents: [comma-separated BNS numbers]\n"
    "Keep your response concise and structured."
)


def write_modelfile(gguf_abs_path: str, model_name: str, out_path: str):
    content = f"""FROM {gguf_abs_path}

SYSTEM \"\"\"{SYSTEM_PROMPT}\"\"\"

PARAMETER temperature 0.1
PARAMETER num_ctx 2048
PARAMETER repeat_penalty 1.1
PARAMETER stop "User:"
PARAMETER stop "\\n\\n\\n"
"""
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"  Modelfile written: {out_path}")


def register_ollama(modelfile_path: str, model_name: str) -> bool:
    print(f"\nRegistering '{model_name}' with Ollama...")
    try:
        result = subprocess.run(
            ["ollama", "create", model_name, "-f", modelfile_path],
            capture_output=True, text=True, timeout=300
        )
        if result.returncode == 0:
            print(f"✓ Model '{model_name}' registered successfully!")
            return True
        else:
            print(f"✗ ollama create failed:")
            print(result.stderr[:500])
            return False
    except FileNotFoundError:
        print("✗ Ollama not found in PATH.")
        print("  Install from https://ollama.ai and ensure 'ollama' is in PATH.")
        return False
    except subprocess.TimeoutExpired:
        print("✗ Timeout registering model (>300s)")
        return False


def main():
    parser = argparse.ArgumentParser(description="Register fine-tuned model with Ollama")
    parser.add_argument("--gguf",       default=GGUF_PATH)
    parser.add_argument("--model_name", default=MODEL_NAME)
    parser.add_argument("--modelfile",  default=MODELFILE)
    args = parser.parse_args()

    # Prefer Q4 GGUF, fall back to FP16
    gguf_path = Path(args.gguf)
    if not gguf_path.exists():
        fp16 = Path("models/gguf/legal-ipc-f16.gguf")
        if fp16.exists():
            print(f"Q4 GGUF not found, using FP16: {fp16}")
            gguf_path = fp16
        else:
            print(f"ERROR: GGUF not found: {args.gguf}")
            print("Run 08_convert_gguf.py first.")
            raise SystemExit(1)

    # Ollama needs absolute path in Modelfile
    gguf_abs = str(gguf_path.resolve()).replace("\\", "/")
    print(f"GGUF     : {gguf_abs}")
    print(f"Model    : {args.model_name}")

    write_modelfile(gguf_abs, args.model_name, args.modelfile)
    success = register_ollama(args.modelfile, args.model_name)

    if success:
        print(f"\n✓ Done! Your trained model is in Ollama as: {args.model_name}")
        print(f"\n  Test directly:")
        print(f"    ollama run {args.model_name}")
        print(f"\n  Or use the predictor:")
        print(f"    python scripts/11_predict.py --model {args.model_name} --interactive")


if __name__ == "__main__":
    main()
