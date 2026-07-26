"""
08_convert_gguf.py
==================
Converts the merged HuggingFace model to GGUF format using llama.cpp,
then quantizes to Q4_K_M for efficient CPU inference in Ollama.

Steps:
  1. Clone llama.cpp (if not already present)
  2. Install llama.cpp Python requirements
  3. Run convert_hf_to_gguf.py  → FP16 GGUF
  4. Quantize FP16 → Q4_K_M    → ~300 MB from ~1 GB

Prerequisites:
  - git must be in PATH
  - Merged model must exist: models/merged/legal-ipc/

Usage:
    python scripts/08_convert_gguf.py
    python scripts/08_convert_gguf.py --merged_dir models/merged/legal-ipc
"""

import argparse
import subprocess
import sys
from pathlib import Path


MERGED_DIR   = "models/merged/legal-ipc"
GGUF_DIR     = "models/gguf"
LLAMA_CPP_DIR= "llama.cpp"
FP16_GGUF    = "models/gguf/legal-ipc-f16.gguf"
QUANT_GGUF   = "models/gguf/legal-ipc-Q4_K_M.gguf"
QUANT_TYPE   = "Q4_K_M"


def run(cmd: list, cwd: str = None, check: bool = True) -> int:
    print(f"  $ {' '.join(str(c) for c in cmd)}")
    result = subprocess.run(cmd, cwd=cwd)
    if check and result.returncode != 0:
        print(f"ERROR: command failed (exit {result.returncode})")
        raise SystemExit(result.returncode)
    return result.returncode


def main():
    parser = argparse.ArgumentParser(description="Convert merged model to GGUF")
    parser.add_argument("--merged_dir", default=MERGED_DIR)
    parser.add_argument("--gguf_dir",   default=GGUF_DIR)
    parser.add_argument("--quant_type", default=QUANT_TYPE,
                        choices=["Q4_K_M", "Q5_K_M", "Q8_0", "F16"])
    parser.add_argument("--skip_clone", action="store_true",
                        help="Skip git clone (llama.cpp already present)")
    args = parser.parse_args()

    merged = Path(args.merged_dir)
    if not merged.exists():
        print(f"ERROR: Merged model not found: {merged}")
        print("Run 07_merge_lora.py first.")
        raise SystemExit(1)

    Path(args.gguf_dir).mkdir(parents=True, exist_ok=True)

    # ── Step 1: Clone llama.cpp ───────────────────────────────────────────────
    if not Path(LLAMA_CPP_DIR).exists() and not args.skip_clone:
        print("\n[1] Cloning llama.cpp...")
        run(["git", "clone", "--depth=1",
             "https://github.com/ggerganov/llama.cpp.git",
             LLAMA_CPP_DIR])
    else:
        print(f"\n[1] llama.cpp directory found at {LLAMA_CPP_DIR}")

    # ── Step 2: Install llama.cpp Python requirements ─────────────────────────
    print("\n[2] Installing llama.cpp Python requirements...")
    req_path = Path(LLAMA_CPP_DIR) / "requirements.txt"
    if req_path.exists():
        run([sys.executable, "-m", "pip", "install", "-r", str(req_path), "-q"])
    else:
        # Minimal deps for conversion only
        run([sys.executable, "-m", "pip", "install",
             "numpy", "sentencepiece", "transformers", "-q"])

    # ── Step 3: Fix Qwen2 tokenizer_config before conversion ─────────────────
    # Qwen2's tokenizer_config has extra_special_tokens as a list, but
    # llama.cpp's conversion script expects a dict. Fix it first.
    print("\n[3a] Fixing Qwen2 tokenizer_config for llama.cpp compatibility...")
    tokenizer_cfg_path = merged / "tokenizer_config.json"
    if tokenizer_cfg_path.exists():
        import json as _json
        with open(tokenizer_cfg_path, encoding="utf-8") as f:
            tcfg = _json.load(f)
        est = tcfg.get("extra_special_tokens")
        if isinstance(est, list):
            tcfg["extra_special_tokens"] = {}
            with open(tokenizer_cfg_path, "w", encoding="utf-8") as f:
                _json.dump(tcfg, f, indent=2, ensure_ascii=False)
            print("  Fixed: extra_special_tokens list → dict")
        else:
            print("  tokenizer_config OK (no fix needed)")

    # ── Step 4: Convert to FP16 GGUF ─────────────────────────────────────────
    print(f"\n[4] Converting {args.merged_dir} → {FP16_GGUF} (FP16)...")
    convert_script = Path(LLAMA_CPP_DIR) / "convert_hf_to_gguf.py"
    if not convert_script.exists():
        # Older llama.cpp uses convert.py
        convert_script = Path(LLAMA_CPP_DIR) / "convert.py"
    if not convert_script.exists():
        print("ERROR: No conversion script found in llama.cpp/")
        print("Try: git -C llama.cpp pull")
        raise SystemExit(1)

    run([
        sys.executable, str(convert_script),
        str(merged),
        "--outfile", FP16_GGUF,
        "--outtype", "f16",
    ])
    print(f"  FP16 GGUF created: {FP16_GGUF}")

    # ── Step 5: Quantize to Q4_K_M ───────────────────────────────────────────
    quant_out = str(Path(args.gguf_dir) /
                    f"legal-ipc-{args.quant_type}.gguf")
    print(f"\n[4] Quantizing FP16 → {quant_out} ({args.quant_type})...")

    # Try pre-built quantize binary first
    quantize_bin = Path(LLAMA_CPP_DIR) / "quantize"
    if not quantize_bin.exists():
        quantize_bin = Path(LLAMA_CPP_DIR) / "quantize.exe"
    if not quantize_bin.exists():
        # Python-based quantization fallback via llama-cpp-python
        print("  quantize binary not found — trying llama-cpp-python...")
        run([sys.executable, "-m", "pip", "install", "llama-cpp-python", "-q"],
            check=False)
        try:
            from llama_cpp import Llama
            print("  Using llama-cpp-python for quantization...")
            # llama-cpp-python doesn't expose CLI quantize easily;
            # skip and use FP16 GGUF directly
            print(f"  ⚠ Quantization skipped. Using FP16 GGUF: {FP16_GGUF}")
            quant_out = FP16_GGUF
        except ImportError:
            print(f"  ⚠ llama-cpp-python not available. Using FP16 GGUF: {FP16_GGUF}")
            quant_out = FP16_GGUF
    else:
        run([str(quantize_bin), FP16_GGUF, quant_out, args.quant_type])

    size_mb = Path(quant_out).stat().st_size / 1e6 if Path(quant_out).exists() else 0
    print(f"\n✓ GGUF ready: {quant_out}  ({size_mb:.0f} MB)")
    print(f"  Next: python scripts/09_test_gguf.py --gguf {quant_out}")


if __name__ == "__main__":
    main()
