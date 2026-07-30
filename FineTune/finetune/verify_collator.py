"""Quick sanity check — run before training to verify collator is correct."""
import os, sys
os.environ["HF_HOME"] = "D:/hf_cache"
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))

from transformers import AutoTokenizer
from finetune.config import PROMPT_TEMPLATE, MAX_SEQ_LENGTH, TRAIN_FILE
from finetune.dataset import BailDataset, BailDataCollator

tok = AutoTokenizer.from_pretrained("google/gemma-2b-it", trust_remote_code=True)
if tok.pad_token is None:
    tok.pad_token = tok.eos_token

ds = BailDataset(TRAIN_FILE, tok, PROMPT_TEMPLATE, MAX_SEQ_LENGTH, "train")
collator = BailDataCollator(pad_token_id=tok.pad_token_id, pad_to_multiple_of=8)

print(f"\nDataset size: {len(ds)}")

errors = []
for batch_size in [1, 2, 4, 8]:
    batch = [ds[i] for i in range(batch_size)]
    out = collator(batch)
    ids_s   = tuple(out["input_ids"].shape)
    attn_s  = tuple(out["attention_mask"].shape)
    label_s = tuple(out["labels"].shape)
    ok = ids_s == attn_s == label_s
    status = "OK" if ok else "FAIL"
    print(f"  batch={batch_size}: {ids_s} [{status}]")
    if not ok:
        errors.append(f"batch={batch_size}: input={ids_s} labels={label_s}")

total_out = sum(sum(1 for l in ds[i]["labels"] if l != -100) for i in range(min(50, len(ds))))
total_tok = sum(len(ds[i]["labels"]) for i in range(min(50, len(ds))))
print(f"\nFirst 50 examples: {total_out}/{total_tok} tokens are output ({total_out/total_tok*100:.1f}%)")

if errors:
    print("\nFAILURES:", errors)
    sys.exit(1)
else:
    print("\nAll checks passed. Safe to train.")
