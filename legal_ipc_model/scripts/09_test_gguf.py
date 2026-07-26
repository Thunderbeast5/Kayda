"""
09_test_gguf.py
===============
Quick sanity test of the GGUF file using llama-cpp-python
BEFORE registering with Ollama.

Runs 3 test queries and checks that the output contains IPC section numbers.

Usage:
    python scripts/09_test_gguf.py
    python scripts/09_test_gguf.py --gguf models/gguf/legal-ipc-Q4_K_M.gguf
"""

import re
import argparse
from pathlib import Path


TEST_CASES = [
    {
        "input": (
            "A man entered a woman's house at night, committed rape, "
            "and threatened to kill her if she reported it."
        ),
        "expected_sections": ["376", "452", "506"],
    },
    {
        "input": (
            "The accused killed his wife by administering poison. "
            "He had been harassing her for dowry for two years."
        ),
        "expected_sections": ["302", "498A", "304B"],
    },
    {
        "input": (
            "Several persons assembled with weapons, attacked the victim, "
            "caused grievous injuries, and robbed him of cash and jewellery."
        ),
        "expected_sections": ["395", "326", "149"],
    },
]

INSTRUCTION = (
    "You are a legal classification model for Indian criminal law. "
    "Given the following case facts, identify the applicable IPC sections. "
    "Respond ONLY in the specified format."
)


def contains_section(text: str, section: str) -> bool:
    return bool(re.search(rf'\b{re.escape(section)}\b', text))


def main():
    parser = argparse.ArgumentParser(description="Test GGUF model")
    parser.add_argument("--gguf", default="models/gguf/legal-ipc-Q4_K_M.gguf")
    parser.add_argument("--n_ctx", type=int, default=2048)
    args = parser.parse_args()

    gguf_path = Path(args.gguf)
    if not gguf_path.exists():
        # Try FP16 fallback
        fp16 = Path("models/gguf/legal-ipc-f16.gguf")
        if fp16.exists():
            print(f"Q4 GGUF not found, using FP16: {fp16}")
            gguf_path = fp16
        else:
            print(f"ERROR: GGUF file not found: {args.gguf}")
            print("Run 08_convert_gguf.py first.")
            raise SystemExit(1)

    print(f"Loading GGUF: {gguf_path}")
    try:
        from llama_cpp import Llama
    except ImportError:
        print("ERROR: llama-cpp-python not installed.")
        print("Install: pip install llama-cpp-python")
        raise SystemExit(1)

    llm = Llama(
        model_path  = str(gguf_path),
        n_ctx       = args.n_ctx,
        n_threads   = 4,
        verbose     = False,
    )
    print("Model loaded.\n")

    passed = 0
    for i, tc in enumerate(TEST_CASES, 1):
        prompt = (
            f"System: {INSTRUCTION}\n"
            f"User: {tc['input']}\n"
            f"Assistant:"
        )
        output = llm(prompt, max_tokens=80, stop=["\n\n", "User:"],
                     echo=False)
        response = output["choices"][0]["text"].strip()

        found    = [s for s in tc["expected_sections"]
                    if contains_section(response, s)]
        missed   = [s for s in tc["expected_sections"]
                    if not contains_section(response, s)]

        status = "✓ PASS" if len(found) >= len(tc["expected_sections"]) // 2 else "✗ FAIL"
        if status.startswith("✓"):
            passed += 1

        print(f"[Test {i}] {status}")
        print(f"  Input   : {tc['input'][:80]}...")
        print(f"  Expected: {tc['expected_sections']}")
        print(f"  Found   : {found}")
        print(f"  Missed  : {missed}")
        print(f"  Response: {response[:150]}")
        print()

    print(f"Result: {passed}/{len(TEST_CASES)} tests passed")
    if passed > 0:
        print("✓ GGUF is functional. Next: python scripts/10_build_ollama.py")
    else:
        print("⚠ No tests passed. The base model may not have learned the format.")
        print("  This is normal if only 100 training examples were used.")
        print("  Proceed with more training data (--limit 1000 or full dataset).")


if __name__ == "__main__":
    main()
