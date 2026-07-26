"""
11_predict.py
=============
Final inference script. Queries the trained model via Ollama API.

The model at this point is backed by TRAINED LoRA weights converted
to GGUF — not the few-shot Modelfile from step2_build_ollama_model.py.

Usage:
    python scripts/11_predict.py --interactive
    python scripts/11_predict.py --text "Two men raped a woman and threatened her."
    python scripts/11_predict.py --text "..." --model legal-ipc-trained
    python scripts/11_predict.py --file cases.txt --json_out
"""

import re
import json
import argparse
import sys
import requests
from pathlib import Path


DEFAULT_MODEL = "legal-ipc-trained"
OLLAMA_URL    = "http://127.0.0.1:11434"

# Deterministic IPC→BNS mapping (same as 02_prepare_dataset.py)
IPC_TO_BNS: dict[str, str] = {
    "34":"3(5)","107":"45","109":"48","120B":"61(2)",
    "166A":"166A","201":"238","202":"239","203":"240","204":"241",
    "302":"101","303":"102","304":"105","304A":"106",
    "304B":"80","306":"108","307":"109","309":"226",
    "323":"115(2)","324":"117(2)","325":"116(2)","326":"117(3)",
    "326A":"124","326B":"125",
    "354":"74","354A":"75","354B":"76","354C":"77","354D":"78",
    "363":"137(2)","364":"139","364A":"140","366":"142",
    "370":"143","375":"63","376":"64","376A":"66","376AB":"65",
    "376(2)":"64(2)","376(2)(g)":"70","376D":"70",
    "392":"309(1)","395":"310(2)","396":"311",
    "406":"316(2)","409":"316(3)","411":"317","420":"318(4)",
    "447":"329(1)","448":"329(2)","450":"330","452":"332",
    "498A":"86","499":"356","500":"356(2)","506":"351","509":"79",
}


def check_ollama(model: str, url: str) -> bool:
    try:
        resp = requests.get(f"{url}/api/tags", timeout=5)
        if resp.status_code != 200:
            return False
        models = [m["name"] for m in resp.json().get("models", [])]
        base = model.split(":")[0]
        return any(base in m for m in models)
    except Exception:
        return False


def predict(text: str, model: str, url: str) -> dict:
    prompt = (
        f"Case facts:\n{text}\n\n"
        f"Identify applicable IPC sections in this format:\n"
        f"IPC Sections: [sections]\nBNS Equivalents: [BNS numbers]"
    )
    try:
        resp = requests.post(
            f"{url}/api/generate",
            json={
                "model": model, "prompt": prompt, "stream": False,
                "options": {
                    "temperature": 0.1, "num_predict": 120,
                    "num_ctx": 2048, "repeat_penalty": 1.1,
                }
            },
            timeout=180
        )
        if resp.status_code != 200:
            return {"error": f"HTTP {resp.status_code}", "raw": "",
                    "ipc_sections": [], "bns_sections": [], "reasoning": ""}
        raw = resp.json().get("response", "").strip()
        return _parse(raw)
    except requests.ConnectionError:
        return {"error": f"Cannot connect to Ollama at {url}. Run: ollama serve",
                "raw": "", "ipc_sections": [], "bns_sections": [], "reasoning": ""}
    except requests.Timeout:
        return {"error": "Ollama timed out", "raw": "",
                "ipc_sections": [], "bns_sections": [], "reasoning": ""}
    except Exception as e:
        return {"error": str(e), "raw": "", "ipc_sections": [], "bns_sections": [], "reasoning": ""}


def _parse(text: str) -> dict:
    # IPC sections
    ipc_m = re.search(r'IPC\s+Sections?:\s*(.*?)(?:\n|$)', text, re.IGNORECASE)
    raw_ipc = ipc_m.group(1).strip() if ipc_m else text
    # Extract all section-like numbers
    candidates = re.findall(r'(\d{2,3}[A-Za-z]*(?:\(\d+\))?(?:\([a-z]\))?)', raw_ipc)

    # Validate: only keep plausible IPC sections (100-511)
    KNOWN_NON_IPC = {str(i) for i in range(1, 100)}
    ipc_secs = []
    for s in candidates:
        base_m = re.match(r'^(\d+)', s)
        if not base_m:
            continue
        base = int(base_m.group(1))
        if 100 <= base <= 511 and str(base) not in KNOWN_NON_IPC:
            ipc_secs.append(s)
    ipc_secs = list(dict.fromkeys(ipc_secs))  # deduplicate

    # BNS: use deterministic mapping (model output BNS may hallucinate)
    bns_secs = []
    for s in ipc_secs:
        bns = IPC_TO_BNS.get(s) or IPC_TO_BNS.get(s.split("(")[0])
        if bns:
            bns_secs.append(f"BNS {bns}")

    # Reasoning from model output (optional)
    reason_m = re.search(r'Reasoning:\s*(.*?)(?:\n\n|$)', text, re.IGNORECASE | re.DOTALL)
    reasoning = reason_m.group(1).strip() if reason_m else ""

    return {
        "ipc_sections": ipc_secs,
        "bns_sections": bns_secs,
        "reasoning":    reasoning,
        "raw":          text,
        "error":        "",
    }


def format_output(text: str, result: dict) -> str:
    lines = [
        "=" * 65,
        f"INPUT   : {text[:200]}{'...' if len(text) > 200 else ''}",
        "-" * 65,
    ]
    if result["error"]:
        lines.append(f"ERROR   : {result['error']}")
    else:
        ipc = result["ipc_sections"]
        bns = result["bns_sections"]
        lines.append(f"IPC     : {', '.join(ipc) if ipc else 'Not identified'}")
        if bns:
            lines.append(f"BNS     : {', '.join(bns)}")
        if result["reasoning"]:
            lines.append(f"Reason  : {result['reasoning'][:200]}")
        lines.append("")
        lines.append("Model response:")
        lines.append(result["raw"])
    lines.append("=" * 65)
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Predict IPC sections (trained model)")
    parser.add_argument("--model",       default=DEFAULT_MODEL)
    parser.add_argument("--url",         default=OLLAMA_URL)
    parser.add_argument("--text",        default="")
    parser.add_argument("--file",        default="")
    parser.add_argument("--interactive", action="store_true")
    parser.add_argument("--json_out",    action="store_true")
    args = parser.parse_args()

    # Check Ollama
    if not check_ollama(args.model, args.url):
        print(f"\n✗ Model '{args.model}' not found in Ollama.")
        print("  Available models:")
        try:
            r = requests.get(f"{args.url}/api/tags", timeout=5)
            for m in r.json().get("models", []):
                print(f"    {m['name']}")
        except Exception:
            print("    (cannot connect to Ollama — run: ollama serve)")
        print(f"\n  Run 10_build_ollama.py first, or use:")
        print(f"    python scripts/10_build_ollama.py --model_name {args.model}")
        raise SystemExit(1)

    # ── Single text ───────────────────────────────────────────────────────────
    if args.text:
        result = predict(args.text, args.model, args.url)
        if args.json_out:
            print(json.dumps({"input": args.text, **result}, indent=2))
        else:
            print(format_output(args.text, result))

    # ── File ──────────────────────────────────────────────────────────────────
    elif args.file:
        fp = Path(args.file)
        if not fp.exists():
            print(f"File not found: {fp}")
            raise SystemExit(1)
        lines = [l.strip() for l in fp.read_text(encoding="utf-8").splitlines() if l.strip()]
        all_results = []
        for i, line in enumerate(lines, 1):
            print(f"[{i}/{len(lines)}]", end=" ", flush=True)
            r = predict(line, args.model, args.url)
            if args.json_out:
                all_results.append({"input": line, **r})
            else:
                print(format_output(line, r))
        if args.json_out:
            print(json.dumps(all_results, indent=2, ensure_ascii=False))

    # ── Interactive ───────────────────────────────────────────────────────────
    elif args.interactive:
        print("\n" + "=" * 65)
        print("  Legal IPC Predictor — Trained Model via Ollama")
        print(f"  Model: {args.model}")
        print("=" * 65)
        print("Type case facts. Type 'quit' to exit.\n")
        while True:
            try:
                print("Facts > ", end="", flush=True)
                text = input().strip()
            except (EOFError, KeyboardInterrupt):
                print("\nGoodbye.")
                break
            if not text:
                continue
            if text.lower() in ("quit", "exit", "q"):
                print("Goodbye.")
                break
            print("Analyzing...\n")
            result = predict(text, args.model, args.url)
            print(format_output(text, result))
            print()
    else:
        parser.print_help()
        print("\nExample:")
        print('  python scripts/11_predict.py --text "A man broke into a house and raped a woman." --model legal-ipc-trained')


if __name__ == "__main__":
    main()
