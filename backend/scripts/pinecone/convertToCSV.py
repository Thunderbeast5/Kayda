import csv
import os
import re
import pypdf

# Set base directory dynamically
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PDF_PATH = os.path.join(BASE_DIR, "pocso.pdf")
CSV_PATH = os.path.join(BASE_DIR, "POCSO_Sections.csv")


def extract_pocso_to_csv(pdf_path, output_csv_path):
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF file not found at path: {pdf_path}")

    print("Extracting text from pocso.pdf...")
    reader = pypdf.PdfReader(pdf_path)
    full_text = "\n".join(
        [page.extract_text() for page in reader.pages if page.extract_text()]
    )

    # 1. Match Chapter headings (e.g., CHAPTER I, CHAPTER II)
    chapter_pattern = re.compile(
        r"CHAPTER\s+([I|V|X|L|C|D|M]+)\b[\.\s—–-]*([^\n]+)", re.IGNORECASE
    )
    chapters = []
    for match in chapter_pattern.finditer(full_text):
        chapters.append(
            {
                "num": match.group(1).upper(),
                "title": match.group(2).strip(),
                "start": match.start(),
            }
        )

    def get_chapter(pos):
        current_num, current_title = "N/A", "N/A"
        for chap in chapters:
            if pos >= chap["start"]:
                current_num = chap["num"]
                current_title = chap["title"]
            else:
                break
        return current_num, current_title

    # 2. Section Pattern for POCSO (Matches section numbers at line boundaries)
    section_pattern = re.compile(
        r"(?:^|\n)\s*(\d{1,2}[A-Z]?)\.\s+([^.\n]+[\.?])", re.MULTILINE
    )
    matches = list(section_pattern.finditer(full_text))

    print(f"Found {len(matches)} section candidate markers. Processing...")

    sections_data = []

    for i, match in enumerate(matches):
        sec_num = match.group(1)
        raw_title = match.group(2).strip()

        # Skip table of contents or index repetitions if matched before main text body
        start_pos = match.start()
        end_pos = (
            matches[i + 1].start() if i + 1 < len(matches) else len(full_text)
        )
        sec_block = full_text[start_pos:end_pos]

        # Extract sub-sections
        sub_secs = re.findall(r"\((?:\d+|[a-z]+)\)", sec_block)
        sub_sections_str = (
            ", ".join(sorted(set(sub_secs))) if sub_secs else "Single"
        )

        # Extract punishment details if present within the section block
        punishment_match = re.search(
            r"(shall be punished [^.\n]+|imprisonment [^.\n]+)",
            sec_block,
            re.IGNORECASE,
        )
        punishment = (
            punishment_match.group(1).strip() if punishment_match else "N/A"
        )

        # Build Description text
        clean_text = " ".join(sec_block.split())
        description = (
            clean_text[:250] + "..." if len(clean_text) > 250 else clean_text
        )

        # Get Chapter info
        chap_num, chap_title = get_chapter(start_pos)

        sections_data.append(
            [
                sec_num,
                sub_sections_str,
                raw_title,
                description,
                punishment,
                chap_num,
                chap_title,
            ]
        )

    # 3. Write output to CSV
    headers = [
        "Section",
        "Sub_Sections",
        "Title",
        "Description",
        "Punishment",
        "Chapter",
        "Chapter_Title",
    ]

    os.makedirs(os.path.dirname(output_csv_path), exist_ok=True)
    with open(output_csv_path, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(sections_data)

    print(
        f"Successfully converted pocso.pdf to CSV! Saved {len(sections_data)} sections in '{output_csv_path}'."
    )


# Execute
extract_pocso_to_csv(PDF_PATH, CSV_PATH)