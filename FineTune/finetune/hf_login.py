"""
One-time HuggingFace login to access Gemma-2B.

Gemma requires accepting Google's terms at:
  https://huggingface.co/google/gemma-2b-it

After accepting, run:
    python finetune/hf_login.py

This stores your token in ~/.cache/huggingface/token
You only need to do this once per machine.
"""

import sys


def main():
    try:
        from huggingface_hub import login, whoami
    except ImportError:
        print("Run: pip install huggingface_hub")
        sys.exit(1)

    print("HuggingFace Login")
    print("─" * 40)
    print("You need a HF account and must accept Gemma's terms at:")
    print("  https://huggingface.co/google/gemma-2b-it")
    print()

    # Check if already logged in
    try:
        user = whoami()
        print(f"Already logged in as: {user['name']}")
        print("Token is cached. You're ready to download Gemma.")
        return
    except Exception:
        pass

    token = input("Paste your HuggingFace token (from https://huggingface.co/settings/tokens): ").strip()
    if not token:
        print("No token provided.")
        sys.exit(1)

    login(token=token)
    print("Login successful. Token cached.")
    print()
    print("Next: run  python finetune/train.py --dry-run  to verify setup")
    print("Then: run  python finetune/train.py  to start training")


if __name__ == "__main__":
    main()
