"""
predict.py — Step 4: Run inference on new case descriptions.

Usage:
    python predict.py --text "A 12-year-old girl was raped by her teacher..."
    python predict.py --file cases_to_predict.txt
    python predict.py --interactive
"""
import argparse
import sys
import torch
sys.path.insert(0, "src")

from utils.logger_setup import setup_logger

logger = setup_logger()

INSTRUCTION = (
    "You are a legal expert in Indian criminal law. Given the following case facts "
    "from the Supreme Court of India, identify all applicable IPC sections and provide "
    "their BNS equivalents."
)


def load_model(model_path: str, base_model: str):
    from transformers import AutoTokenizer, AutoModelForCausalLM
    from peft import PeftModel

    logger.info(f"Loading model from {model_path}...")
    tokenizer = AutoTokenizer.from_pretrained(model_path)
    base = AutoModelForCausalLM.from_pretrained(
        base_model,
        torch_dtype=torch.float16,
        device_map="auto",
    )
    model = PeftModel.from_pretrained(base, model_path)
    model.eval()
    logger.info("Model loaded")
    return model, tokenizer


def predict_one(model, tokenizer, text: str, device: str = "cuda") -> str:
    prompt = (
        f"<s>[INST] {INSTRUCTION}\n\n{text} [/INST]"
    )
    inputs = tokenizer(prompt, return_tensors="pt").to(device)
    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens     = 300,
            temperature        = 0.1,
            do_sample          = True,
            top_p              = 0.95,
            repetition_penalty = 1.1,
            pad_token_id       = tokenizer.eos_token_id,
        )
    response = tokenizer.decode(
        outputs[0][inputs["input_ids"].shape[1]:],
        skip_special_tokens=True
    ).strip()
    return response


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model_path", default="models/legal_model/final")
    parser.add_argument("--base_model",
                        default="mistralai/Mistral-7B-Instruct-v0.2")
    parser.add_argument("--text",        default="",
                        help="Case description text")
    parser.add_argument("--file",        default="",
                        help="File with one case per line")
    parser.add_argument("--interactive", action="store_true",
                        help="Interactive mode — type cases one by one")
    args = parser.parse_args()

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model, tokenizer = load_model(args.model_path, args.base_model)

    if args.text:
        result = predict_one(model, tokenizer, args.text, device)
        print("\n" + "=" * 60)
        print("INPUT :", args.text[:200])
        print("-" * 60)
        print("OUTPUT:", result)
        print("=" * 60)

    elif args.file:
        with open(args.file, encoding="utf-8") as f:
            lines = [l.strip() for l in f if l.strip()]
        for i, line in enumerate(lines, 1):
            result = predict_one(model, tokenizer, line, device)
            print(f"\n[{i}] INPUT : {line[:150]}")
            print(f"    OUTPUT: {result}\n")

    elif args.interactive:
        print("Legal IPC Predictor — type case facts, press Enter twice to predict.")
        print("Type 'quit' to exit.\n")
        while True:
            lines = []
            print("Case facts> ", end="", flush=True)
            while True:
                line = input()
                if line.lower() == "quit":
                    sys.exit(0)
                if line == "" and lines:
                    break
                lines.append(line)
            text = " ".join(lines)
            if text:
                result = predict_one(model, tokenizer, text, device)
                print("\nPrediction:")
                print(result)
                print()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
