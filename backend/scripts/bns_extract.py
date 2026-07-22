from pathlib import Path
import pdfplumber
import re

# ----------------------------------------------------
# Paths
# ----------------------------------------------------

BASE_DIR = Path(__file__).resolve().parents[2]

PDF_PATH = BASE_DIR / "data" / "new" / "BNS.pdf"

OUTPUT_DIR = BASE_DIR / "data" / "processed"
OUTPUT_DIR.mkdir(exist_ok=True)

RAW_TEXT = OUTPUT_DIR / "bns_raw.txt"
CLEAN_TEXT = OUTPUT_DIR / "bns_clean.txt"

# ----------------------------------------------------
# Step 1 : Extract PDF
# ----------------------------------------------------

print("Extracting PDF...")

text = ""

with pdfplumber.open(PDF_PATH) as pdf:
    for page in pdf.pages:

        page_text = page.extract_text()

        if page_text:
            text += page_text + "\n"

with open(RAW_TEXT, "w", encoding="utf-8") as f:
    f.write(text)

print("Raw text saved.")

# ----------------------------------------------------
# Step 2 : Clean text
# ----------------------------------------------------

print("Cleaning text...")

# Gazette headers
text = re.sub(r"THE GAZETTE OF INDIA.*", "", text)

# Page references
text = re.sub(r"\[PART.*?\]", "", text)

# Multiple blank lines
text = re.sub(r"\n{2,}", "\n", text)

# Multiple spaces
text = re.sub(r"[ \t]+", " ", text)

# Remove leading/trailing spaces
lines = []

for line in text.splitlines():

    line = line.strip()

    if line == "":
        continue

    lines.append(line)

text = "\n".join(lines)

with open(CLEAN_TEXT, "w", encoding="utf-8") as f:
    f.write(text)

print("Clean text saved.")

print(f"\nSaved to:\n{CLEAN_TEXT}")