"""
file_utils.py — File I/O helpers
"""
import hashlib
import json
import os
import pickle
from pathlib import Path
from typing import Any


def compute_hash(file_path: str) -> str:
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def ensure_dirs(*paths: str):
    for p in paths:
        Path(p).mkdir(parents=True, exist_ok=True)


def save_checkpoint(data: Any, path: str = "checkpoints/checkpoint.pkl"):
    ensure_dirs(str(Path(path).parent))
    with open(path, "wb") as f:
        pickle.dump(data, f)


def load_checkpoint(path: str = "checkpoints/checkpoint.pkl") -> Any:
    if not Path(path).exists():
        return None
    with open(path, "rb") as f:
        return pickle.load(f)


def save_json(data: Any, path: str):
    ensure_dirs(str(Path(path).parent))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)


def save_jsonl(rows: list[dict], path: str):
    ensure_dirs(str(Path(path).parent))
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def list_pdfs(directory: str) -> list[str]:
    return sorted(str(p) for p in Path(directory).rglob("*.pdf"))
