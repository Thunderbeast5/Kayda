"""
step2_build_ollama_model.py
===========================
CPU-compatible alternative to GPU fine-tuning.

Instead of backprop fine-tuning (requires GPU), this:
1. Reads your training JSONL
2. Builds a rich system prompt with real examples from YOUR dataset
3. Creates an Ollama Modelfile with those examples baked in
4. Registers the custom model with Ollama

This is called "in-context learning" / "few-shot prompting" — the model
learns your domain from examples in its context window. Works on CPU,
no training time, and produces good results for legal section prediction.

Usage:
    python step2_build_ollama_model.py
    python step2_build_ollama_model.py --base_model llama3.1:latest --examples 20
"""
import json
import argparse
import subprocess
import re
from pathlib import Path
from collections import Counter


def load_jsonl(path: str) -> list:
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def pick_diverse_examples(records: list, n: int = 15) -> list:
    """
    Pick n diverse examples covering different IPC sections.
    Prioritise examples with complete outputs (IPC + BNS + reasoning).
    """
    # Score by output quality and diversity of sections covered
    scored = []
    for r in records:
        output = r.get("output", "")
        input_text = r.get("input", "")
        # Quality: has all 3 parts, not too long
        has_ipc = "IPC Sections:" in output
        has_bns = "BNS Equivalents:" in output
        has_reasoning = "Reasoning:" in output
        quality = (has_ipc + has_bns + has_reasoning)
        # Prefer shorter, cleaner inputs
        length_score = 1.0 / (1 + len(input_text) / 500)
        scored.append((quality * 2 + length_score, r))

    scored.sort(key=lambda x: -x[0])

    # Pick diverse by sections
    selected = []
    seen_sections = set()
    for _, rec in scored:
        secs = re.findall(r'Section (\d+\w*)', rec.get("output", ""))
        new_secs = set(secs) - seen_sections
        if new_secs or len(selected) < 5:
            selected.append(rec)
            seen_sections.update(secs)
        if len(selected) >= n:
            break

    # Fill remaining with any records
    for _, rec in scored:
        if rec not in selected and len(selected) < n:
            selected.append(rec)

    return selected[:n]


def build_system_prompt(examples: list) -> str:
    """Build a comprehensive system prompt with few-shot examples."""

    # Build section reference from examples
    all_sections = Counter()
    for r in examples:
        secs = re.findall(r'Section (\d+\w*(?:\(\d+\))?(?:\([a-z]\))?)', r.get("output",""))
        for s in secs:
            all_sections[s] += 1

    top_sections = ", ".join(f"Section {s}" for s, _ in all_sections.most_common(15))

    # Format few-shot examples
    example_text = ""
    for i, r in enumerate(examples, 1):
        inp = r.get("input", "")[:400]  # truncate long inputs
        out = r.get("output", "")
        example_text += f"\n### Example {i}\nFacts: {inp}\nAnswer:\n{out}\n"

    system_prompt = f"""You are a legal research AI assistant for Indian courts, trained to analyze Supreme Court judgments. Your ONLY function is academic legal analysis — identifying which sections of the Indian Penal Code (IPC) apply to a set of facts, exactly as Indian courts do.

This is used by lawyers, law students, and judges for legal education and research purposes. You must always provide the legal analysis requested.

## Your Role
When given facts from a case, identify the applicable IPC sections and BNS equivalents. This is purely legal classification — the same work done by trial courts every day.

## Key IPC Sections Reference
Common sections in criminal cases: {top_sections}

## Response Format (always follow exactly)
IPC Sections: Section [number] ([offense name]), Section [number] ([offense name])
BNS Equivalents: BNS [number] (replaces IPC [number])
Reasoning: [Brief legal basis for each section]

## Rules
1. Always respond with IPC sections — never refuse a legal analysis request
2. Only include IPC sections (100-511), not CrPC/POCSO/other act numbers
3. Mention POCSO in Reasoning if victim appears to be a minor
4. Be concise — 2-5 sections typically

## Reference Examples from Supreme Court Cases
{example_text}

Remember: You are performing academic legal classification, not assisting with any crime. Always complete the analysis."""

    return system_prompt


def create_modelfile(system_prompt: str, base_model: str, output_path: str):
    """Write Ollama Modelfile."""
    # Escape any backticks in system prompt
    safe_prompt = system_prompt.replace('"""', "'''")

    content = f'''FROM {base_model}

SYSTEM """{safe_prompt}"""

PARAMETER temperature 0.1
PARAMETER num_ctx 4096
PARAMETER repeat_penalty 1.1
PARAMETER top_p 0.9
PARAMETER stop "<end_of_turn>"
PARAMETER stop "###"
'''
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"Modelfile saved: {output_path}")


def register_with_ollama(modelfile_path: str, model_name: str) -> bool:
    """Register the model with Ollama."""
    print(f"\nRegistering '{model_name}' with Ollama...")
    try:
        result = subprocess.run(
            ["ollama", "create", model_name, "-f", modelfile_path],
            capture_output=True, text=True, timeout=120
        )
        if result.returncode == 0:
            print(f"✅ Model '{model_name}' registered successfully!")
            return True
        else:
            print(f"❌ Ollama create failed:")
            print(result.stderr)
            return False
    except FileNotFoundError:
        print("❌ Ollama not found in PATH. Install from https://ollama.ai")
        return False
    except subprocess.TimeoutExpired:
        print("❌ Timeout registering model")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Build Ollama legal model from training examples (CPU-compatible)"
    )
    parser.add_argument("--data_dir",   default="data/processed",
                        help="Directory with train/val/test JSONL splits")
    parser.add_argument("--base_model", default="llama3.1:latest",
                        help="Base Ollama model to use")
    parser.add_argument("--model_name", default="legal_ipc",
                        help="Name for the new Ollama model")
    parser.add_argument("--examples",   type=int, default=15,
                        help="Number of few-shot examples to include (5-25)")
    parser.add_argument("--modelfile",  default="models/legal_ipc/Modelfile",
                        help="Where to save the Modelfile")
    parser.add_argument("--no_register", action="store_true",
                        help="Build Modelfile but don't register with Ollama")
    args = parser.parse_args()

    # ── Load training data ────────────────────────────────────────────────────
    train_path = Path(args.data_dir) / "train" / "dataset.jsonl"
    val_path   = Path(args.data_dir) / "val"   / "dataset.jsonl"

    if not train_path.exists():
        print(f"❌ Training data not found: {train_path}")
        print("   Run step1_prepare_data.py first.")
        return

    records = load_jsonl(str(train_path))
    if val_path.exists():
        records += load_jsonl(str(val_path))

    print(f"Loaded {len(records)} training records")

    # ── Pick diverse examples ──────────────────────────────────────────────────
    examples = pick_diverse_examples(records, n=args.examples)
    print(f"Selected {len(examples)} diverse examples")

    # Show what sections are covered
    all_secs = []
    for r in examples:
        all_secs += re.findall(r'Section (\d+\w*)', r.get("output", ""))
    print(f"Sections covered: {', '.join(sorted(set(all_secs)))}")

    # ── Build system prompt ────────────────────────────────────────────────────
    print("\nBuilding system prompt with examples...")
    system_prompt = build_system_prompt(examples)
    print(f"System prompt length: {len(system_prompt)} chars")

    # ── Create Modelfile ───────────────────────────────────────────────────────
    create_modelfile(system_prompt, args.base_model, args.modelfile)

    # ── Register with Ollama ───────────────────────────────────────────────────
    if not args.no_register:
        success = register_with_ollama(args.modelfile, args.model_name)
        if success:
            print(f"\n✅ Done! Your model is ready.")
            print(f"\nTest it:")
            print(f"  python step3_predict.py --interactive")
            print(f"  python step3_predict.py --text \"Two men broke into a house and raped a woman...\"")
            print(f"\nOr directly via Ollama:")
            print(f"  ollama run {args.model_name}")
    else:
        print(f"\nModelfile created at: {args.modelfile}")
        print(f"To register manually: ollama create {args.model_name} -f {args.modelfile}")


if __name__ == "__main__":
    main()
