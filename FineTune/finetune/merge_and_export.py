"""
Merge LoRA adapter into the base model and export a standalone model.

Run after training:
    python finetune/merge_and_export.py

Why merge?
  The LoRA adapter is ~50MB. The quantized base model stays frozen.
  For inference, you can either:
    (A) Load base + adapter at runtime (slower to load, same inference speed)
    (B) Merge adapter into base, save as full model (faster to load, same inference speed)
  Option B is better for deployment. Option A is fine for experimentation.

Output:
    models/gemma2b-bail-merged/   — merged float16 model ready for inference
"""

import gc
import logging
import sys
from pathlib import Path
import os

# Redirect HF cache to D: before any HF import
_hf_cache = Path("D:/hf_cache")
_hf_cache.mkdir(parents=True, exist_ok=True)
os.environ["HF_HOME"] = str(_hf_cache)

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s")
logger = logging.getLogger(__name__)


def merge_and_save(adapter_path: Path, output_path: Path, base_model_id: str) -> None:
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import PeftModel

    logger.info(f"Loading base model: {base_model_id}")
    # Load in float16 on CPU — merging doesn't require GPU and avoids the 4GB VRAM limit.
    # On CPU this is slower to load (~2 min) but completes without OOM.
    model = AutoModelForCausalLM.from_pretrained(
        base_model_id,
        torch_dtype=torch.float16,
        device_map="cpu",           # CPU only — no VRAM needed for merge
        trust_remote_code=True,
        low_cpu_mem_usage=True,
    )

    logger.info(f"Loading LoRA adapter: {adapter_path}")
    model = PeftModel.from_pretrained(
        model,
        str(adapter_path),
        device_map="cpu",
    )

    logger.info("Merging adapter into base model weights...")
    model = model.merge_and_unload()

    logger.info(f"Saving merged model → {output_path}")
    output_path.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(output_path), safe_serialization=True)

    tokenizer = AutoTokenizer.from_pretrained(str(adapter_path), trust_remote_code=True)
    tokenizer.save_pretrained(str(output_path))

    logger.info("Merge complete.")
    logger.info(f"Merged model saved to: {output_path}")

    del model
    gc.collect()


def main() -> None:
    from finetune.config import MODEL_ID, MODEL_OUTPUT_DIR, MERGED_OUTPUT_DIR

    adapter_path = MODEL_OUTPUT_DIR / "final_adapter"
    if not adapter_path.exists():
        logger.error(f"Adapter not found at {adapter_path}. Run training first.")
        sys.exit(1)

    merge_and_save(adapter_path, MERGED_OUTPUT_DIR, MODEL_ID)


if __name__ == "__main__":
    main()
