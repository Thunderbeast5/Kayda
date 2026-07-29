"""
Dataset loader and tokenizer for fine-tuning.
Handles prompt formatting, tokenization, and length filtering.
"""

import json
import logging
from pathlib import Path
from typing import Optional

from torch.utils.data import Dataset

logger = logging.getLogger(__name__)


def format_prompt(instruction: str, input_text: str, output: str, template: str) -> str:
    """Apply the prompt template to one training example."""
    return template.format(
        instruction=instruction.strip(),
        input=input_text.strip(),
        output=output.strip(),
    )


class BailDataset(Dataset):
    """
    Dataset for anticipatory bail instruction fine-tuning.

    Each example is a fully-formatted prompt string:
        <start_of_turn>user\n{instruction}\n\nContext:\n{input}<end_of_turn>
        <start_of_turn>model\n{output}<end_of_turn>

    The model is trained to predict the entire sequence (input + output).
    Loss masking on the instruction/input portion is handled separately
    via the DataCollatorForSeq2Seq in the trainer setup.
    """

    def __init__(
        self,
        jsonl_path: Path,
        tokenizer,
        prompt_template: str,
        max_length: int = 1024,
        split_name: str = "train",
    ):
        self.tokenizer = tokenizer
        self.template = prompt_template
        self.max_length = max_length
        self.split_name = split_name

        raw_examples = self._load(jsonl_path)
        self.examples = self._tokenize_and_filter(raw_examples)

        logger.info(
            f"[{split_name}] Loaded {len(self.examples)} examples "
            f"(from {len(raw_examples)} raw, "
            f"{len(raw_examples) - len(self.examples)} filtered for length)"
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
                        logger.warning(f"Bad JSON line in {path}: {e}")
        return examples

    def _tokenize_and_filter(self, raw: list[dict]) -> list[dict]:
        """
        Tokenize each example and filter those that exceed max_length.
        Returns list of tokenized dicts with input_ids, attention_mask, labels.

        Labels: copy of input_ids. The DataCollator will mask the prompt portion
        so loss is only computed on the model's output tokens.
        """
        processed = []
        too_long = 0

        for ex in raw:
            # Format the full prompt (instruction + input + output)
            full_prompt = format_prompt(
                ex["instruction"], ex.get("input", ""), ex["output"], self.template
            )

            # Tokenize — no padding here, handled by DataCollator
            tokenized = self.tokenizer(
                full_prompt,
                truncation=True,
                max_length=self.max_length,
                padding=False,
                return_tensors=None,  # return plain lists, not tensors
            )

            if len(tokenized["input_ids"]) >= self.max_length:
                too_long += 1
                # Still include it — truncation is fine for training,
                # but flag it so we know how many were truncated
                tokenized["_truncated"] = True
            else:
                tokenized["_truncated"] = False

            # Labels = input_ids (SFT: predict the whole sequence)
            tokenized["labels"] = tokenized["input_ids"].copy()

            processed.append(tokenized)

        if too_long:
            logger.warning(
                f"[{self.split_name}] {too_long}/{len(raw)} examples "
                f"hit max_length={self.max_length} and were truncated"
            )

        return processed

    def __len__(self) -> int:
        return len(self.examples)

    def __getitem__(self, idx: int) -> dict:
        ex = self.examples[idx]
        return {
            "input_ids": ex["input_ids"],
            "attention_mask": ex["attention_mask"],
            "labels": ex["labels"],
        }


def build_datasets(
    tokenizer,
    prompt_template: str,
    train_path: Path,
    val_path: Path,
    max_length: int = 1024,
) -> tuple["BailDataset", "BailDataset"]:
    """Build train and validation datasets."""
    train_ds = BailDataset(train_path, tokenizer, prompt_template, max_length, "train")
    val_ds   = BailDataset(val_path,   tokenizer, prompt_template, max_length, "val")
    return train_ds, val_ds
