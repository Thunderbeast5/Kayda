"""
07_merge_lora.py
================
Merges the LoRA adapter weights into the base model to produce
a standalone HuggingFace model (no adapter dependency).

Input:  base model + adapter in models/adapters/legal-ipc-lora/final
Output: merged model in models/merged/legal-ipc/

Usage:
    python scripts/07_merge_lora.py
    python scripts/07_merge_lora.py --adapter models/adapters/legal-ipc-lora/best
"""

import argparse
from pathlib import Path


BASE_MODEL  = "google/gemma-3-4b-it"
ADAPTER_DIR = "models/adapters/gemma3-legal-lora/final"
MERGED_DIR  = "models/merged/gemma3-legal"


def main():
    parser = argparse.ArgumentParser(description="Merge LoRA adapter into base model")
    parser.add_argument("--model",      default=BASE_MODEL)
    parser.add_argument("--adapter",    default=ADAPTER_DIR)
    parser.add_argument("--output_dir", default=MERGED_DIR)
    args = parser.parse_args()

    if not Path(args.adapter).exists():
        print(f"ERROR: Adapter not found: {args.adapter}")
        print("Run 05_train_lora_cpu.py first.")
        raise SystemExit(1)

    print(f"Base model : {args.model}")
    print(f"Adapter    : {args.adapter}")
    print(f"Output     : {args.output_dir}")

    import torch
    from transformers import AutoTokenizer, AutoModelForCausalLM
    from peft import PeftModel

    print("\nLoading base model on CPU...")
    tokenizer = AutoTokenizer.from_pretrained(args.adapter, trust_remote_code=True)
    base = AutoModelForCausalLM.from_pretrained(
        args.model,
        torch_dtype       = torch.float32,
        device_map        = "cpu",
        trust_remote_code = True,
    )

    print("Loading LoRA adapter...")
    model = PeftModel.from_pretrained(base, args.adapter)

    print("Merging adapter weights into base model...")
    model = model.merge_and_unload()

    print(f"Saving merged model to {args.output_dir}...")
    Path(args.output_dir).mkdir(parents=True, exist_ok=True)
    model.save_pretrained(args.output_dir, safe_serialization=True)
    tokenizer.save_pretrained(args.output_dir)

    # Verify
    size_mb = sum(
        p.stat().st_size for p in Path(args.output_dir).rglob("*") if p.is_file()
    ) / 1e6
    print(f"\n✓ Merged model saved ({size_mb:.0f} MB)")
    print(f"  Next: python scripts/08_convert_gguf.py")


if __name__ == "__main__":
    main()
