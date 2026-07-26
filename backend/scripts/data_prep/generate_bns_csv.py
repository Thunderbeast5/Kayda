import fitz  # PyMuPDF
import re
import csv

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

PDF_PATH = BASE_DIR.parent.parent / "data" / "new" / "BNS.pdf"
OUTPUT_CSV = BASE_DIR.parent.parent / "data" / "new"/ "bns_sections1.csv"

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
current_subsections = []

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
                "Sub_Sections": ",".join(current_subsections),
                "Title": current_title,
                "Description": current_desc.strip(),
                "Punishment": "",
                "Chapter": chapter,
                "Chapter_Title": chapter_title
            })
        current_section = m.group(1)
        current_title = m.group(2)
        current_desc = ""
        current_subsections = []

    else:

        if current_section:

            # Detect subsection numbers like (1), (2), (a), (b), (i), (ii)
            sub = re.match(r"^\(([0-9]+|[a-z]+|[ivxlcdm]+)\)", line, re.IGNORECASE)

            if sub:
                current_subsections.append(sub.group(1))

            current_desc += line + " "

# Save last section
if current_section:
    rows.append({
        "Section": current_section,
        "Sub_Sections": ",".join(current_subsections),
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
            "Sub_Sections",
            "Title",
            "Description",
            "Punishment",
            "Chapter",
            "Chapter_Title",
        ]
    )

    writer.writeheader()
    writer.writerows(rows)

print(f"Generated {len(rows)} sections.")