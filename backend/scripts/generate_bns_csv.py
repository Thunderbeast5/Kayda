import fitz  # PyMuPDF
import re
import csv

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

PDF_PATH = BASE_DIR.parent.parent / "data" / "BNS.pdf"
OUTPUT_CSV = BASE_DIR.parent.parent / "data" / "bns_sections.csv"

doc = fitz.open(PDF_PATH)

text = ""
for page in doc:
    text += page.get_text()

# Remove extra spaces
text = re.sub(r"\r", "", text)
text = re.sub(r"[ \t]+", " ", text)

lines = text.split("\n")

chapter = ""
chapter_title = ""

rows = []

current_section = None
current_title = ""
current_desc = ""

for line in lines:

    line = line.strip()

    if not line:
        continue

    # Detect chapter
    m = re.match(r"CHAPTER\s+([IVXLC]+)", line)
    if m:
        chapter = m.group(1)
        continue

    if chapter and line.isupper():
        chapter_title = line.title()
        continue

    # Detect section
    m = re.match(r"^(\d+)\.\s*(.+)$", line)

    if m:

        # Save previous section
        if current_section is not None:
            rows.append({
                "Section": current_section,
                "Title": current_title,
                "Description": current_desc.strip(),
                "Punishment": "",
                "Chapter": chapter,
                "Chapter_Title": chapter_title
            })

        current_section = m.group(1)
        current_title = m.group(2)
        current_desc = ""

    else:
        if current_section:
            current_desc += line + " "

# Save last section
if current_section:
    rows.append({
        "Section": current_section,
        "Title": current_title,
        "Description": current_desc.strip(),
        "Punishment": "",
        "Chapter": chapter,
        "Chapter_Title": chapter_title
    })

with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(
        f,
        fieldnames=[
            "Section",
            "Title",
            "Description",
            "Punishment",
            "Chapter",
            "Chapter_Title",
        ],
    )

    writer.writeheader()
    writer.writerows(rows)

print(f"Generated {len(rows)} sections.")