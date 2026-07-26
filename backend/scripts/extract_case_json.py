import os
import json
from pathlib import Path

from dotenv import load_dotenv
from groq import Groq

load_dotenv()

client = Groq(
    api_key=os.getenv("GROQ_API_KEY")
)
BASE_DIR = Path(__file__).resolve().parents[2]

CLEANED_DIR = BASE_DIR / "data" / "cleaned"
OUTPUT_DIR = BASE_DIR / "data" / "json"

OUTPUT_DIR.mkdir(exist_ok=True)
for txt_file in CLEANED_DIR.glob("*.txt"):

    print(f"Processing {txt_file.name}")

    with open(txt_file, encoding="utf-8") as f:
        judgment = f.read()

    prompt = f"""
    `You are an expert Indian Criminal Lawyer.

    Convert the following Indian criminal judgment into structured JSON.

    IMPORTANT RULES:

    1. Return ONLY valid JSON.
    2. Do not include markdown.
    3. Do not include explanations.
    4. If a field is unavailable, use an empty string or an empty list.
    5. Preserve the legal meaning; do not invent facts.

    Use EXACTLY this schema:

    {{
    "metadata": {{
        "case_name": "",
        "court": "",
        "date": "",
        "judge": "",
        "citation": ""
    }},

    "facts": [
        {{
        "id": "F1",
        "text": ""
        }}
    ],

    "issues": [
        {{
        "id": "I1",
        "text": ""
        }}
    ],

    "ipc_bns_sections": [
        {{
        "act": "",
        "section": "",
        "title": ""
        }}
    ],

    "prosecution_arguments": [
        {{
        "id": "P1",
        "text": ""
        }}
    ],

    "defense_arguments": [
        {{
        "id": "D1",
        "text": ""
        }}
    ],

    "judge_reasoning": [
        {{
        "id": "R1",
        "text": ""
        }}
    ],

    "decision": {{
        "outcome": "",
        "summary": ""
    }},

    "legal_principles": [
        {{
        "id": "LP1",
        "text": ""
        }}
    ]
    }}

    Instructions:

    - Split facts into individual factual statements.
    - Split legal issues into separate questions.
    - Extract every IPC/BNS section mentioned.
    - For each section provide:
    - act (IPC or BNS)
    - section number only (e.g. "69", "351(3)")
    - official section title if available.
    - Separate prosecution and defense arguments.
    - Extract the judge's reasoning as separate points.
    - Decision should contain:
    - outcome
    - short summary.
    - Extract every legal principle separately.

    Judgment:

    {judgment}
    """
    response = client.chat.completions.create(
        model="openai/gpt-oss-120b",   # or another Groq-supported model
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ],
        temperature=0
    )

    output = response.choices[0].message.content
    output = output.strip()

    if output.startswith("```"):
        output = output.replace("```json", "").replace("```", "").strip()

    case_json = json.loads(output)
    output_path = OUTPUT_DIR / f"{txt_file.stem}.json"

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(case_json, f, indent=4, ensure_ascii=False)
        
    print(f"Saved {output_path.name}")