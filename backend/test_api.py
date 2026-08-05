# import os
# from pathlib import Path
# import requests


# def load_dotenv(dotenv_path: Path) -> None:
#     if not dotenv_path.exists():
#         return

#     with dotenv_path.open(encoding="utf-8") as f:
#         for line in f:
#             line = line.strip()
#             if not line or line.startswith("#"):
#                 continue
#             if "=" not in line:
#                 continue
#             key, value = line.split("=", 1)
#             key = key.strip()
#             value = value.strip().strip('"').strip("'")
#             if key and key not in os.environ:
#                 os.environ[key] = value


# env_path = Path(__file__).resolve().parent / ".env"
# if not os.getenv("OPENAI_API_KEY"):
#     load_dotenv(env_path)

# api_key = os.getenv("OPENAI_API_KEY")
# if not api_key:
#     raise SystemExit("Set OPENAI_API_KEY in your environment first.")

# response = requests.get(
#     "https://api.openai.com/v1/models",
#     headers={"Authorization": f"Bearer {api_key}"}
# )

# print("Status:", response.status_code)
# print(response.text)

import os
from pathlib import Path
import requests

def load_dotenv(dotenv_path: Path) -> None:
    if not dotenv_path.exists():
        return
    with dotenv_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value

env_path = Path(__file__).resolve().parent / ".env"
if not os.getenv("OPENAI_API_KEY"):
    load_dotenv(env_path)

api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise SystemExit("Set OPENAI_API_KEY in your environment first.")

url = "https://api.openai.com/v1/chat/completions"
headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json",
}
data = {
    "model": "gpt-3.5-turbo",
    "messages": [
        {"role": "user", "content": "Hello"}
    ],
    "max_tokens": 50,
}

response = requests.post(url, headers=headers, json=data)
print("Status:", response.status_code)
print(response.text)