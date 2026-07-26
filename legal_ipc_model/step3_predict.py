"""
step3_predict.py
================
Query the fine-tuned Ollama model for IPC section prediction.

Usage:
    python step3_predict.py --interactive
    python step3_predict.py --text "Two men broke into a house and raped a woman..."
    python step3_predict.py --file cases.txt
    python step3_predict.py --model legal_ipc --text "..."
"""
import argparse
import re
import sys
import json
import requests
from pathlib import Path


OLLAMA_URL   = "http://127.0.0.1:11434"
DEFAULT_MODEL = "legal_ipc"


def predict_ollama(text: str, model: str = DEFAULT_MODEL,
                   url: str = OLLAMA_URL) -> dict:
    """Send case facts to Ollama and parse the response."""
    try:
        resp = requests.post(
            f"{url}/api/generate",
            json={
                "model":  model,
                "prompt": f"Case facts:\n{text}\n\nAnalyze and identify applicable IPC sections:",
                "stream": False,
                "options": {
                    "temperature":   0.1,
                    "num_predict":   400,
                    "num_ctx":       4096,
                    "repeat_penalty":1.1,
                }
            },
            timeout=180
        )
        if resp.status_code != 200:
            return {"error": f"HTTP {resp.status_code}: {resp.text[:200]}",
                    "raw": "", "ipc_sections": [], "bns_sections": []}

        raw = resp.json().get("response", "").strip()
        return _parse_response(raw)

    except requests.ConnectionError:
        return {"error": f"Cannot connect to Ollama at {url}. Is it running?",
                "raw": "", "ipc_sections": [], "bns_sections": []}
    except requests.Timeout:
        return {"error": "Ollama timed out (>180s). Try a shorter input.",
                "raw": "", "ipc_sections": [], "bns_sections": []}
    except Exception as e:
        return {"error": str(e), "raw": "", "ipc_sections": [], "bns_sections": []}


def _parse_response(text: str) -> dict:
    """Extract structured fields from model response."""
    result = {
        "raw":          text,
        "ipc_sections": [],
        "bns_sections": [],
        "reasoning":    "",
        "error":        "",
    }

    # Extract IPC sections line
    ipc_match = re.search(r"IPC\s+Sections?:\s*(.*?)(?:\n|BNS|$)",
                           text, re.IGNORECASE | re.DOTALL)
    if ipc_match:
        raw_ipc = ipc_match.group(1).strip()
        # Parse "Section 376 (rape), Section 302 (murder)" etc.
        sections = re.findall(
            r"(?:Section\s+)?(\d{2,3}[A-Za-z]*(?:\(\d+\))?(?:\([a-z]\))?)",
            raw_ipc
        )
        result["ipc_sections"] = list(dict.fromkeys(
            s for s in sections if re.search(r"\d", s)
        ))

    # Extract BNS equivalents
    bns_match = re.search(r"BNS\s+Equivalents?:\s*(.*?)(?:\n|Reasoning|$)",
                           text, re.IGNORECASE | re.DOTALL)
    if bns_match:
        raw_bns = bns_match.group(1).strip()
        bns = re.findall(r"BNS\s+([\d\w\(\)/]+)", raw_bns, re.IGNORECASE)
        result["bns_sections"] = list(dict.fromkeys(bns))

    # Extract reasoning
    reason_match = re.search(r"Reasoning:\s*(.*?)(?:\n\n|$)",
                              text, re.IGNORECASE | re.DOTALL)
    if reason_match:
        result["reasoning"] = reason_match.group(1).strip()

    return result


def format_output(text: str, result: dict) -> str:
    lines = [
        "=" * 65,
        "LEGAL IPC SECTION PREDICTOR",
        "=" * 65,
        f"INPUT: {text[:200]}{'...' if len(text) > 200 else ''}",
        "-" * 65,
    ]

    if result.get("error"):
        lines.append(f"ERROR: {result['error']}")
    else:
        ipc = result.get("ipc_sections", [])
        bns = result.get("bns_sections", [])
        reasoning = result.get("reasoning", "")

        if ipc:
            lines.append(f"IPC Sections : {', '.join(ipc)}")
        else:
            lines.append("IPC Sections : Could not identify")

        if bns:
            lines.append(f"BNS (2023)   : {', '.join(bns)}")

        if reasoning:
            lines.append(f"Reasoning    : {reasoning}")

        lines.append("")
        lines.append("--- Full Model Response ---")
        lines.append(result.get("raw", ""))

    lines.append("=" * 65)
    return "\n".join(lines)


def check_model_available(model: str, url: str) -> bool:
    """Check if the Ollama model exists."""
    try:
        resp = requests.get(f"{url}/api/tags", timeout=5)
        models = [m["name"] for m in resp.json().get("models", [])]
        available = any(model.split(":")[0] in m for m in models)
        if not available:
            print(f"\nModel '{model}' not found in Ollama.")
            print(f"Available models: {models}")
            print(f"\nRun step2_build_ollama_model.py first to create it.")
        return available
    except Exception:
        print(f"Cannot connect to Ollama at {url}")
        print("Start Ollama with: ollama serve")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Predict IPC sections using fine-tuned Ollama model"
    )
    parser.add_argument("--model",       default=DEFAULT_MODEL,
                        help=f"Ollama model name (default: {DEFAULT_MODEL})")
    parser.add_argument("--url",         default=OLLAMA_URL,
                        help=f"Ollama URL (default: {OLLAMA_URL})")
    parser.add_argument("--text",        default="",
                        help="Case description text to predict")
    parser.add_argument("--file",        default="",
                        help="Text file with one case per line")
    parser.add_argument("--interactive", action="store_true",
                        help="Interactive mode — type cases one by one")
    parser.add_argument("--json_out",    action="store_true",
                        help="Output results as JSON")
    args = parser.parse_args()

    if not check_model_available(args.model, args.url):
        sys.exit(1)

    # ── Single text ───────────────────────────────────────────────────────────
    if args.text:
        result = predict_ollama(args.text, args.model, args.url)
        if args.json_out:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(format_output(args.text, result))

    # ── File of cases ─────────────────────────────────────────────────────────
    elif args.file:
        if not Path(args.file).exists():
            print(f"File not found: {args.file}")
            sys.exit(1)
        with open(args.file, encoding="utf-8") as f:
            lines = [l.strip() for l in f if l.strip()]
        print(f"Processing {len(lines)} cases from {args.file}...\n")
        all_results = []
        for i, line in enumerate(lines, 1):
            print(f"[{i}/{len(lines)}] Processing...")
            result = predict_ollama(line, args.model, args.url)
            if args.json_out:
                all_results.append({"input": line, **result})
            else:
                print(format_output(line, result))
                print()
        if args.json_out:
            print(json.dumps(all_results, indent=2, ensure_ascii=False))

    # ── Interactive mode ──────────────────────────────────────────────────────
    elif args.interactive:
        print("\n" + "=" * 65)
        print("  Legal IPC Predictor — Powered by Ollama + llama3.1")
        print("  Model:", args.model)
        print("=" * 65)
        print("Type case facts and press Enter to predict IPC sections.")
        print("Commands: 'quit' to exit | 'model <name>' to switch model")
        print()

        current_model = args.model
        while True:
            try:
                print("Case facts > ", end="", flush=True)
                text = input().strip()
            except (EOFError, KeyboardInterrupt):
                print("\nGoodbye.")
                break

            if not text:
                continue
            if text.lower() in ("quit", "exit", "q"):
                print("Goodbye.")
                break
            if text.lower().startswith("model "):
                current_model = text.split(" ", 1)[1].strip()
                print(f"Switched to model: {current_model}")
                continue

            print("Analyzing...\n")
            result = predict_ollama(text, current_model, args.url)
            print(format_output(text, result))
            print()

    else:
        parser.print_help()
        print("\nExamples:")
        print('  python step3_predict.py --interactive')
        print('  python step3_predict.py --text "A man broke into a house at night and raped a woman."')
        print('  python step3_predict.py --text "The accused committed murder with a knife." --json_out')


if __name__ == "__main__":
    main()
