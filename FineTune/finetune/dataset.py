"""
Dataset loader, tokenizer, and collator for fine-tuning.

Design decisions:
  - Label masking at tokenization time (in BailDataset), not via a runtime collator.
    Labels for instruction/input tokens are set to -100. Loss is only computed
    on the model's output tokens.
  - Custom collator (BailDataCollator) pads all three fields — input_ids,
    attention_mask, labels — using exactly the right pad values:
      input_ids:      pad_token_id  (tokenizer's pad token)
      attention_mask: 0             (don't attend to padding)
      labels:         -100          (ignore padding in loss)
    This guarantees input_ids and labels are always the same length, which is
    the requirement for causal LM loss computation.
  - Left-truncation: when the full prompt exceeds max_length, we truncate from
    the LEFT (cutting context from the instruction/input side) to preserve the
    model's output tokens at the end.
"""

import json
import logging
from pathlib import Path
from dataclasses import dataclass

import torch
from torch.utils.data import Dataset

logger = logging.getLogger(__name__)


class BailDataset(Dataset):
    """
    Tokenizes each example with label masking applied at load time.
    Returns dict with input_ids, attention_mask, labels as Python lists.
    BailDataCollator turns these into padded tensors at batch time.
    """

    def __init__(
        self,
        jsonl_path: Path,
        tokenizer,
        prompt_template: str,
        max_length: int = 768,
        split_name: str = "train",
    ):
        self.tokenizer = tokenizer
        self.template = prompt_template
        self.max_length = max_length
        self.split_name = split_name

        raw = self._load(jsonl_path)
        self.examples = self._process(raw)

        truncated = sum(1 for e in self.examples if e.get("_truncated", False))
        logger.info(
            f"[{split_name}] {len(self.examples)} examples loaded "
            f"({truncated} truncated to {max_length} tokens)"
        )

    def _load(self, path: Path) -> list[dict]:
        examples = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        examples.append(json.loads(line))
                    except json.JSONDecodeError as e:
                        logger.warning(f"Bad JSON in {path.name}: {e}")
        return examples

    def _process(self, raw: list[dict]) -> list[dict]:
        """
        Tokenize each example and apply label masking.

        The response boundary in the Gemma chat template is:
            <start_of_turn>model\n
        Everything before this is instruction/input (masked to -100).
        Everything from here onward is the model output (contributes to loss).

        Left-truncation preserves output tokens when the full sequence is too long.
        """
        RESPONSE_MARKER = "<start_of_turn>model\n"
        original_trunc_side = self.tokenizer.truncation_side
        processed = []
        skipped = 0

        for ex in raw:
            instruction = ex.get("instruction", "").strip()
            input_text  = ex.get("input", "").strip()
            output      = ex.get("output", "").strip()

            # Build the full prompt (instruction + input + output)
            full_prompt = self.template.format(
                instruction=instruction,
                input=input_text,
                output=output,
            )

            # Tokenize with left-truncation so output is never cut off
            self.tokenizer.truncation_side = "left"
            full_tok = self.tokenizer(
                full_prompt,
                truncation=True,
                max_length=self.max_length,
                padding=False,
                add_special_tokens=True,
                return_attention_mask=True,
            )
            self.tokenizer.truncation_side = original_trunc_side

            input_ids      = full_tok["input_ids"]
            attention_mask = full_tok["attention_mask"]
            seq_len        = len(input_ids)
            truncated      = seq_len >= self.max_length

            # Find the split point: where does the model's response start?
            # Re-tokenize the prompt-only portion (no left-truncation here)
            if RESPONSE_MARKER in full_prompt:
                marker_char_pos = full_prompt.index(RESPONSE_MARKER) + len(RESPONSE_MARKER)
                prompt_only = full_prompt[:marker_char_pos]

                # Tokenize prompt-only with the same left-truncation so lengths
                # are consistent with the full tokenization
                self.tokenizer.truncation_side = "left"
                prompt_tok = self.tokenizer(
                    prompt_only,
                    truncation=True,
                    max_length=self.max_length,
                    padding=False,
                    add_special_tokens=True,
                )
                self.tokenizer.truncation_side = original_trunc_side
                n_prompt_tokens = len(prompt_tok["input_ids"])
            else:
                # No marker found — mask nothing (train on full sequence)
                n_prompt_tokens = 0

            # Build labels: copy input_ids, mask instruction/input tokens
            labels = list(input_ids)  # explicit copy
            for i in range(min(n_prompt_tokens, seq_len)):
                labels[i] = -100

            # Verify lengths match before storing
            assert len(input_ids) == len(labels) == len(attention_mask), (
                f"Length mismatch: input_ids={len(input_ids)}, "
                f"labels={len(labels)}, attention_mask={len(attention_mask)}"
            )

            # Skip if ALL output tokens were also truncated (no learning signal)
            n_output_tokens = sum(1 for l in labels if l != -100)
            if n_output_tokens == 0:
                skipped += 1
                continue

            processed.append({
                "input_ids":      input_ids,
                "attention_mask": attention_mask,
                "labels":         labels,
                "_truncated":     truncated,
            })

        if skipped:
            logger.warning(
                f"[{self.split_name}] Skipped {skipped}/{len(raw)} examples "
                f"where output was fully truncated (no learning signal)"
            )

        return processed

    def __len__(self) -> int:
        return len(self.examples)

    def __getitem__(self, idx: int) -> dict:
        ex = self.examples[idx]
        return {
            "input_ids":      ex["input_ids"],
            "attention_mask": ex["attention_mask"],
            "labels":         ex["labels"],
        }


@dataclass
class BailDataCollator:
    """
    Pads a batch of examples to the same length.

    Padding values:
      input_ids:      pad_token_id  — so the model sees a valid token
      attention_mask: 0             — model ignores padding positions
      labels:         -100          — loss ignores padding positions

    All three fields end up the same length every time.
    This is the permanent fix for "batch_size mismatch" errors.
    """
    pad_token_id: int
    pad_to_multiple_of: int = 8

    def __call__(self, features: list[dict]) -> dict[str, torch.Tensor]:
        # Find longest sequence in this batch
        max_len = max(len(f["input_ids"]) for f in features)

        # Round up to multiple of 8 for CUDA efficiency
        if self.pad_to_multiple_of:
            max_len = ((max_len + self.pad_to_multiple_of - 1)
                       // self.pad_to_multiple_of * self.pad_to_multiple_of)

        batch_input_ids      = []
        batch_attention_mask = []
        batch_labels         = []

        for f in features:
            seq_len    = len(f["input_ids"])
            pad_len    = max_len - seq_len

            # Pad on the RIGHT (standard for causal LM)
            batch_input_ids.append(
                f["input_ids"] + [self.pad_token_id] * pad_len
            )
            batch_attention_mask.append(
                f["attention_mask"] + [0] * pad_len
            )
            batch_labels.append(
                f["labels"] + [-100] * pad_len
            )

        return {
            "input_ids":      torch.tensor(batch_input_ids,      dtype=torch.long),
            "attention_mask": torch.tensor(batch_attention_mask, dtype=torch.long),
            "labels":         torch.tensor(batch_labels,         dtype=torch.long),
        }


def build_datasets(
    tokenizer,
    prompt_template: str,
    train_path: Path,
    val_path: Path,
    max_length: int = 768,
) -> tuple[BailDataset, BailDataset]:
    train_ds = BailDataset(train_path, tokenizer, prompt_template, max_length, "train")
    val_ds   = BailDataset(val_path,   tokenizer, prompt_template, max_length, "val")
    return train_ds, val_ds
