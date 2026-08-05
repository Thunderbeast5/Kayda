import os
import re
import pandas as pd
from pypdf import PdfReader
from tqdm import tqdm

# ==========================================================
# CONFIGURATION
# ==========================================================
PDF_FOLDER_PATH = r"C:\Users\Ajinkya\Desktop\MootCourt\data\Dataset"
OUTPUT_FOLDER_PATH = r"C:\Users\Ajinkya\Desktop\MootCourt\data\Dataset_csv"

os.makedirs(OUTPUT_FOLDER_PATH, exist_ok=True)

# ==========================================================
# PDF TEXT EXTRACTION
# ==========================================================
def extract_text_from_pdf(pdf_path):
    try:
        reader = PdfReader(pdf_path)
        pages = []

        for page in reader.pages:
            text = page.extract_text()
            if text:
                pages.append(text)

        return "\n".join(pages)

    except Exception as e:
        print(f"Error reading {pdf_path}: {e}")
        return ""

# ==========================================================
# METADATA EXTRACTION
# ==========================================================
def extract_court(text):

    text_upper = text.upper()

    if "SUPREME COURT OF INDIA" in text_upper:
        return "Supreme Court of India"

    match = re.search(
        r"HIGH COURT.*",
        text,
        re.IGNORECASE
    )

    if match:
        return match.group(0).strip()

    return ""


def extract_date(text):

    patterns = [
        r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}",
        r"\d{1,2}\.\d{1,2}\.\d{2,4}"
    ]

    for pattern in patterns:
        match = re.search(pattern, text)

        if match:
            return match.group(0)

    return ""


def extract_ipc_sections(text):

    patterns = [

        r"Sections?\s+([\dA-Za-z,\-\s]+)\s+of\s+the\s+Indian\s+Penal\s+Code",

        r"Sections?\s+([\dA-Za-z,\-\s]+)\s+of\s+the\s+IPC",

        r"Sections?\s+([\dA-Za-z,\-\s]+)\s+IPC",

        r"Sections?\s+([\dA-Za-z,\-\s]+)\s+of\s+IPC",

        r"Sections?\s+([\dA-Za-z,\-\s]+)\s+of\s+the\s+BNS",

        r"Sections?\s+([\dA-Za-z,\-\s]+)\s+BNS"
    ]

    sections = set()

    for pattern in patterns:

        matches = re.findall(pattern, text, re.IGNORECASE)

        for match in matches:

            nums = re.findall(r"\d+[A-Za-z]?", match)

            sections.update(nums)

    return ", ".join(sorted(sections))


def extract_acts(text):

    acts = [

        "IPC",
        "Indian Penal Code",

        "BNS",
        "Bharatiya Nyaya Sanhita",

        "CrPC",
        "Code of Criminal Procedure",

        "BNSS",

        "POCSO",
        "Protection of Children from Sexual Offences Act",

        "Dowry Prohibition Act",

        "Domestic Violence Act",

        "Hindu Marriage Act",

        "Hindu Succession Act",

        "Indian Evidence Act",

        "Evidence Act",

        "Constitution",

        "Sexual Harassment of Women at Workplace Act",

        "Maternity Benefit Act"

    ]

    found = []

    lower = text.lower()

    for act in acts:

        if act.lower() in lower:
            found.append(act)

    return ", ".join(found)


def important_text(text):

    if len(text) <= 12000:
        return text

    beginning = text[:7000]

    ending = text[-4000:]

    return (
        beginning
        + "\n\n...[OMITTED MIDDLE OF JUDGMENT]...\n\n"
        + ending
    )

# ==========================================================
# FIND ALL PDFs
# ==========================================================
pdf_paths = []

for root, dirs, files in os.walk(PDF_FOLDER_PATH):

    for file in files:

        if file.lower().endswith(".pdf"):

            pdf_paths.append(os.path.join(root, file))

print(f"Found {len(pdf_paths)} PDFs.")

# ==========================================================
# CONVERT EACH PDF TO ITS OWN CSV
# ==========================================================
for pdf_path in tqdm(pdf_paths):

    judgment_text = extract_text_from_pdf(pdf_path)

    if not judgment_text.strip():
        continue

    case_name = os.path.splitext(os.path.basename(pdf_path))[0]

    # Folder name becomes category
    case_category = os.path.basename(os.path.dirname(pdf_path))

    relative_folder = os.path.relpath(
        os.path.dirname(pdf_path),
        PDF_FOLDER_PATH
    )

    output_dir = os.path.join(
        OUTPUT_FOLDER_PATH,
        relative_folder
    )

    os.makedirs(output_dir, exist_ok=True)

    row = {

        "case_name": case_name,

        "court": extract_court(judgment_text),

        "decision_date": extract_date(judgment_text),

        "ipc_sections": extract_ipc_sections(judgment_text),

        "acts_referred": extract_acts(judgment_text),

        "case_category": case_category,

        "text_for_classification": important_text(judgment_text),

        "judgment_text": judgment_text

    }

    df = pd.DataFrame([row])

    csv_path = os.path.join(
        output_dir,
        case_name + ".csv"
    )

    df.to_csv(
        csv_path,
        index=False,
        encoding="utf-8-sig"
    )

print("\nDone!")
print(f"Individual CSV files saved in:\n{OUTPUT_FOLDER_PATH}")